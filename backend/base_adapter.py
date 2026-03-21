"""Abstract base class for all data source adapters."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from backend.settings import settings


class BaseAdapter(ABC):
    """All data source adapters must implement this interface."""

    def __init__(self, config: dict | None = None) -> None:
        self.config: dict = config or {}

    @abstractmethod
    async def fetch(self, ticker: str) -> dict:
        """Fetch data for a ticker. Returns a dict passed to the LLM tool."""
        ...

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """The name of the LangChain tool this adapter exposes."""
        ...

    @property
    @abstractmethod
    def tool_description(self) -> str:
        """Description passed to the LLM so it knows when to use this tool."""
        ...

    def validate_output(self, data: dict) -> dict:
        """Validate required keys and enforce LLM_MAX_CONTEXT_CHARS size cap.

        Subclasses override this to check adapter-specific required keys,
        then call super().validate_output(data) for the size cap.
        """
        serialized = json.dumps(data)
        max_chars: int = settings.llm_max_context_chars
        if len(serialized) > max_chars:
            truncated = serialized[:max_chars] + " [truncated]"
            return {"_truncated_output": truncated}
        return data
