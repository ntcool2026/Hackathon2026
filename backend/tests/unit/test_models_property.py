"""Property-based tests for Pydantic models."""
from __future__ import annotations

# Feature: stock-portfolio-advisor, Property 16: StockData serialization round-trip

from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models import StockData

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid ticker: 1–5 uppercase letters
ticker_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu",)),
    min_size=1,
    max_size=5,
)

# Optional float fields — finite floats only (no NaN/inf which Pydantic rejects)
opt_float = st.one_of(st.none(), st.floats(allow_nan=False, allow_infinity=False))

# Optional int fields
opt_int = st.one_of(st.none(), st.integers(min_value=0, max_value=10**12))

# Optional string fields
opt_str = st.one_of(st.none(), st.text(max_size=50))

# datetime strategy — always timezone-aware UTC
datetime_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(timezone.utc),
)

stock_data_strategy = st.builds(
    StockData,
    ticker=ticker_strategy,
    price=opt_float,
    price_change_pct=opt_float,
    volume=opt_int,
    peg_ratio=opt_float,
    beta=opt_float,
    pe_ratio=opt_float,
    debt_to_equity=opt_float,
    market_cap=opt_int,
    sector=opt_str,
    fetched_at=datetime_strategy,
    is_stale=st.booleans(),
)


# ---------------------------------------------------------------------------
# Property 16: StockData serialization round-trip
# Validates: Requirements 6.1, 6.3, 6.4
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(stock=stock_data_strategy)
def test_stock_data_serialization_round_trip(stock: StockData) -> None:
    """For all valid StockData objects, parsing then serializing then parsing
    SHALL produce an equivalent StockData object (round-trip property).

    Validates: Requirements 6.1, 6.3, 6.4
    """
    round_tripped = StockData.model_validate(stock.model_dump())
    assert round_tripped == stock


# ---------------------------------------------------------------------------
# Property 17: Malformed payloads are rejected with a parse error
# Feature: stock-portfolio-advisor, Property 17: Malformed payloads are rejected with a parse error
# Validates: Requirements 6.2
# ---------------------------------------------------------------------------

import pytest
from pydantic import ValidationError

# Strategy: generate dicts that are missing required fields or have wrong types
# Required fields for StockData: ticker (str) and fetched_at (datetime)

# Missing 'ticker' field
missing_ticker_strategy = st.fixed_dictionaries(
    {
        "fetched_at": datetime_strategy,
    }
)

# Missing 'fetched_at' field
missing_fetched_at_strategy = st.fixed_dictionaries(
    {
        "ticker": ticker_strategy,
    }
)

# Wrong type for 'ticker' (non-string)
wrong_ticker_type_strategy = st.fixed_dictionaries(
    {
        "ticker": st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.lists(st.text()),
        ),
        "fetched_at": datetime_strategy,
    }
)

# Wrong type for 'price' (non-numeric string)
wrong_price_type_strategy = st.fixed_dictionaries(
    {
        "ticker": ticker_strategy,
        "fetched_at": datetime_strategy,
        "price": st.text(min_size=1).filter(
            lambda s: not s.replace(".", "", 1).lstrip("-").isdigit()
        ),
    }
)

malformed_payload_strategy = st.one_of(
    missing_ticker_strategy,
    missing_fetched_at_strategy,
    wrong_ticker_type_strategy,
    wrong_price_type_strategy,
)


@settings(max_examples=100)
@given(payload=malformed_payload_strategy)
def test_malformed_stock_data_raises_validation_error(payload: dict) -> None:
    """IF a StockData payload is malformed or missing required fields,
    THEN StockData SHALL reject the payload and raise a ValidationError.

    Validates: Requirements 6.2
    """
    with pytest.raises(ValidationError):
        StockData.model_validate(payload)
