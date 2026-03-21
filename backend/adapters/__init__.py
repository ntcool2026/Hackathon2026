"""Adapter registry: maps adapter name strings to their implementation classes."""
from backend.adapters.news_adapter import FinnhubAdapter, NewsAPIAdapter
from backend.adapters.sec_edgar_adapter import SECEdgarAdapter
from backend.adapters.yfinance_adapter import YFinanceAdapter

ADAPTER_REGISTRY = {
    "finnhub": FinnhubAdapter,
    "newsapi": NewsAPIAdapter,
    "sec_edgar": SECEdgarAdapter,
    "yfinance": YFinanceAdapter,
}

__all__ = ["ADAPTER_REGISTRY", "FinnhubAdapter", "NewsAPIAdapter", "SECEdgarAdapter", "YFinanceAdapter"]
