"""Property-based tests for the scoring engine.

# Feature: stock-portfolio-advisor
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models import (
    CustomCriterion,
    GrowthVsValue,
    Recommendation,
    ScoreBreakdown,
    StockData,
    TimeHorizon,
    UserPreferences,
)
from backend.scoring import (
    SCORE_BUY_THRESHOLD,
    SCORE_SELL_THRESHOLD,
    compute_recommendation,
    compute_risk_score,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

NOW = datetime.now(tz=timezone.utc)

opt_positive_float = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)

SECTORS = [
    "Utilities", "Consumer Staples", "Healthcare", "Financials", "Industrials",
    "Real Estate", "Consumer Discretionary", "Communication Services",
    "Information Technology", "Materials", "Energy", None,
]

stock_strategy = st.builds(
    StockData,
    ticker=st.just("TEST"),
    peg_ratio=opt_positive_float,
    beta=opt_positive_float,
    pe_ratio=opt_positive_float,
    sector=st.sampled_from(SECTORS),
    fetched_at=st.just(NOW),
)

prefs_strategy = st.builds(
    UserPreferences,
    risk_tolerance=st.integers(min_value=1, max_value=10),
    time_horizon=st.sampled_from(list(TimeHorizon)),
    growth_vs_value=st.sampled_from(list(GrowthVsValue)),
)

criterion_strategy = st.builds(
    CustomCriterion,
    user_id=st.just("u1"),
    name=st.text(min_size=1, max_size=20),
    weight=st.integers(min_value=1, max_value=10),
    metric=st.sampled_from(["pe_ratio", "beta", "peg_ratio", "debt_to_equity"]),
    operator=st.sampled_from(["gt", "lt", "gte", "lte", "eq"]),
    threshold=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False).map(
        lambda f: Decimal(str(round(f, 4)))
    ),
)


# ---------------------------------------------------------------------------
# Property 7: Risk score is sensitive to its inputs
# Validates: Requirements 3.1, 3.2
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(prefs=prefs_strategy)
def test_risk_score_sensitive_to_inputs(prefs: UserPreferences) -> None:
    """Property 7: Risk score is sensitive to its inputs.

    A high-risk stock (high PEG, high beta, high P/E, risky sector) SHALL
    produce a strictly higher final_score than a low-risk stock under the
    same preferences.

    Validates: Requirements 3.1, 3.2
    """
    # Feature: stock-portfolio-advisor, Property 7: Risk score is sensitive to its inputs
    low_risk = StockData(
        ticker="LOW", peg_ratio=0.1, beta=0.1, pe_ratio=5.0,
        sector="Utilities", fetched_at=NOW,
    )
    high_risk = StockData(
        ticker="HIGH", peg_ratio=3.0, beta=3.0, pe_ratio=50.0,
        sector="Energy", fetched_at=NOW,
    )
    low_bd = compute_risk_score(low_risk, prefs, [])
    high_bd = compute_risk_score(high_risk, prefs, [])
    assert high_bd.final_score > low_bd.final_score


# ---------------------------------------------------------------------------
# Property 8: Recommendation is deterministic given risk score and preferences
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(stock=stock_strategy, prefs=prefs_strategy)
def test_recommendation_is_deterministic(stock: StockData, prefs: UserPreferences) -> None:
    """Property 8: Recommendation is deterministic given risk score and preferences.

    Calling compute_risk_score twice with identical inputs SHALL produce
    identical final_score and recommendation values.

    Validates: Requirements 3.3
    """
    # Feature: stock-portfolio-advisor, Property 8: Recommendation is deterministic given risk score and preferences
    bd1 = compute_risk_score(stock, prefs, [])
    bd2 = compute_risk_score(stock, prefs, [])
    assert bd1.final_score == bd2.final_score
    assert bd1.recommendation == bd2.recommendation


# ---------------------------------------------------------------------------
# Property 31: ScoreBreakdown contains all normalized component scores
# Validates: Requirements 3.6
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(stock=stock_strategy, prefs=prefs_strategy)
def test_score_breakdown_components_in_range(stock: StockData, prefs: UserPreferences) -> None:
    """Property 31: ScoreBreakdown contains all normalized component scores.

    All component scores (peg_score, beta_score, pe_score, sector_score) SHALL
    be in [0, 100], weights SHALL sum to 1.0, and final_score SHALL be in [0, 100].

    Validates: Requirements 3.6
    """
    # Feature: stock-portfolio-advisor, Property 31: ScoreBreakdown contains all normalized component scores
    bd = compute_risk_score(stock, prefs, [])

    assert 0.0 <= bd.peg_score <= 100.0
    assert 0.0 <= bd.beta_score <= 100.0
    assert 0.0 <= bd.pe_score <= 100.0
    assert 0.0 <= bd.sector_score <= 100.0
    assert 0.0 <= bd.final_score <= 100.0
    assert pytest.approx(sum(bd.weights.values()), abs=1e-6) == 1.0
    assert bd.recommendation is not None


# ---------------------------------------------------------------------------
# Property 32: Recommendation thresholds are respected for all scores
# Validates: Requirements 3.7
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_recommendation_thresholds_respected(score: float) -> None:
    """Property 32: Recommendation thresholds are respected for all scores.

    For any score in [0, 100]:
    - score < BUY_THRESHOLD  → BUY
    - score >= SELL_THRESHOLD → SELL
    - otherwise              → HOLD

    Validates: Requirements 3.7
    """
    # Feature: stock-portfolio-advisor, Property 32: Recommendation thresholds are respected for all scores
    rec = compute_recommendation(score)
    if score < SCORE_BUY_THRESHOLD:
        assert rec == Recommendation.BUY
    elif score >= SCORE_SELL_THRESHOLD:
        assert rec == Recommendation.SELL
    else:
        assert rec == Recommendation.HOLD
