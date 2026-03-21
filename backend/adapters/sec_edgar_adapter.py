"""SEC EDGAR adapter: fetches recent 10-K, 10-Q, 8-K filings."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from backend.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)

_EDGAR_COMPANY_TICKERS = "https://www.sec.gov/files/company_tickers.json"
_EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
_TARGET_FORMS = {"10-K", "10-Q", "8-K"}
_HEADERS = {"User-Agent": "stock-portfolio-advisor contact@example.com"}


class SECEdgarAdapter(BaseAdapter):
    """Fetches recent SEC filings from the EDGAR public API (no API key required)."""

    # Simple in-process cache: ticker → CIK string
    _cik_cache: dict[str, str] = {}

    @property
    def tool_name(self) -> str:
        return "fetch_sec_filings"

    @property
    def tool_description(self) -> str:
        return (
            "Fetch the most recent 10-K, 10-Q, and 8-K SEC filings for a given stock ticker "
            "using the SEC EDGAR public API."
        )

    async def fetch(self, ticker: str) -> dict:
        ticker = ticker.upper()
        try:
            cik = await self._resolve_cik(ticker)
            if not cik:
                return self._empty(ticker)
            filings = await self._fetch_filings(ticker, cik)
            return {"ticker": ticker, "filings": filings, "fetched_at": datetime.now(tz=timezone.utc).isoformat()}
        except Exception as exc:
            logger.warning("SEC EDGAR fetch failed for %s: %s", ticker, exc)
            return self._empty(ticker)

    def validate_output(self, data: dict) -> dict:
        required = {"ticker", "filings"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"SECEdgarAdapter output missing required keys: {missing}")
        return super().validate_output(data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _resolve_cik(self, ticker: str) -> str | None:
        if ticker in self._cik_cache:
            return self._cik_cache[ticker]
        try:
            async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
                resp = await client.get(_EDGAR_COMPANY_TICKERS)
                resp.raise_for_status()
                data: dict = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch EDGAR company tickers: %s", exc)
            return None

        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker:
                cik = str(entry["cik_str"]).zfill(10)
                self._cik_cache[ticker] = cik
                return cik
        return None

    async def _fetch_filings(self, ticker: str, cik: str) -> list[dict]:
        url = _EDGAR_SUBMISSIONS.format(cik=cik)
        try:
            async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data: dict = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch EDGAR submissions for %s: %s", ticker, exc)
            return []

        recent = data.get("filings", {}).get("recent", {})
        forms: list[str] = recent.get("form", [])
        dates: list[str] = recent.get("filingDate", [])
        descriptions: list[str] = recent.get("primaryDocument", [])

        results: list[dict] = []
        seen_forms: set[str] = set()

        for form, date_str, desc in zip(forms, dates, descriptions):
            if form not in _TARGET_FORMS:
                continue
            if form in seen_forms:
                continue
            seen_forms.add(form)
            results.append({
                "form_type": form,
                "filed_at": date_str,
                "description": (desc or "")[:1000],
            })
            if len(results) >= 3:
                break

        return results

    @staticmethod
    def _empty(ticker: str) -> dict:
        return {
            "ticker": ticker,
            "filings": [],
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        }
