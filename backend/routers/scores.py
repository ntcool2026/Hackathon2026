"""Scores router: read current scores, rationale, history, and price charts."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from backend.auth import get_current_user, get_or_create_user, require_auth
from backend.db import AsyncSession, get_db
from backend.models_orm import StockScore as StockScoreORM, StockScoreHistory

router = APIRouter(prefix="/api/scores", dependencies=[Depends(require_auth)])

_refresh_lock = asyncio.Lock()


@router.get("")
async def list_scores(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    result = await db.execute(
        select(StockScoreORM).where(StockScoreORM.user_id == user_id)
    )
    return [_format_score(s) for s in result.scalars().all()]


@router.post("/refresh")
async def trigger_refresh(user: dict = Depends(get_current_user)):
    """Manually trigger the data pipeline and LLM agent cycle."""
    from backend.agent import run_data_pipeline
    from backend.llm_agent import run_llm_agent_cycle

    # Guard against concurrent manual refreshes
    if _refresh_lock.locked():
        return {"status": "refresh already in progress"}

    async def _run():
        async with _refresh_lock:
            await run_data_pipeline()
            await run_llm_agent_cycle()

    asyncio.create_task(_run())
    return {"status": "refresh triggered"}


@router.get("/{ticker}/rationale")
async def get_rationale(
    ticker: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    score = await _get_score(db, user_id, ticker.upper())
    return {"ticker": ticker.upper(), "rationale": score.rationale, "rationale_at": score.rationale_at}


@router.get("/{ticker}/history")
async def get_score_history(
    ticker: str,
    limit: int = Query(default=30, ge=1, le=500),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    result = await db.execute(
        select(StockScoreHistory)
        .where(
            StockScoreHistory.user_id == user_id,
            StockScoreHistory.ticker == ticker.upper(),
        )
        .order_by(StockScoreHistory.computed_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "risk_score": float(r.risk_score),
            "recommendation": r.recommendation,
            "breakdown": r.breakdown,
            "computed_at": r.computed_at,
        }
        for r in rows
    ]


@router.get("/{ticker}/price-history")
async def get_price_history(
    ticker: str,
    period: str = Query(default="1y", pattern="^(1w|1y|2y)$"),
    user: dict = Depends(get_current_user),
):
    """Return OHLC close price history for charting. period: 1w | 1y | 2y"""
    from backend.adapters.yfinance_adapter import YFinanceAdapter
    adapter = YFinanceAdapter()
    data = await adapter.fetch_price_history(ticker.upper(), period)
    return {"ticker": ticker.upper(), "period": period, "data": data}


@router.get("/price-history/multi")
async def get_multi_price_history(
    tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT"),
    period: str = Query(default="2y", pattern="^(1w|1y|2y)$"),
    user: dict = Depends(get_current_user),
):
    """Return close price history for multiple tickers, normalised to % change from first point."""
    from backend.adapters.yfinance_adapter import YFinanceAdapter
    adapter = YFinanceAdapter()
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:10]

    results = await asyncio.gather(
        *[adapter.fetch_price_history(t, period) for t in ticker_list],
        return_exceptions=True,
    )

    series: dict[str, list[dict]] = {}
    for ticker, data in zip(ticker_list, results):
        if isinstance(data, Exception) or not data:
            series[ticker] = []
        else:
            base = data[0]["close"] if data else None
            series[ticker] = [
                {"date": p["date"], "pct": round((p["close"] / base - 1) * 100, 2) if base else 0}
                for p in data
            ]

    return {"period": period, "series": series}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# NOTE: This route is intentionally placed AFTER all /{ticker}/sub-path routes
# to avoid FastAPI matching "rationale", "history", etc. as the ticker param.
@router.get("/{ticker}")
async def get_score(
    ticker: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    score = await _get_score(db, user_id, ticker.upper())
    return _format_score(score)


async def _get_score(db: AsyncSession, user_id: str, ticker: str) -> StockScoreORM:
    result = await db.execute(
        select(StockScoreORM).where(
            StockScoreORM.user_id == user_id,
            StockScoreORM.ticker == ticker,
        )
    )
    score = result.scalar_one_or_none()
    if score is None:
        raise HTTPException(status_code=404, detail=f"No score found for ticker {ticker}")
    return score


def _format_score(s: StockScoreORM) -> dict:
    return {
        "ticker": s.ticker,
        "risk_score": float(s.risk_score),
        "recommendation": s.recommendation,
        "breakdown": s.breakdown,
        "rationale": s.rationale,
        "rationale_at": s.rationale_at,
        "ai_risk_score": float(s.ai_risk_score) if s.ai_risk_score is not None else None,
        "ai_recommendation": s.ai_recommendation,
        "computed_at": s.computed_at,
    }
