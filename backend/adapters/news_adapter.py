"""News sentiment adapters: Finnhub and NewsAPI."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from backend.base_adapter import BaseAdapter
from backend.settings import settings

logger = logging.getLogger(__name__)

_FALLBACK = {
    "sentiment": 0.0,
    "headline_summary": "",
    "article_count": 0,
    "fetched_at": "",
}


def _score_to_float(articles: list[dict]) -> float:
    """Compute a simple average sentiment from article scores if available."""
    scores = [a.get("sentiment", {}).get("score", 0.0) for a in articles if isinstance(a.get("sentiment"), dict)]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


class FinnhubAdapter(BaseAdapter):
    """Fetches news sentiment from Finnhub free tier."""

    @property
    def tool_name(self) -> str:
        return "fetch_news_sentiment"

    @property
    def tool_description(self) -> str:
        return "Fetch recent news sentiment (positive/neutral/negative) for a stock ticker."

    async def fetch(self, ticker: str) -> dict:
        api_key = settings.finnhub_api_key
        if not api_key:
            logger.warning("FINNHUB_API_KEY not set; returning empty sentiment")
            return {**_FALLBACK, "fetched_at": datetime.now(tz=timezone.utc).isoformat()}

        url = "https://finnhub.io/api/v1/company-news"
        from datetime import date, timedelta
        today = date.today()
        params = {
            "symbol": ticker.upper(),
            "from": (today - timedelta(days=7)).isoformat(),
            "to": today.isoformat(),
            "token": api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                articles: list[dict] = resp.json() or []
        except Exception as exc:
            logger.warning("Finnhub news fetch failed for %s: %s", ticker, exc)
            return {**_FALLBACK, "fetched_at": datetime.now(tz=timezone.utc).isoformat()}

        if not articles:
            return {**_FALLBACK, "article_count": 0, "fetched_at": datetime.now(tz=timezone.utc).isoformat()}

        top3 = articles[:3]
        headlines = " | ".join(
            (a.get("headline", "") or "")[:500] for a in top3
        )
        sentiment_score = _score_to_float(top3)

        return {
            "sentiment": sentiment_score,
            "headline_summary": headlines,
            "article_count": len(articles),
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        }

    def validate_output(self, data: dict) -> dict:
        required = {"sentiment", "headline_summary", "article_count"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"FinnhubAdapter output missing required keys: {missing}")
        return super().validate_output(data)


class NewsAPIAdapter(BaseAdapter):
    """Fetches news sentiment from NewsAPI free tier."""

    @property
    def tool_name(self) -> str:
        return "fetch_news_sentiment"

    @property
    def tool_description(self) -> str:
        return "Fetch recent news sentiment (positive/neutral/negative) for a stock ticker."

    async def fetch(self, ticker: str) -> dict:
        api_key = settings.news_api_key
        if not api_key:
            logger.warning("NEWS_API_KEY not set; returning empty sentiment")
            return {**_FALLBACK, "fetched_at": datetime.now(tz=timezone.utc).isoformat()}

        url = "https://newsapi.org/v2/everything"
        params = {
            "q": ticker.upper(),
            "sortBy": "publishedAt",
            "pageSize": 5,
            "apiKey": api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                articles: list[dict] = data.get("articles") or []
        except Exception as exc:
            logger.warning("NewsAPI fetch failed for %s: %s", ticker, exc)
            return {**_FALLBACK, "fetched_at": datetime.now(tz=timezone.utc).isoformat()}

        if not articles:
            return {**_FALLBACK, "article_count": 0, "fetched_at": datetime.now(tz=timezone.utc).isoformat()}

        top3 = articles[:3]
        headlines = " | ".join(
            (a.get("title", "") or "")[:500] for a in top3
        )

        return {
            "sentiment": 0.0,  # NewsAPI free tier has no sentiment score
            "headline_summary": headlines,
            "article_count": len(articles),
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        }

    def validate_output(self, data: dict) -> dict:
        required = {"sentiment", "headline_summary", "article_count"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"NewsAPIAdapter output missing required keys: {missing}")
        return super().validate_output(data)
