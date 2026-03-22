"""Pure-function scoring engine: risk score computation and recommendation logic."""
from __future__ import annotations

import os

from backend.models import (
    CustomCriterion,
    Recommendation,
    ScoreBreakdown,
    StockData,
    UserPreferences,
)

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------

SCORE_BUY_THRESHOLD: float = float(os.getenv("SCORE_BUY_THRESHOLD", "35"))
SCORE_SELL_THRESHOLD: float = float(os.getenv("SCORE_SELL_THRESHOLD", "65"))

# ---------------------------------------------------------------------------
# Sector risk weights (0–100)
# ---------------------------------------------------------------------------

SECTOR_RISK_WEIGHTS: dict[str, float] = {
    "Utilities": 20,
    "Consumer Staples": 25,
    "Healthcare": 35,
    "Financials": 50,
    "Industrials": 50,
    "Real Estate": 55,
    "Consumer Discretionary": 60,
    "Communication Services": 60,
    "Information Technology": 65,
    "Materials": 65,
    "Energy": 75,
    "Unknown": 50,  # default when sector is None
}

# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def normalize_peg(peg: float) -> float:
    """PEG ratio → 0–100 (0 → 0, ≥3.0 → 100). Higher PEG = more risk."""
    return min(max((peg / 3.0) * 100.0, 0.0), 100.0)


def normalize_beta(b: float) -> float:
    """Beta → 0–100 (0 → 0, ≥3.0 → 100)."""
    return min(max((b / 3.0) * 100.0, 0.0), 100.0)


def normalize_pe(pe: float) -> float:
    """P/E ratio → 0–100 (0 → 0, ≥50 → 100). Higher P/E = more risk."""
    return min(max((pe / 50.0) * 100.0, 0.0), 100.0)


# ---------------------------------------------------------------------------
# Criterion evaluation
# ---------------------------------------------------------------------------

_OPERATORS = {
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
}


def evaluate_criterion(stock_data: StockData, criterion: CustomCriterion) -> bool:
    """Return True if the criterion condition is met for the given stock data."""
    value = getattr(stock_data, criterion.metric, None)
    if value is None:
        return False
    op = _OPERATORS.get(criterion.operator)
    if op is None:
        return False
    try:
        threshold = float(criterion.threshold)
        return op(float(value), threshold)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def compute_risk_score(
    stock_data: StockData,
    prefs: UserPreferences,
    criteria: list[CustomCriterion],
) -> ScoreBreakdown:
    """Compute a full ScoreBreakdown for a stock given user preferences and criteria."""

    # --- Component scores ---
    peg_score = normalize_peg(stock_data.peg_ratio or 0.0)
    beta_score = normalize_beta(stock_data.beta or 0.0) if stock_data.beta is not None else None
    pe_score = normalize_pe(float(stock_data.pe_ratio)) if stock_data.pe_ratio is not None else None
    sector_key = stock_data.sector or "Unknown"
    sector_score = float(SECTOR_RISK_WEIGHTS.get(sector_key, SECTOR_RISK_WEIGHTS["Unknown"]))

    # --- Weight renormalization for missing inputs ---
    base_weights: dict[str, float] = {
        "peg": 0.30,
        "beta": 0.25,
        "pe": 0.25,
        "sector": 0.20,
    }
    active: dict[str, float] = {"peg": peg_score, "sector": sector_score}
    if beta_score is not None:
        active["beta"] = beta_score
    if pe_score is not None:
        active["pe"] = pe_score

    raw_weight_sum = sum(base_weights[k] for k in active)
    weights_used: dict[str, float] = {
        k: base_weights[k] / raw_weight_sum for k in active
    }

    base_score = sum(active[k] * weights_used[k] for k in active)

    # --- Preference multipliers ---
    tolerance_multiplier = 1.0 + (5 - prefs.risk_tolerance) * 0.05  # 0.75–1.25
    horizon_multiplier = {"short": 1.10, "medium": 1.00, "long": 0.90}[prefs.time_horizon.value]
    gv_multiplier = {"growth": 0.95, "balanced": 1.00, "value": 1.05}[prefs.growth_vs_value.value]
    preference_adjustment = tolerance_multiplier * horizon_multiplier * gv_multiplier

    adjusted_score = min(max(base_score * preference_adjustment, 0.0), 100.0)

    # --- Custom criteria adjustment ---
    criteria_adjustment = min(
        sum(
            criterion.weight * 2
            for criterion in criteria
            if evaluate_criterion(stock_data, criterion)
        ),
        20,
    )

    final_score = min(adjusted_score + criteria_adjustment, 100.0)

    recommendation = compute_recommendation(final_score)

    return ScoreBreakdown(
        peg_score=peg_score,
        beta_score=beta_score if beta_score is not None else 0.0,
        pe_score=pe_score if pe_score is not None else 0.0,
        sector_score=sector_score,
        weights=weights_used,
        base_score=base_score,
        preference_adjustment=preference_adjustment,
        criteria_adjustment=float(criteria_adjustment),
        final_score=final_score,
        recommendation=recommendation,
    )


def compute_recommendation(score: float) -> Recommendation:
    """Map a final risk score to a BUY / HOLD / SELL recommendation."""
    if score < SCORE_BUY_THRESHOLD:
        return Recommendation.BUY
    elif score >= SCORE_SELL_THRESHOLD:
        return Recommendation.SELL
    return Recommendation.HOLD
