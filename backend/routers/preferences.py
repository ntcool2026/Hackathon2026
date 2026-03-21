"""Preferences router: read/update user preferences with live rescore."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.agent import _get_criteria, _get_user_tickers, _upsert_stock_score
from backend.auth import get_current_user, get_or_create_user, require_auth
from backend.db import AsyncSession, get_db
from backend.main import limiter
from backend.models import UserPreferences, UserPreferencesUpdate
from backend.models_orm import (
    StockData as StockDataORM,
    UserPreferences as UserPreferencesORM,
)
from backend.scoring import compute_recommendation, compute_risk_score

router = APIRouter(prefix="/api/preferences", dependencies=[Depends(require_auth)])


@router.get("")
async def get_preferences(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    result = await db.execute(
        select(UserPreferencesORM).where(UserPreferencesORM.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return UserPreferences().model_dump()
    return {
        "risk_tolerance": row.risk_tolerance,
        "time_horizon": row.time_horizon,
        "sector_preference": row.sector_preference or [],
        "dividend_preference": row.dividend_preference,
        "growth_vs_value": row.growth_vs_value,
        "updated_at": row.updated_at,
    }


@router.put("")
@limiter.limit("20/minute")
async def update_preferences(
    request: Request,
    body: UserPreferencesUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    now = datetime.now(tz=timezone.utc)

    stmt = pg_insert(UserPreferencesORM).values(
        user_id=user_id,
        risk_tolerance=body.risk_tolerance,
        time_horizon=body.time_horizon.value,
        sector_preference=body.sector_preference,
        dividend_preference=body.dividend_preference,
        growth_vs_value=body.growth_vs_value.value,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=["user_id"],
        set_={
            "risk_tolerance": body.risk_tolerance,
            "time_horizon": body.time_horizon.value,
            "sector_preference": body.sector_preference,
            "dividend_preference": body.dividend_preference,
            "growth_vs_value": body.growth_vs_value.value,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    await db.commit()

    # Trigger rescore asynchronously (fire-and-forget, within 5s)
    asyncio.create_task(_rescore_user(user_id, body))

    return {"status": "updated"}


@router.get("/preview")
async def preview_preferences(
    risk_tolerance: int = 5,
    time_horizon: str = "medium",
    sector_preference: str = "",
    dividend_preference: bool = False,
    growth_vs_value: str = "balanced",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return hypothetical scores for the given preferences without saving."""
    from backend.models import GrowthVsValue, TimeHorizon

    user_id = await get_or_create_user(user, db)
    prefs = UserPreferences(
        risk_tolerance=risk_tolerance,
        time_horizon=TimeHorizon(time_horizon),
        sector_preference=[s for s in sector_preference.split(",") if s],
        dividend_preference=dividend_preference,
        growth_vs_value=GrowthVsValue(growth_vs_value),
    )
    criteria = await _get_criteria(db, user_id)
    tickers = await _get_user_tickers(db, user_id)

    previews = []
    for ticker in tickers:
        result = await db.execute(
            select(StockDataORM).where(StockDataORM.ticker == ticker)
        )
        row = result.scalar_one_or_none()
        if row is None:
            continue
        from backend.models import StockData
        stock_data = StockData(
            ticker=row.ticker,
            price=float(row.price) if row.price else None,
            volume=int(row.volume) if row.volume else None,
            volatility=float(row.volatility) if row.volatility else None,
            beta=float(row.beta) if row.beta else None,
            pe_ratio=float(row.pe_ratio) if row.pe_ratio else None,
            debt_to_equity=float(row.debt_to_equity) if row.debt_to_equity else None,
            market_cap=int(row.market_cap) if row.market_cap else None,
            sector=row.sector,
            fetched_at=row.fetched_at,
            is_stale=row.is_stale,
        )
        breakdown = compute_risk_score(stock_data, prefs, criteria)
        recommendation = compute_recommendation(breakdown.final_score)
        previews.append({
            "ticker": ticker,
            "risk_score": breakdown.final_score,
            "recommendation": recommendation.value,
            "breakdown": breakdown.model_dump(),
        })

    return {"previews": previews}


# ---------------------------------------------------------------------------
# Background rescore
# ---------------------------------------------------------------------------


async def _rescore_user(user_id: str, prefs: UserPreferences) -> None:
    """Rescore all tickers for a user after preference update (fire-and-forget)."""
    from backend.db import AsyncSessionLocal
    from backend.models import StockData

    async with AsyncSessionLocal() as db:
        criteria = await _get_criteria(db, user_id)
        tickers = await _get_user_tickers(db, user_id)

        for ticker in tickers:
            result = await db.execute(
                select(StockDataORM).where(StockDataORM.ticker == ticker)
            )
            row = result.scalar_one_or_none()
            if row is None:
                continue
            stock_data = StockData(
                ticker=row.ticker,
                price=float(row.price) if row.price else None,
                volume=int(row.volume) if row.volume else None,
                volatility=float(row.volatility) if row.volatility else None,
                beta=float(row.beta) if row.beta else None,
                pe_ratio=float(row.pe_ratio) if row.pe_ratio else None,
                debt_to_equity=float(row.debt_to_equity) if row.debt_to_equity else None,
                market_cap=int(row.market_cap) if row.market_cap else None,
                sector=row.sector,
                fetched_at=row.fetched_at,
                is_stale=row.is_stale,
            )
            breakdown = compute_risk_score(stock_data, prefs, criteria)
            recommendation = compute_recommendation(breakdown.final_score)
            await _upsert_stock_score(db, user_id, ticker, breakdown, recommendation)

        await db.commit()
