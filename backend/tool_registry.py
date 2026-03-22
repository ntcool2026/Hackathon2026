"""ToolRegistry: loads tools_config.yaml and exposes LangChain StructuredTools."""
from __future__ import annotations

import yaml
from langchain_core.tools import StructuredTool

from backend.base_adapter import BaseAdapter
from backend.settings import settings

class ToolRegistry:
    """Loads tools_config.yaml at startup and wraps enabled adapters as LangChain tools."""

    def __init__(self, config: dict) -> None:
        # Import here to avoid circular imports at module load time
        from backend.adapters import ADAPTER_REGISTRY  # type: ignore[import]

        self._tools: list[StructuredTool] = []

        for entry in config.get("tools", []):
            if not entry.get("enabled", False):
                continue

            adapter_name: str = entry.get("adapter", "")
            tool_name: str = entry.get("name", adapter_name)

            if adapter_name not in ADAPTER_REGISTRY:
                raise ValueError(
                    f"Unknown adapter '{adapter_name}' for tool '{tool_name}'. "
                    f"Available adapters: {list(ADAPTER_REGISTRY.keys())}"
                )

            adapter_cls = ADAPTER_REGISTRY[adapter_name]
            adapter: BaseAdapter = adapter_cls(config=entry.get("config", {}))

            # Capture adapter in closure
            async def _fetch(ticker: str, _adapter: BaseAdapter = adapter) -> dict:
                raw = await _adapter.fetch(ticker)
                return _adapter.validate_output(raw)

            self._tools.append(
                StructuredTool.from_function(
                    coroutine=_fetch,
                    name=adapter.tool_name,
                    description=adapter.tool_description,
                )
            )
            logger.debug("Registered tool '%s' backed by '%s'", adapter.tool_name, adapter_name)

    @classmethod
    def from_config(cls, path: str | None = None) -> "ToolRegistry":
        """Load config from a YAML file path (or TOOLS_CONFIG_PATH env var)."""
        from pathlib import Path
        resolved_path = path or settings.tools_config_path
        # If the path is relative, resolve it against the repo root (two levels up from this file)
        p = Path(resolved_path)
        if not p.is_absolute() and not p.exists():
            repo_root = Path(__file__).resolve().parents[1]
            p = repo_root / resolved_path
        try:
            with open(p) as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"tools_config.yaml not found at '{p}'. "
                "Set TOOLS_CONFIG_PATH to the correct path."
            )
        if config is None:
            raise ValueError(
                f"tools_config.yaml at '{resolved_path}' is empty or malformed."
            )
        return cls(config)

    def get_tools(self) -> list[StructuredTool]:
        return list(self._tools)
