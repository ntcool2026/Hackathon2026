"""Layer 1 — Data pipeline: fetch stock data, compute scores, broadcast updates."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.yfinance_adapter import YFinanceAdapter
from backend.db import AsyncSessionLocal
from backend.models import (
    CustomCriterion,
    Recommendation,
    ScoreBreakdown,
    StockData,
    UserPreferences,
    WSEvent,
)
from backend.models_orm import (
    CustomCriterion as CustomCriterionORM,
    Portfolio,
    PortfolioStock,
    StockData as StockDataORM,
    StockScore as StockScoreORM,
    StockScoreHistory,
    UserPreferences as UserPreferencesORM,
    UserThreshold as UserThresholdORM,
    RefreshLog,
)
from backend.scoring import compute_recommendation, compute_risk_score
from backend.settings import settings

logger = logging.getLogger(__name__)

_yfinance = YFinanceAdapter()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_data_pipeline() -> None:
    """Fetch fresh stock data, compute scores, persist, and broadcast."""
    async with AsyncSessionLocal() as db:
        log_id = await _log_cycle_start(db)
        started_at = datetime.now(tz=timezone.utc)
        errors: dict[str, str] = {}
        stocks_updated = 0

        try:
            # 1. Collect all unique tickers across all portfolios
            tickers = await _get_all_tickers(db)
            if not tickers:
                logger.info("Data pipeline: no tickers to process")
                await _log_cycle_end(db, log_id, 0, {})
                return

            # 2. Fetch stock data concurrently with semaphore
            semaphore = asyncio.Semaphore(settings.fetch_concurrency)
            tasks = [_fetch_with_retry(ticker, semaphore) for ticker in tickers]
            results: list[StockData | None] = await asyncio.gather(*tasks)

            # 3. Upsert stock_data rows
            stock_map: dict[str, StockData] = {}
            for ticker, stock_data in zip(tickers, results):
                if stock_data is None:
                    errors[ticker] = "fetch failed after 3 retries"
                    # Mark stale
                    await db.execute(
                        text(
                            "UPDATE stock_data SET is_stale = true WHERE ticker = :t"
                        ),
                        {"t": ticker},
                    )
                else:
                    stock_map[ticker] = stock_data
                    await _upsert_stock_data(db, stock_data)
                    stocks_updated += 1

            await db.commit()

            # 4. Score per user and persist
            user_ids = await _get_all_user_ids(db)
            for user_id in user_ids:
                prefs = await _get_preferences(db, user_id)
                criteria = await _get_criteria(db, user_id)
                thresholds = await _get_thresholds(db, user_id)
                user_tickers = await _get_user_tickers(db, user_id)

                for ticker in user_tickers:
                    stock_data = stock_map.get(ticker)
                    if stock_data is None:
                        continue
                    breakdown = compute_risk_score(stock_data, prefs, criteria)
                    recommendation = compute_recommendation(breakdown.final_score)

                    # Read prev score BEFORE upsert so threshold crossing detection works
                    threshold_val = thresholds.get(ticker)
                    prev_score: float | None = None
                    if threshold_val is not None:
                        prev_row = await db.execute(
                            select(StockScoreORM.risk_score).where(
                                StockScoreORM.user_id == user_id,
                                StockScoreORM.ticker == ticker,
                            )
                        )
                        prev_val = prev_row.scalar_one_or_none()
                        prev_score = float(prev_val) if prev_val is not None else None

                    await _upsert_stock_score(db, user_id, ticker, breakdown, recommendation)
                    await _append_score_history(db, user_id, ticker, breakdown, recommendation)

                    # Threshold alert check (uses prev_score captured before upsert)
                    if threshold_val is not None:
                        crossed = prev_score is not None and prev_score < threshold_val <= breakdown.final_score
                        if crossed:
                            from backend.ws_manager import ws_manager as _ws
                            await _ws.broadcast_to_user(
                                user_id,
                                WSEvent(
                                    event="threshold_alert",
                                    payload={
                                        "ticker": ticker,
                                        "risk_score": breakdown.final_score,
                                        "threshold": threshold_val,
                                    },
                                ),
                            )

                    # Broadcast score_update
                    from backend.ws_manager import ws_manager
                    await ws_manager.broadcast_to_user(
                        user_id,
                        WSEvent(
                            event="score_update",
                            payload={
                                "ticker": ticker,
                                "risk_score": breakdown.final_score,
                                "recommendation": recommendation.value,
                                "breakdown": breakdown.model_dump(),
                            },
                        ),
                    )

            await db.commit()
            await _log_cycle_end(db, log_id, stocks_updated, errors)
            logger.info(
                "Data pipeline complete: %d stocks updated, %d errors",
                stocks_updated,
                len(errors),
            )

        except Exception as exc:
            logger.exception("Data pipeline failed: %s", exc)
            await _log_cycle_end(db, log_id, stocks_updated, {"_pipeline": str(exc)})




# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------


async def _fetch_with_retry(ticker: str, semaphore: asyncio.Semaphore) -> StockData | None:
    async with semaphore:
        for attempt in range(3):
            try:
                return await _yfinance.fetch_stock_data(ticker)
            except Exception as exc:
                logger.warning(
                    "Fetch attempt %d/3 failed for %s: %s", attempt + 1, ticker, exc
                )
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
        return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _get_all_tickers(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(PortfolioStock.ticker).distinct()
    )
    return [row[0] for row in result.all()]


async def _get_all_user_ids(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(Portfolio.user_id).distinct()
    )
    return [row[0] for row in result.all()]


async def _get_user_tickers(db: AsyncSession, user_id: str) -> list[str]:
    result = await db.execute(
        select(PortfolioStock.ticker)
        .join(Portfolio, Portfolio.id == PortfolioStock.portfolio_id)
        .where(Portfolio.user_id == user_id)
        .distinct()
    )
    return [row[0] for row in result.all()]


async def _get_preferences(db: AsyncSession, user_id: str) -> UserPreferences:
    result = await db.execute(
        select(UserPreferencesORM).where(UserPreferencesORM.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return UserPreferences()
    return UserPreferences(
        risk_tolerance=row.risk_tolerance,
        time_horizon=row.time_horizon,
        sector_preference=row.sector_preference or [],
        dividend_preference=row.dividend_preference,
        growth_vs_value=row.growth_vs_value,
    )


async def _get_criteria(db: AsyncSession, user_id: str) -> list[CustomCriterion]:
    result = await db.execute(
        select(CustomCriterionORM).where(CustomCriterionORM.user_id == user_id)
    )
    rows = result.scalars().all()
    return [
        CustomCriterion(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            description=row.description,
            weight=row.weight,
            metric=row.metric,
            operator=row.operator,
            threshold=row.threshold,
        )
        for row in rows
    ]


async def _get_thresholds(db: AsyncSession, user_id: str) -> dict[str, float]:
    result = await db.execute(
        select(UserThresholdORM).where(UserThresholdORM.user_id == user_id)
    )
    return {row.ticker: float(row.threshold) for row in result.scalars().all()}


async def _upsert_stock_data(db: AsyncSession, stock_data: StockData) -> None:
    stmt = pg_insert(StockDataORM).values(
        ticker=stock_data.ticker,
        price=stock_data.price,
        price_change_pct=stock_data.price_change_pct,
        volume=stock_data.volume,
        peg_ratio=stock_data.peg_ratio,
        beta=stock_data.beta,
        pe_ratio=stock_data.pe_ratio,
        debt_to_equity=stock_data.debt_to_equity,
        market_cap=stock_data.market_cap,
        sector=stock_data.sector,
        fetched_at=stock_data.fetched_at,
        is_stale=stock_data.is_stale,
    ).on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "price": stock_data.price,
            "price_change_pct": stock_data.price_change_pct,
            "volume": stock_data.volume,
            "peg_ratio": stock_data.peg_ratio,
            "beta": stock_data.beta,
            "pe_ratio": stock_data.pe_ratio,
            "debt_to_equity": stock_data.debt_to_equity,
            "market_cap": stock_data.market_cap,
            "sector": stock_data.sector,
            "fetched_at": stock_data.fetched_at,
            "is_stale": False,
        },
    )
    await db.execute(stmt)


async def _upsert_stock_score(
    db: AsyncSession,
    user_id: str,
    ticker: str,
    breakdown: ScoreBreakdown,
    recommendation: Recommendation,
) -> None:
    now = datetime.now(tz=timezone.utc)
    stmt = pg_insert(StockScoreORM).values(
        id=uuid.uuid4(),
        user_id=user_id,
        ticker=ticker,
        risk_score=breakdown.final_score,
        recommendation=recommendation.value,
        breakdown=breakdown.model_dump(),
        computed_at=now,
    ).on_conflict_do_update(
        index_elements=["user_id", "ticker"],
        set_={
            "risk_score": breakdown.final_score,
            "recommendation": recommendation.value,
            "breakdown": breakdown.model_dump(),
            "computed_at": now,
        },
    )
    await db.execute(stmt)


async def _append_score_history(
    db: AsyncSession,
    user_id: str,
    ticker: str,
    breakdown: ScoreBreakdown,
    recommendation: Recommendation,
) -> None:
    now = datetime.now(tz=timezone.utc)
    history = StockScoreHistory(
        id=uuid.uuid4(),
        user_id=user_id,
        ticker=ticker,
        risk_score=breakdown.final_score,
        recommendation=recommendation.value,
        breakdown=breakdown.model_dump(),
        computed_at=now,
    )
    db.add(history)


async def _log_cycle_start(db: AsyncSession) -> uuid.UUID:
    log_id = uuid.uuid4()
    log = RefreshLog(
        id=log_id,
        started_at=datetime.now(tz=timezone.utc),
    )
    db.add(log)
    await db.commit()
    return log_id


async def _log_cycle_end(
    db: AsyncSession,
    log_id: uuid.UUID,
    stocks_updated: int,
    errors: dict,
) -> None:
    await db.execute(
        text(
            "UPDATE refresh_logs SET ended_at = :now, stocks_updated = :n, errors = :e "
            "WHERE id = :id"
        ),
        {
            "now": datetime.now(tz=timezone.utc),
            "n": stocks_updated,
            "e": errors or None,
            "id": str(log_id),
        },
    )
    await db.commit()
