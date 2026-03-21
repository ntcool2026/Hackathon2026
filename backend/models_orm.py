"""SQLAlchemy 2.x ORM models for all database tables."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    portfolios: Mapped[list[Portfolio]] = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
    preferences: Mapped[Optional[UserPreferences]] = relationship(
        "UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    custom_criteria: Mapped[list[CustomCriterion]] = relationship(
        "CustomCriterion", back_populates="user", cascade="all, delete-orphan"
    )
    stock_scores: Mapped[list[StockScore]] = relationship(
        "StockScore", back_populates="user", cascade="all, delete-orphan"
    )
    user_thresholds: Mapped[list[UserThreshold]] = relationship(
        "UserThreshold", back_populates="user", cascade="all, delete-orphan"
    )
    score_history: Mapped[list[StockScoreHistory]] = relationship(
        "StockScoreHistory", back_populates="user", cascade="all, delete-orphan"
    )


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    user: Mapped[User] = relationship("User", back_populates="portfolios")
    stocks: Mapped[list[PortfolioStock]] = relationship(
        "PortfolioStock", back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioStock(Base):
    __tablename__ = "portfolio_stocks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="stocks")


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    risk_tolerance: Mapped[int] = mapped_column(SmallInteger, server_default="5", nullable=False)
    time_horizon: Mapped[str] = mapped_column(Text, server_default="medium", nullable=False)
    sector_preference: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    dividend_preference: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    growth_vs_value: Mapped[str] = mapped_column(Text, server_default="balanced", nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    user: Mapped[User] = relationship("User", back_populates="preferences")


class CustomCriterion(Base):
    __tablename__ = "custom_criteria"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weight: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    user: Mapped[User] = relationship("User", back_populates="custom_criteria")


class StockData(Base):
    __tablename__ = "stock_data"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    price_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    peg_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    beta: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    debt_to_equity: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    market_cap: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)


class StockScore(Base):
    __tablename__ = "stock_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    breakdown: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rationale_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    ai_risk_score: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    ai_recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="stock_scores")


class UserThreshold(Base):
    __tablename__ = "user_thresholds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True
    )

    user: Mapped[User] = relationship("User", back_populates="user_thresholds")


class StockScoreHistory(Base):
    __tablename__ = "stock_score_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    breakdown: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="score_history")


class RefreshLog(Base):
    __tablename__ = "refresh_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    stocks_updated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    errors: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
