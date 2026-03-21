"""yfinance adapter: stock data and earnings."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import yfinance as yf

from backend.base_adapter import BaseAdapter
from backend.models import EarningsData, StockData

logger = logging.getLogger(__name__)


class YFinanceAdapter(BaseAdapter):
    """Fetches stock data and earnings via yfinance."""

    @property
    def tool_name(self) -> str:
        return "fetch_earnings"

    @property
    def tool_description(self) -> str:
        return (
            "Fetch the most recent earnings data (EPS estimate, EPS actual, surprise %) "
            "for a given stock ticker using yfinance."
        )

    async def fetch(self, ticker: str) -> dict:
        """Fetch StockData for a ticker. Returns a dict representation."""
        stock_data = await self.fetch_stock_data(ticker)
        return stock_data.model_dump(mode="json")

    async def fetch_stock_data(self, ticker: str) -> StockData:
        """Return a StockData object for the given ticker."""
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, self._get_info, ticker)
        return StockData(
            ticker=ticker.upper(),
            price=_safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
            price_change_pct=_safe_float(info.get("regularMarketChangePercent")),
            volume=_safe_int(info.get("volume") or info.get("regularMarketVolume")),
            peg_ratio=_safe_float(info.get("trailingPegRatio") or info.get("pegRatio")),
            beta=_safe_float(info.get("beta")),
            pe_ratio=_safe_float(info.get("trailingPE") or info.get("forwardPE")),
            debt_to_equity=_safe_float(info.get("debtToEquity")),
            market_cap=_safe_int(info.get("marketCap")),
            sector=info.get("sector"),
            fetched_at=datetime.now(tz=timezone.utc),
            is_stale=False,
        )

    async def fetch_price_history(self, ticker: str, period: str) -> list[dict]:
        """Return OHLC price history for the given period (1w, 1y, 2y)."""
        period_map = {"1w": ("7d", "1d"), "1y": ("1y", "1wk"), "2y": ("2y", "1wk")}
        yf_period, interval = period_map.get(period, ("1y", "1wk"))
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, self._get_history, ticker, yf_period, interval)
        return df

    async def fetch_earnings(self, ticker: str) -> EarningsData:
        """Return EarningsData for the given ticker."""
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, self._get_info, ticker)
        eps_actual = _safe_float(info.get("trailingEps"))
        eps_estimate = _safe_float(info.get("epsForward") or info.get("epsCurrentYear"))
        surprise_pct: float | None = None
        if eps_actual is not None and eps_estimate and eps_estimate != 0:
            surprise_pct = ((eps_actual - eps_estimate) / abs(eps_estimate)) * 100.0
        return EarningsData(
            ticker=ticker.upper(),
            eps_actual=eps_actual,
            eps_estimate=eps_estimate,
            surprise_pct=surprise_pct,
            report_date=None,
            fetched_at=datetime.now(tz=timezone.utc),
        )

    def validate_output(self, data: dict) -> dict:
        required = {"ticker", "fetched_at"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"YFinanceAdapter output missing required keys: {missing}")
        return super().validate_output(data)

    # ------------------------------------------------------------------
    # Sync helper (runs in executor)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_history(ticker: str, period: str, interval: str) -> list[dict]:
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval)
            if df.empty:
                return []
            return [
                {"date": str(idx.date()), "close": round(float(row["Close"]), 2)}
                for idx, row in df.iterrows()
            ]
        except Exception as exc:
            logger.warning("yfinance history failed for %s: %s", ticker, exc)
            return []

    @staticmethod
    def _get_info(ticker: str) -> dict:
        try:
            return yf.Ticker(ticker).info or {}
        except Exception as exc:
            logger.warning("yfinance info failed for %s: %s", ticker, exc)
            return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
