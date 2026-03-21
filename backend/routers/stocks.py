"""Stocks router: add/remove stocks from portfolios with immediate scoring."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.adapters.yfinance_adapter import YFinanceAdapter
from backend.agent import _get_criteria, _get_preferences, _upsert_stock_data, _upsert_stock_score
from backend.auth import get_current_user, get_or_create_user, require_auth
from backend.db import AsyncSession, get_db
from backend.limiter import limiter
from backend.models_orm import Portfolio, PortfolioStock, StockScore as StockScoreORM
from backend.scoring import compute_recommendation, compute_risk_score

router = APIRouter(prefix="/api/portfolios", dependencies=[Depends(require_auth)])

_yfinance = YFinanceAdapter()

_MAX_STOCKS_PER_PORTFOLIO = 100


class AddStockBody(BaseModel):
    ticker: str


@router.get("/{portfolio_id}/stocks")
async def list_stocks(
    portfolio_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    portfolio = await _get_portfolio(db, portfolio_id, user_id)

    result = await db.execute(
        select(PortfolioStock).where(PortfolioStock.portfolio_id == portfolio_id)
    )
    stocks = result.scalars().all()

    # Attach scores
    tickers = [s.ticker for s in stocks]
    scores_result = await db.execute(
        select(StockScoreORM).where(
            StockScoreORM.user_id == user_id,
            StockScoreORM.ticker.in_(tickers),
        )
    )
    score_map = {s.ticker: s for s in scores_result.scalars().all()}

    # Attach latest prices from stock_data
    from backend.models_orm import StockData as StockDataORM
    prices_result = await db.execute(
        select(StockDataORM.ticker, StockDataORM.price, StockDataORM.price_change_pct).where(StockDataORM.ticker.in_(tickers))
    )
    price_map = {
        row[0]: {
            "price": float(row[1]) if row[1] is not None else None,
            "price_change_pct": float(row[2]) if row[2] is not None else None,
        }
        for row in prices_result.all()
    }

    return [
        {
            "ticker": s.ticker,
            "added_at": s.added_at,
            "price": price_map.get(s.ticker, {}).get("price"),
            "price_change_pct": price_map.get(s.ticker, {}).get("price_change_pct"),
            "score": _format_score(score_map.get(s.ticker)),
        }
        for s in stocks
    ]


@router.post("/{portfolio_id}/stocks", status_code=201)
@limiter.limit("10/minute")
async def add_stock(
    request: Request,
    portfolio_id: uuid.UUID,
    body: AddStockBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    portfolio = await _get_portfolio(db, portfolio_id, user_id)

    # Enforce 100-stock limit
    count_result = await db.execute(
        select(func.count()).where(PortfolioStock.portfolio_id == portfolio_id)
    )
    count = count_result.scalar_one()
    if count >= _MAX_STOCKS_PER_PORTFOLIO:
        raise HTTPException(
            status_code=409,
            detail=f"Portfolio already has {_MAX_STOCKS_PER_PORTFOLIO} stocks (limit reached)",
        )

    ticker = body.ticker.upper().strip()

    # Validate ticker via yfinance
    try:
        stock_data = await _yfinance.fetch_stock_data(ticker)
        if stock_data.price is None:
            raise ValueError("no price data")
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid or unknown ticker: {ticker}")

    # Add to portfolio (ignore duplicate)
    stmt = pg_insert(PortfolioStock).values(
        id=uuid.uuid4(),
        portfolio_id=portfolio_id,
        ticker=ticker,
        added_at=datetime.now(tz=timezone.utc),
    ).on_conflict_do_nothing(index_elements=["portfolio_id", "ticker"])
    await db.execute(stmt)

    # Upsert stock data
    await _upsert_stock_data(db, stock_data)

    # Compute and persist initial score
    prefs = await _get_preferences(db, user_id)
    criteria = await _get_criteria(db, user_id)
    breakdown = compute_risk_score(stock_data, prefs, criteria)
    recommendation = compute_recommendation(breakdown.final_score)
    await _upsert_stock_score(db, user_id, ticker, breakdown, recommendation)

    await db.commit()
    return {"ticker": ticker, "risk_score": breakdown.final_score, "recommendation": recommendation.value}


@router.delete("/{portfolio_id}/stocks/{ticker}", status_code=204)
async def remove_stock(
    portfolio_id: uuid.UUID,
    ticker: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    portfolio = await _get_portfolio(db, portfolio_id, user_id)

    ticker = ticker.upper()
    result = await db.execute(
        select(PortfolioStock).where(
            PortfolioStock.portfolio_id == portfolio_id,
            PortfolioStock.ticker == ticker,
        )
    )
    stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found in portfolio")

    await db.delete(stock)

    # Remove score for this user+ticker if no other portfolio has it
    other = await db.execute(
        select(PortfolioStock)
        .join(Portfolio, Portfolio.id == PortfolioStock.portfolio_id)
        .where(
            Portfolio.user_id == user_id,
            PortfolioStock.ticker == ticker,
            PortfolioStock.portfolio_id != portfolio_id,
        )
    )
    if other.scalar_one_or_none() is None:
        score_result = await db.execute(
            select(StockScoreORM).where(
                StockScoreORM.user_id == user_id,
                StockScoreORM.ticker == ticker,
            )
        )
        score = score_result.scalar_one_or_none()
        if score:
            await db.delete(score)

    await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_portfolio(db: AsyncSession, portfolio_id: uuid.UUID, user_id: str) -> Portfolio:
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id, Portfolio.user_id == user_id
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


def _format_score(score: StockScoreORM | None) -> dict | None:
    if score is None:
        return None
    return {
        "risk_score": float(score.risk_score),
        "recommendation": score.recommendation,
        "breakdown": score.breakdown,
        "rationale": score.rationale,
        "rationale_at": score.rationale_at,
        "ai_risk_score": float(score.ai_risk_score) if score.ai_risk_score is not None else None,
        "ai_recommendation": score.ai_recommendation,
        "computed_at": score.computed_at,
    }
