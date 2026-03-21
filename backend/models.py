"""Pydantic models and shared types for the Stock Portfolio Advisor."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Recommendation(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class TimeHorizon(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class GrowthVsValue(str, Enum):
    GROWTH = "growth"
    VALUE = "value"
    BALANCED = "balanced"


# ---------------------------------------------------------------------------
# Stock data
# ---------------------------------------------------------------------------

class StockData(BaseModel):
    ticker: str
    price: Optional[float] = None
    price_change_pct: Optional[float] = None
    volume: Optional[int] = None
    peg_ratio: Optional[float] = None
    beta: Optional[float] = None
    pe_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None  # kept for custom criteria
    market_cap: Optional[int] = None
    sector: Optional[str] = None
    fetched_at: datetime
    is_stale: bool = False


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class ScoreBreakdown(BaseModel):
    """Normalized component scores (0–100 each), weights, and final outputs."""
    # Component scores
    peg_score: float = Field(..., ge=0, le=100)
    beta_score: float = Field(0.0, ge=0, le=100)
    pe_score: float = Field(0.0, ge=0, le=100)
    sector_score: float = Field(..., ge=0, le=100)
    # Effective weights after renormalization
    weights: dict[str, float]
    # Intermediate values
    base_score: float = Field(0.0, ge=0, le=100)
    preference_adjustment: float = 1.0
    criteria_adjustment: float = Field(0.0, ge=0, le=20)
    # Final outputs
    final_score: float = Field(0.0, ge=0, le=100)
    recommendation: Optional["Recommendation"] = None


class StockScore(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: str
    ticker: str
    risk_score: float = Field(..., ge=0, le=100)
    recommendation: Recommendation
    breakdown: Optional[ScoreBreakdown] = None
    rationale: Optional[str] = None
    rationale_at: Optional[datetime] = None
    computed_at: datetime


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------

class UserPreferences(BaseModel):
    risk_tolerance: int = Field(5, ge=1, le=10)
    time_horizon: TimeHorizon = TimeHorizon.MEDIUM
    sector_preference: list[str] = Field(default_factory=list)
    dividend_preference: bool = False
    growth_vs_value: GrowthVsValue = GrowthVsValue.BALANCED


class UserPreferencesUpdate(UserPreferences):
    """Same as UserPreferences but all fields required for PUT."""
    risk_tolerance: int = Field(..., ge=1, le=10)
    time_horizon: TimeHorizon
    growth_vs_value: GrowthVsValue


# ---------------------------------------------------------------------------
# Custom criteria
# ---------------------------------------------------------------------------

class CustomCriterion(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: str
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    weight: int = Field(..., ge=1, le=10)
    metric: str
    operator: str  # "gt", "lt", "gte", "lte", "eq"
    threshold: Decimal

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        allowed = {"gt", "lt", "gte", "lte", "eq"}
        if v not in allowed:
            raise ValueError(f"operator must be one of {allowed}")
        return v


class CustomCriterionCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    weight: int = Field(..., ge=1, le=10)
    metric: str
    operator: str
    threshold: Decimal

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        allowed = {"gt", "lt", "gte", "lte", "eq"}
        if v not in allowed:
            raise ValueError(f"operator must be one of {allowed}")
        return v


# ---------------------------------------------------------------------------
# News / earnings / SEC
# ---------------------------------------------------------------------------

class NewsSentiment(BaseModel):
    ticker: str
    sentiment: float = Field(..., ge=-1.0, le=1.0)  # -1 negative, +1 positive
    headline_summary: str
    article_count: int = Field(..., ge=0)
    fetched_at: datetime


class EarningsData(BaseModel):
    ticker: str
    eps_actual: Optional[float] = None
    eps_estimate: Optional[float] = None
    surprise_pct: Optional[float] = None
    report_date: Optional[datetime] = None
    fetched_at: datetime


class SECFiling(BaseModel):
    ticker: str
    cik: str
    form_type: str  # "10-K", "10-Q", "8-K"
    filed_at: Optional[datetime] = None
    description: Optional[str] = None  # truncated to 1000 chars
    url: Optional[str] = None


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

class UserThreshold(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: str
    ticker: str
    threshold: float = Field(..., ge=0, le=100)


class UserThresholdCreate(BaseModel):
    ticker: str
    threshold: float = Field(..., ge=0, le=100)


# ---------------------------------------------------------------------------
# WebSocket events
# ---------------------------------------------------------------------------

class WSEvent(BaseModel):
    event: str  # "score_update" | "rationale_update" | "threshold_alert" | "data_stale"
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    answer: str


# ---------------------------------------------------------------------------
# Portfolio analysis
# ---------------------------------------------------------------------------

class PortfolioAnalysisResult(BaseModel):
    summary: str = Field(..., max_length=500)
    concentration_flags: list[str] = Field(default_factory=list)
