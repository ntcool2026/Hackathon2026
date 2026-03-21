"""Scores router: read current scores, rationale, and history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from backend.auth import get_current_user, get_or_create_user, require_auth
from backend.db import AsyncSession, get_db
from backend.models_orm import StockScore as StockScoreORM, StockScoreHistory

router = APIRouter(prefix="/api/scores", dependencies=[Depends(require_auth)])


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


@router.get("/{ticker}")
async def get_score(
    ticker: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    score = await _get_score(db, user_id, ticker.upper())
    return _format_score(score)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        "computed_at": s.computed_at,
    }
