"""Unit tests for the LLM response parser."""
from __future__ import annotations

import pytest

from backend.llm_agent import _parse_llm_response


class TestParseStructuredFormat:
    """Model returns the expected structured format."""

    def test_clean_structured_response(self):
        raw = "AI_RISK_SCORE: 42\nAI_RECOMMENDATION: HOLD\nRATIONALE: Stock looks fairly valued."
        rationale, score, rec = _parse_llm_response(raw)
        assert score == pytest.approx(42.0)
        assert rec == "HOLD"
        assert "fairly valued" in rationale

    def test_buy_recommendation(self):
        raw = "AI_RISK_SCORE: 20\nAI_RECOMMENDATION: BUY\nRATIONALE: Strong growth prospects."
        _, score, rec = _parse_llm_response(raw)
        assert score == pytest.approx(20.0)
        assert rec == "BUY"

    def test_sell_recommendation(self):
        raw = "AI_RISK_SCORE: 80\nAI_RECOMMENDATION: SELL\nRATIONALE: High debt and slowing growth."
        _, score, rec = _parse_llm_response(raw)
        assert score == pytest.approx(80.0)
        assert rec == "SELL"

    def test_decimal_score(self):
        raw = "AI_RISK_SCORE: 57.5\nAI_RECOMMENDATION: HOLD\nRATIONALE: Mixed signals."
        _, score, _ = _parse_llm_response(raw)
        assert score == pytest.approx(57.5)

    def test_score_clamped_above_100(self):
        raw = "AI_RISK_SCORE: 150\nAI_RECOMMENDATION: SELL\nRATIONALE: Extreme risk."
        _, score, _ = _parse_llm_response(raw)
        assert score == pytest.approx(100.0)

    def test_score_clamped_below_0(self):
        raw = "AI_RISK_SCORE: -10\nAI_RECOMMENDATION: BUY\nRATIONALE: Very safe."
        _, score, _ = _parse_llm_response(raw)
        assert score == pytest.approx(0.0)

    def test_case_insensitive_keys(self):
        raw = "ai_risk_score: 55\nai_recommendation: hold\nrationale: Neutral outlook."
        _, score, rec = _parse_llm_response(raw)
        assert score == pytest.approx(55.0)
        assert rec == "HOLD"

    def test_extra_whitespace_around_colon(self):
        raw = "AI_RISK_SCORE :  63\nAI_RECOMMENDATION :  SELL\nRATIONALE: Overvalued."
        _, score, rec = _parse_llm_response(raw)
        assert score == pytest.approx(63.0)
        assert rec == "SELL"

    def test_structured_response_with_preamble(self):
        """Model outputs thinking text before the structured block."""
        raw = (
            "First, I need to analyze the stock carefully.\n"
            "Looking at the data provided...\n"
            "AI_RISK_SCORE: 45\n"
            "AI_RECOMMENDATION: HOLD\n"
            "RATIONALE: Moderate risk based on mixed signals."
        )
        _, score, rec = _parse_llm_response(raw)
        assert score == pytest.approx(45.0)
        assert rec == "HOLD"


class TestParseFallbackExtraction:
    """Model returns free-form text without structured keys."""

    def test_score_from_x_out_of_100(self):
        raw = "Based on my analysis, I would give this stock a risk score of 60 out of 100."
        _, score, _ = _parse_llm_response(raw)
        assert score == pytest.approx(60.0)

    def test_score_from_slash_notation(self):
        raw = "The overall risk is 72/100 given the high debt levels."
        _, score, _ = _parse_llm_response(raw)
        assert score == pytest.approx(72.0)

    def test_recommendation_from_conclusion(self):
        raw = "After reviewing all signals, my recommendation is: SELL due to high valuation."
        _, _, rec = _parse_llm_response(raw)
        assert rec == "SELL"

    def test_recommendation_from_frequency_count(self):
        """Falls back to most-frequent BUY/HOLD/SELL mention."""
        raw = "BUY signals are strong. BUY the dip. BUY now. SELL is not advised. HOLD is possible."
        _, _, rec = _parse_llm_response(raw)
        assert rec == "BUY"

    def test_rationale_fallback_uses_last_sentences(self):
        raw = "Sentence one. Sentence two. Sentence three. Sentence four."
        rationale, _, _ = _parse_llm_response(raw)
        assert rationale is not None
        assert len(rationale) > 0

    def test_rationale_capped_at_600_chars(self):
        raw = "word " * 200  # 1000 chars
        rationale, _, _ = _parse_llm_response(raw)
        assert len(rationale) <= 600 + 1  # +1 for ellipsis char


class TestParseEdgeCases:
    """Edge cases and malformed inputs."""

    def test_empty_string_returns_none_score(self):
        _, score, _ = _parse_llm_response("")
        assert score is None

    def test_no_score_returns_none(self):
        raw = "This is just some text with no structured data."
        _, score, _ = _parse_llm_response(raw)
        assert score is None

    def test_no_recommendation_returns_none_or_fallback(self):
        raw = "AI_RISK_SCORE: 50\nRATIONALE: Some analysis."
        _, _, rec = _parse_llm_response(raw)
        # No BUY/HOLD/SELL anywhere — rec should be None
        assert rec is None

    def test_always_returns_three_tuple(self):
        result = _parse_llm_response("garbage input @@##")
        assert len(result) == 3

    def test_rationale_never_none(self):
        """Rationale should always be a non-empty string."""
        raw = "AI_RISK_SCORE: 50\nAI_RECOMMENDATION: HOLD\nRATIONALE: Good stock."
        rationale, _, _ = _parse_llm_response(raw)
        assert rationale is not None
        assert len(rationale) > 0

    def test_rationale_never_none_on_empty_input(self):
        rationale, _, _ = _parse_llm_response("")
        assert rationale is not None

    def test_score_with_leading_zeros(self):
        raw = "AI_RISK_SCORE: 05\nAI_RECOMMENDATION: BUY\nRATIONALE: Very low risk."
        _, score, _ = _parse_llm_response(raw)
        assert score == pytest.approx(5.0)
