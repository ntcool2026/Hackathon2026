"""Unit tests for the scoring engine."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.models import (
    CustomCriterion,
    GrowthVsValue,
    Recommendation,
    StockData,
    TimeHorizon,
    UserPreferences,
)
from backend.scoring import (
    SCORE_BUY_THRESHOLD,
    SCORE_SELL_THRESHOLD,
    compute_recommendation,
    compute_risk_score,
    evaluate_criterion,
    normalize_beta,
    normalize_peg,
    normalize_pe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.now(tz=timezone.utc)


def make_stock(
    ticker: str = "TEST",
    peg_ratio: float | None = 1.5,
    beta: float | None = 1.0,
    pe_ratio: float | None = 20.0,
    sector: str | None = "Information Technology",
) -> StockData:
    return StockData(
        ticker=ticker,
        peg_ratio=peg_ratio,
        beta=beta,
        pe_ratio=pe_ratio,
        sector=sector,
        fetched_at=NOW,
    )


def make_prefs(
    risk_tolerance: int = 5,
    time_horizon: TimeHorizon = TimeHorizon.MEDIUM,
    growth_vs_value: GrowthVsValue = GrowthVsValue.BALANCED,
) -> UserPreferences:
    return UserPreferences(
        risk_tolerance=risk_tolerance,
        time_horizon=time_horizon,
        growth_vs_value=growth_vs_value,
    )


def make_criterion(
    metric: str = "pe_ratio",
    operator: str = "gt",
    threshold: float = 30.0,
    weight: int = 5,
) -> CustomCriterion:
    return CustomCriterion(
        user_id="u1",
        name="test",
        metric=metric,
        operator=operator,
        threshold=Decimal(str(threshold)),
        weight=weight,
    )


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------


class TestNormalizePeg:
    def test_zero(self):
        assert normalize_peg(0.0) == 0.0

    def test_midpoint(self):
        assert normalize_peg(1.5) == pytest.approx(50.0)

    def test_at_max(self):
        assert normalize_peg(3.0) == 100.0

    def test_above_max_clamped(self):
        assert normalize_peg(10.0) == 100.0

    def test_negative_clamped(self):
        assert normalize_peg(-1.0) == 0.0


class TestNormalizeBeta:
    def test_zero(self):
        assert normalize_beta(0.0) == 0.0

    def test_one(self):
        assert normalize_beta(1.0) == pytest.approx(100 / 3)

    def test_at_max(self):
        assert normalize_beta(3.0) == 100.0

    def test_above_max_clamped(self):
        assert normalize_beta(5.0) == 100.0


class TestNormalizePe:
    def test_zero(self):
        assert normalize_pe(0.0) == 0.0

    def test_midpoint(self):
        assert normalize_pe(25.0) == pytest.approx(50.0)

    def test_at_max(self):
        assert normalize_pe(50.0) == 100.0

    def test_above_max_clamped(self):
        assert normalize_pe(200.0) == 100.0


# ---------------------------------------------------------------------------
# compute_recommendation
# ---------------------------------------------------------------------------


class TestComputeRecommendation:
    def test_buy_below_threshold(self):
        assert compute_recommendation(SCORE_BUY_THRESHOLD - 0.1) == Recommendation.BUY

    def test_buy_at_zero(self):
        assert compute_recommendation(0.0) == Recommendation.BUY

    def test_hold_at_buy_threshold(self):
        assert compute_recommendation(SCORE_BUY_THRESHOLD) == Recommendation.HOLD

    def test_hold_midrange(self):
        assert compute_recommendation(50.0) == Recommendation.HOLD

    def test_sell_at_sell_threshold(self):
        assert compute_recommendation(SCORE_SELL_THRESHOLD) == Recommendation.SELL

    def test_sell_at_100(self):
        assert compute_recommendation(100.0) == Recommendation.SELL


# ---------------------------------------------------------------------------
# evaluate_criterion
# ---------------------------------------------------------------------------


class TestEvaluateCriterion:
    def test_gt_true(self):
        stock = make_stock(pe_ratio=40.0)
        c = make_criterion(metric="pe_ratio", operator="gt", threshold=30.0)
        assert evaluate_criterion(stock, c) is True

    def test_gt_false(self):
        stock = make_stock(pe_ratio=20.0)
        c = make_criterion(metric="pe_ratio", operator="gt", threshold=30.0)
        assert evaluate_criterion(stock, c) is False

    def test_lt_true(self):
        stock = make_stock(beta=0.5)
        c = make_criterion(metric="beta", operator="lt", threshold=1.0)
        assert evaluate_criterion(stock, c) is True

    def test_gte_equal(self):
        stock = make_stock(pe_ratio=30.0)
        c = make_criterion(metric="pe_ratio", operator="gte", threshold=30.0)
        assert evaluate_criterion(stock, c) is True

    def test_lte_equal(self):
        stock = make_stock(pe_ratio=30.0)
        c = make_criterion(metric="pe_ratio", operator="lte", threshold=30.0)
        assert evaluate_criterion(stock, c) is True

    def test_eq_true(self):
        stock = make_stock(pe_ratio=25.0)
        c = make_criterion(metric="pe_ratio", operator="eq", threshold=25.0)
        assert evaluate_criterion(stock, c) is True

    def test_missing_metric_returns_false(self):
        stock = make_stock(beta=None)
        c = make_criterion(metric="beta", operator="gt", threshold=0.5)
        assert evaluate_criterion(stock, c) is False

    def test_nonexistent_metric_returns_false(self):
        stock = make_stock()
        c = make_criterion(metric="nonexistent_field", operator="gt", threshold=0.0)
        assert evaluate_criterion(stock, c) is False

    def test_invalid_operator_returns_false(self):
        stock = make_stock(pe_ratio=30.0)
        c = make_criterion(metric="pe_ratio", operator="gt", threshold=10.0)
        # Bypass validator to inject bad operator
        c = c.model_copy(update={"operator": "bad"})
        assert evaluate_criterion(stock, c) is False


# ---------------------------------------------------------------------------
# compute_risk_score
# ---------------------------------------------------------------------------


class TestComputeRiskScore:
    def test_output_in_range(self):
        bd = compute_risk_score(make_stock(), make_prefs(), [])
        assert 0.0 <= bd.final_score <= 100.0

    def test_all_fields_present(self):
        bd = compute_risk_score(make_stock(), make_prefs(), [])
        assert bd.peg_score >= 0
        assert bd.beta_score >= 0
        assert bd.pe_score >= 0
        assert bd.sector_score >= 0
        assert bd.recommendation is not None

    def test_missing_beta_and_pe_still_scores(self):
        stock = make_stock(beta=None, pe_ratio=None)
        bd = compute_risk_score(stock, make_prefs(), [])
        assert 0.0 <= bd.final_score <= 100.0
        # Only peg + sector weights should be active
        assert "beta" not in bd.weights
        assert "pe" not in bd.weights
        assert pytest.approx(sum(bd.weights.values()), abs=1e-9) == 1.0

    def test_weights_sum_to_one(self):
        bd = compute_risk_score(make_stock(), make_prefs(), [])
        assert pytest.approx(sum(bd.weights.values()), abs=1e-9) == 1.0

    def test_high_risk_stock_scores_higher(self):
        low_risk = make_stock(peg_ratio=0.5, beta=0.3, pe_ratio=10.0, sector="Utilities")
        high_risk = make_stock(peg_ratio=4.0, beta=2.5, pe_ratio=80.0, sector="Energy")
        prefs = make_prefs()
        low_bd = compute_risk_score(low_risk, prefs, [])
        high_bd = compute_risk_score(high_risk, prefs, [])
        assert high_bd.final_score > low_bd.final_score

    def test_high_risk_tolerance_lowers_score(self):
        stock = make_stock()
        low_tol = compute_risk_score(stock, make_prefs(risk_tolerance=1), [])
        high_tol = compute_risk_score(stock, make_prefs(risk_tolerance=10), [])
        assert high_tol.final_score < low_tol.final_score

    def test_long_horizon_lowers_score(self):
        stock = make_stock()
        short = compute_risk_score(stock, make_prefs(time_horizon=TimeHorizon.SHORT), [])
        long_ = compute_risk_score(stock, make_prefs(time_horizon=TimeHorizon.LONG), [])
        assert long_.final_score < short.final_score

    def test_criteria_increases_score(self):
        stock = make_stock(pe_ratio=40.0)
        no_criteria = compute_risk_score(stock, make_prefs(), [])
        criterion = make_criterion(metric="pe_ratio", operator="gt", threshold=30.0, weight=5)
        with_criteria = compute_risk_score(stock, make_prefs(), [criterion])
        assert with_criteria.final_score > no_criteria.final_score
        assert with_criteria.criteria_adjustment == pytest.approx(10.0)  # weight * 2

    def test_criteria_adjustment_capped_at_20(self):
        stock = make_stock(pe_ratio=100.0, beta=3.0)
        # 6 criteria each with weight=10 → would be 120 without cap
        criteria = [
            make_criterion(metric="pe_ratio", operator="gt", threshold=0.0, weight=10)
            for _ in range(6)
        ]
        bd = compute_risk_score(stock, make_prefs(), criteria)
        assert bd.criteria_adjustment == pytest.approx(20.0)

    def test_unmatched_criteria_no_adjustment(self):
        stock = make_stock(pe_ratio=10.0)
        criterion = make_criterion(metric="pe_ratio", operator="gt", threshold=50.0, weight=5)
        bd = compute_risk_score(stock, make_prefs(), [criterion])
        assert bd.criteria_adjustment == pytest.approx(0.0)

    def test_unknown_sector_uses_default(self):
        stock = make_stock(sector=None)
        bd = compute_risk_score(stock, make_prefs(), [])
        assert bd.sector_score == 50.0

    def test_final_score_never_exceeds_100(self):
        # Worst-case stock + criteria
        stock = make_stock(peg_ratio=10.0, beta=5.0, pe_ratio=200.0, sector="Energy")
        criteria = [make_criterion(metric="pe_ratio", operator="gt", threshold=0.0, weight=10) for _ in range(6)]
        bd = compute_risk_score(stock, make_prefs(risk_tolerance=1), criteria)
        assert bd.final_score <= 100.0

    def test_recommendation_consistent_with_final_score(self):
        stock = make_stock(peg_ratio=0.1, beta=0.1, pe_ratio=5.0, sector="Utilities")
        bd = compute_risk_score(stock, make_prefs(risk_tolerance=10), [])
        assert bd.recommendation == compute_recommendation(bd.final_score)
