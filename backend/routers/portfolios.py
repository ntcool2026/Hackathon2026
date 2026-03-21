"""Portfolios router: CRUD for user portfolios."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from backend.auth import get_current_user, get_or_create_user, require_auth
from backend.db import AsyncSession, get_db
from backend.models_orm import Portfolio, PortfolioStock

router = APIRouter(prefix="/api/portfolios", dependencies=[Depends(require_auth)])


class PortfolioCreate(BaseModel):
    name: str


@router.get("")
async def list_portfolios(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    )
    portfolios = result.scalars().all()
    return [
        {"id": str(p.id), "name": p.name, "created_at": p.created_at}
        for p in portfolios
    ]


@router.post("", status_code=201)
async def create_portfolio(
    body: PortfolioCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    portfolio = Portfolio(id=uuid.uuid4(), user_id=user_id, name=body.name)
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return {"id": str(portfolio.id), "name": portfolio.name, "created_at": portfolio.created_at}


@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_or_create_user(user, db)
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id, Portfolio.user_id == user_id
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    await db.delete(portfolio)
    await db.commit()
