"""Thresholds router: per-user per-ticker alert thresholds."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.auth import get_current_user, get_or_create_user, require_auth
from backend.db import AsyncSession, get_db
from backend.models import UserThresholdCreate
from backend.models_orm import UserThreshold as UserThresholdORM

router = APIRouter(prefix="/api/thresholds", dependencies=[Depends(require_auth)])


@router.get("")
async def list_thresholds(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    result = await db.execute(
        select(UserThresholdORM).where(UserThresholdORM.user_id == user_id)
    )
    return [
        {"id": str(t.id), "ticker": t.ticker, "threshold": float(t.threshold), "created_at": t.created_at}
        for t in result.scalars().all()
    ]


@router.post("", status_code=201)
async def upsert_threshold(
    body: UserThresholdCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    ticker = body.ticker.upper()

    stmt = pg_insert(UserThresholdORM).values(
        id=uuid.uuid4(),
        user_id=user_id,
        ticker=ticker,
        threshold=body.threshold,
    ).on_conflict_do_update(
        index_elements=["user_id", "ticker"],
        set_={"threshold": body.threshold},
    )
    await db.execute(stmt)
    await db.commit()
    return {"ticker": ticker, "threshold": body.threshold}


@router.delete("/{ticker}", status_code=204)
async def delete_threshold(
    ticker: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    result = await db.execute(
        select(UserThresholdORM).where(
            UserThresholdORM.user_id == user_id,
            UserThresholdORM.ticker == ticker.upper(),
        )
    )
    threshold = result.scalar_one_or_none()
    if threshold is None:
        raise HTTPException(status_code=404, detail=f"No threshold found for ticker {ticker.upper()}")
    await db.delete(threshold)
    await db.commit()
