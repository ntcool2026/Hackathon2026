"""Property-based tests for BaseAdapter, ToolRegistry, and data source adapters.

# Feature: stock-portfolio-advisor
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.adapters.news_adapter import FinnhubAdapter, NewsAPIAdapter
from backend.adapters.sec_edgar_adapter import SECEdgarAdapter
from backend.adapters.yfinance_adapter import YFinanceAdapter
from backend.base_adapter import BaseAdapter
from backend.models import EarningsData

# ---------------------------------------------------------------------------
# Concrete stub adapter for testing BaseAdapter directly
# ---------------------------------------------------------------------------

class StubAdapter(BaseAdapter):
    """Minimal concrete adapter for testing BaseAdapter.validate_output."""

    @property
    def tool_name(self) -> str:
        return "stub"

    @property
    def tool_description(self) -> str:
        return "stub"

    async def fetch(self, ticker: str) -> dict:
        return {}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Arbitrary string keys and values for dict generation
key_strategy = st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"))
value_strategy = st.one_of(st.text(max_size=50), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.booleans())

dict_strategy = st.dictionaries(key_strategy, value_strategy, min_size=0, max_size=10)

NOW = datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Property 38: Adapter validate_output rejects missing required keys
# Validates: Requirements 12.1, 12.2
# ---------------------------------------------------------------------------


def test_yfinance_validate_output_rejects_missing_ticker() -> None:
    """Property 38 (YFinance): validate_output raises ValueError when 'ticker' is missing.

    # Feature: stock-portfolio-advisor, Property 38: Adapter validate_output rejects missing required keys
    Validates: Requirements 12.1, 12.2
    """
    adapter = YFinanceAdapter()
    with pytest.raises(ValueError, match="missing required keys"):
        adapter.validate_output({"fetched_at": NOW.isoformat()})


def test_yfinance_validate_output_rejects_missing_fetched_at() -> None:
    """Property 38 (YFinance): validate_output raises ValueError when 'fetched_at' is missing."""
    adapter = YFinanceAdapter()
    with pytest.raises(ValueError, match="missing required keys"):
        adapter.validate_output({"ticker": "AAPL"})


def test_finnhub_validate_output_rejects_missing_keys() -> None:
    """Property 38 (Finnhub): validate_output raises ValueError when required keys are missing.

    # Feature: stock-portfolio-advisor, Property 38: Adapter validate_output rejects missing required keys
    """
    adapter = FinnhubAdapter()
    # Missing 'article_count'
    with pytest.raises(ValueError, match="missing required keys"):
        adapter.validate_output({"sentiment": 0.0, "headline_summary": "test"})


def test_sec_edgar_validate_output_rejects_missing_filings() -> None:
    """Property 38 (SEC): validate_output raises ValueError when 'filings' is missing."""
    adapter = SECEdgarAdapter()
    with pytest.raises(ValueError, match="missing required keys"):
        adapter.validate_output({"ticker": "AAPL"})


@settings(max_examples=100)
@given(data=dict_strategy)
def test_base_adapter_validate_output_accepts_valid_dict(data: dict) -> None:
    """Property 38 (base): validate_output on BaseAdapter passes any dict through (no required keys at base level).

    # Feature: stock-portfolio-advisor, Property 38: Adapter validate_output rejects missing required keys
    Validates: Requirements 12.1, 12.2
    """
    adapter = StubAdapter()
    # Base adapter has no required-key check — it only truncates
    result = adapter.validate_output(data)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Property 39: Adapter output is truncated when it exceeds LLM_MAX_CONTEXT_CHARS
# Validates: Requirements 7.2
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(extra_chars=st.integers(min_value=1, max_value=5000))
def test_base_adapter_truncates_large_output(extra_chars: int) -> None:
    """Property 39: validate_output truncates serialized output exceeding 8000 chars.

    # Feature: stock-portfolio-advisor, Property 39: Adapter output is truncated when it exceeds LLM_MAX_CONTEXT_CHARS
    Validates: Requirements 7.2
    """
    adapter = StubAdapter()
    # Build a dict whose JSON serialization exceeds 8000 chars
    big_value = "x" * (8000 + extra_chars)
    data = {"key": big_value}
    result = adapter.validate_output(data)
    # Should be truncated — result contains _truncated_output key
    assert "_truncated_output" in result
    truncated_str = result["_truncated_output"]
    assert truncated_str.endswith("[truncated]")
    assert len(truncated_str) <= 8000 + len(" [truncated]")


def test_base_adapter_does_not_truncate_small_output() -> None:
    """Property 39 (inverse): small output passes through unchanged."""
    adapter = StubAdapter()
    data = {"ticker": "AAPL", "price": 150.0}
    result = adapter.validate_output(data)
    assert result == data


# ---------------------------------------------------------------------------
# Property 26: ToolRegistry loads only enabled tools
# Validates: Requirements 12.1, 12.3
# ---------------------------------------------------------------------------


def test_tool_registry_loads_only_enabled_tools() -> None:
    """Property 26: ToolRegistry loads only enabled tools from config.

    # Feature: stock-portfolio-advisor, Property 26: ToolRegistry loads only enabled tools
    Validates: Requirements 12.1, 12.3
    """
    from backend.tool_registry import ToolRegistry

    config = {
        "tools": [
            {"name": "tool_a", "enabled": True, "adapter": "yfinance"},
            {"name": "tool_b", "enabled": False, "adapter": "finnhub"},
            {"name": "tool_c", "enabled": True, "adapter": "sec_edgar"},
        ]
    }
    registry = ToolRegistry(config)
    tools = registry.get_tools()
    # Only 2 enabled tools should be loaded
    assert len(tools) == 2


def test_tool_registry_empty_when_all_disabled() -> None:
    """Property 26: ToolRegistry returns empty list when all tools are disabled."""
    from backend.tool_registry import ToolRegistry

    config = {
        "tools": [
            {"name": "tool_a", "enabled": False, "adapter": "yfinance"},
            {"name": "tool_b", "enabled": False, "adapter": "finnhub"},
        ]
    }
    registry = ToolRegistry(config)
    assert registry.get_tools() == []


# ---------------------------------------------------------------------------
# Property 27: Invalid tools_config.yaml raises a descriptive startup error
# Validates: Requirements 12.4
# ---------------------------------------------------------------------------


def test_tool_registry_raises_on_missing_file() -> None:
    """Property 27: Missing tools_config.yaml raises FileNotFoundError with descriptive message.

    # Feature: stock-portfolio-advisor, Property 27: Invalid tools_config.yaml raises a descriptive startup error
    Validates: Requirements 12.4
    """
    from backend.tool_registry import ToolRegistry

    with pytest.raises(FileNotFoundError, match="tools_config.yaml not found"):
        ToolRegistry.from_config("/nonexistent/path/tools_config.yaml")


def test_tool_registry_raises_on_unknown_adapter() -> None:
    """Property 27: Unknown adapter name raises ValueError with descriptive message."""
    from backend.tool_registry import ToolRegistry

    config = {
        "tools": [
            {"name": "bad_tool", "enabled": True, "adapter": "nonexistent_adapter"},
        ]
    }
    with pytest.raises(ValueError, match="Unknown adapter"):
        ToolRegistry(config)


def test_tool_registry_raises_on_empty_yaml() -> None:
    """Property 27: Empty YAML file raises ValueError."""
    from backend.tool_registry import ToolRegistry

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")  # empty file
        tmp_path = f.name

    try:
        with pytest.raises(ValueError, match="empty or malformed"):
            ToolRegistry.from_config(tmp_path)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Property 28: Adapter fetch output passes through to the LLM tool unchanged
# Validates: Requirements 12.1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yfinance_fetch_output_passes_through_validate() -> None:
    """Property 28: YFinanceAdapter fetch output passes through validate_output unchanged (when valid).

    # Feature: stock-portfolio-advisor, Property 28: Adapter fetch output passes through to the LLM tool unchanged
    Validates: Requirements 12.1
    """
    adapter = YFinanceAdapter()
    valid_output = {
        "ticker": "AAPL",
        "price": 150.0,
        "fetched_at": NOW.isoformat(),
    }
    result = adapter.validate_output(valid_output)
    # All original keys should be present
    assert result["ticker"] == "AAPL"
    assert result["price"] == 150.0


@pytest.mark.asyncio
async def test_finnhub_fetch_output_passes_through_validate() -> None:
    """Property 28: FinnhubAdapter fetch output passes through validate_output unchanged (when valid)."""
    adapter = FinnhubAdapter()
    valid_output = {
        "sentiment": 0.5,
        "headline_summary": "Markets rally",
        "article_count": 3,
        "fetched_at": NOW.isoformat(),
    }
    result = adapter.validate_output(valid_output)
    assert result["sentiment"] == 0.5
    assert result["article_count"] == 3


# ---------------------------------------------------------------------------
# Property 22: Earnings adapter returns well-formed data for valid responses
# Validates: Requirements 9.1, 9.2
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    eps_actual=st.one_of(st.none(), st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
    eps_estimate=st.one_of(st.none(), st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False)),
)
@pytest.mark.asyncio
async def test_earnings_adapter_returns_well_formed_data(
    eps_actual: float | None, eps_estimate: float | None
) -> None:
    """Property 22: Earnings adapter returns well-formed EarningsData for valid yfinance responses.

    # Feature: stock-portfolio-advisor, Property 22: Earnings adapter returns well-formed data for valid responses
    Validates: Requirements 9.1, 9.2
    """
    adapter = YFinanceAdapter()
    mock_info = {
        "trailingEps": eps_actual,
        "epsForward": eps_estimate,
    }
    with patch.object(adapter, "_get_info", return_value=mock_info):
        result = await adapter.fetch_earnings("AAPL")

    assert isinstance(result, EarningsData)
    assert result.ticker == "AAPL"
    assert result.eps_actual == eps_actual
    # surprise_pct should only be set when both values are present and estimate != 0
    if eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
        assert result.surprise_pct is not None
    else:
        assert result.surprise_pct is None


# ---------------------------------------------------------------------------
# Property 21: News adapter returns well-formed sentiment for valid responses
# Validates: Requirements 8.1, 8.2
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    article_count=st.integers(min_value=0, max_value=10),
    headline=st.text(min_size=0, max_size=600),
)
@pytest.mark.asyncio
async def test_news_adapter_returns_well_formed_sentiment(
    article_count: int, headline: str
) -> None:
    """Property 21: News adapter returns well-formed sentiment dict for valid API responses.

    # Feature: stock-portfolio-advisor, Property 21: News adapter returns well-formed sentiment for valid responses
    Validates: Requirements 8.1, 8.2
    """
    adapter = FinnhubAdapter()
    articles = [{"headline": headline, "sentiment": {}} for _ in range(article_count)]

    mock_response = MagicMock()
    mock_response.json.return_value = articles
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("backend.adapters.news_adapter.settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_client):
        mock_settings.finnhub_api_key = "test_key"
        result = await adapter.fetch("AAPL")

    assert "sentiment" in result
    assert "headline_summary" in result
    assert "article_count" in result
    assert isinstance(result["sentiment"], float)
    assert isinstance(result["article_count"], int)
    # Headlines should be truncated to 500 chars each
    if article_count > 0:
        for part in result["headline_summary"].split(" | "):
            assert len(part) <= 500


# ---------------------------------------------------------------------------
# Property 23: SEC EDGAR adapter returns well-formed filings for valid responses
# Validates: Requirements 10.1, 10.2
# ---------------------------------------------------------------------------


@settings(max_examples=30)
@given(
    forms=st.lists(
        st.sampled_from(["10-K", "10-Q", "8-K", "S-1", "DEF 14A"]),
        min_size=0,
        max_size=10,
    ),
    description=st.text(min_size=0, max_size=1500),
)
@pytest.mark.asyncio
async def test_sec_edgar_adapter_returns_well_formed_filings(
    forms: list[str], description: str
) -> None:
    """Property 23: SEC EDGAR adapter returns well-formed filings (max 3, target forms only).

    # Feature: stock-portfolio-advisor, Property 23: SEC EDGAR adapter returns well-formed filings for valid responses
    Validates: Requirements 10.1, 10.2
    """
    adapter = SECEdgarAdapter()
    n = len(forms)
    mock_submissions = {
        "filings": {
            "recent": {
                "form": forms,
                "filingDate": ["2024-01-01"] * n,
                "primaryDocument": [description] * n,
            }
        }
    }

    mock_cik_resp = MagicMock()
    mock_cik_resp.json.return_value = {
        "0": {"ticker": "AAPL", "cik_str": 320193}
    }
    mock_cik_resp.raise_for_status = MagicMock()

    mock_sub_resp = MagicMock()
    mock_sub_resp.json.return_value = mock_submissions
    mock_sub_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=[mock_cik_resp, mock_sub_resp])

    # Clear CIK cache to force fresh lookup
    SECEdgarAdapter._cik_cache.clear()

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.fetch("AAPL")

    assert "ticker" in result
    assert "filings" in result
    filings = result["filings"]
    # At most 3 filings
    assert len(filings) <= 3
    # Only target form types
    target_forms = {"10-K", "10-Q", "8-K"}
    for filing in filings:
        assert filing["form_type"] in target_forms
        # Description truncated to 1000 chars
        assert len(filing.get("description", "")) <= 1000
