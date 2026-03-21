"""Custom criteria router: CRUD with rescore on change."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from backend.auth import get_current_user, get_or_create_user, require_auth
from backend.db import AsyncSession, get_db
from backend.models import CustomCriterionCreate
from backend.models_orm import CustomCriterion as CustomCriterionORM

router = APIRouter(prefix="/api/criteria", dependencies=[Depends(require_auth)])

_MAX_CRITERIA = 20


@router.get("")
async def list_criteria(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    result = await db.execute(
        select(CustomCriterionORM).where(CustomCriterionORM.user_id == user_id)
    )
    return [_format(c) for c in result.scalars().all()]


@router.post("", status_code=201)
async def create_criterion(
    body: CustomCriterionCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)

    count_result = await db.execute(
        select(func.count()).where(CustomCriterionORM.user_id == user_id)
    )
    if count_result.scalar_one() >= _MAX_CRITERIA:
        raise HTTPException(status_code=409, detail=f"Maximum of {_MAX_CRITERIA} criteria reached")

    criterion = CustomCriterionORM(
        id=uuid.uuid4(),
        user_id=user_id,
        name=body.name,
        description=body.description,
        weight=body.weight,
        metric=body.metric,
        operator=body.operator,
        threshold=body.threshold,
    )
    db.add(criterion)
    await db.commit()
    await db.refresh(criterion)

    asyncio.create_task(_trigger_rescore(user_id))
    return _format(criterion)


@router.put("/{criterion_id}")
async def update_criterion(
    criterion_id: uuid.UUID,
    body: CustomCriterionCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    criterion = await _get_criterion(db, criterion_id, user_id)

    criterion.name = body.name
    criterion.description = body.description
    criterion.weight = body.weight
    criterion.metric = body.metric
    criterion.operator = body.operator
    criterion.threshold = body.threshold
    await db.commit()
    await db.refresh(criterion)

    asyncio.create_task(_trigger_rescore(user_id))
    return _format(criterion)


@router.delete("/{criterion_id}", status_code=204)
async def delete_criterion(
    criterion_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    criterion = await _get_criterion(db, criterion_id, user_id)
    await db.delete(criterion)
    await db.commit()

    asyncio.create_task(_trigger_rescore(user_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_criterion(
    db: AsyncSession, criterion_id: uuid.UUID, user_id: str
) -> CustomCriterionORM:
    result = await db.execute(
        select(CustomCriterionORM).where(
            CustomCriterionORM.id == criterion_id,
            CustomCriterionORM.user_id == user_id,
        )
    )
    c = result.scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="Criterion not found")
    return c


def _format(c: CustomCriterionORM) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "description": c.description,
        "weight": c.weight,
        "metric": c.metric,
        "operator": c.operator,
        "threshold": str(c.threshold),
        "created_at": c.created_at,
    }


async def _trigger_rescore(user_id: str) -> None:
    """Re-run scoring for all user tickers after criteria change."""
    from backend.db import AsyncSessionLocal
    from backend.agent import _get_criteria, _get_preferences, _get_user_tickers, _upsert_stock_score
    from backend.models import StockData
    from backend.models_orm import StockData as StockDataORM
    from backend.scoring import compute_recommendation, compute_risk_score
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        prefs = await _get_preferences(db, user_id)
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
