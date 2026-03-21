"""Layer 2 — LLM agent cycle: generate natural language rationale via LangChain ReAct."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from sqlalchemy import select, text

from backend.db import AsyncSessionLocal
from backend.models import WSEvent
from backend.models_orm import Portfolio, PortfolioStock, StockScore as StockScoreORM
from backend.settings import settings
from backend.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default ReAct prompt
# ---------------------------------------------------------------------------

_DEFAULT_REACT_PROMPT = """\
You are a financial analysis assistant. For the stock ticker {ticker}, use the available tools \
to gather signals (news sentiment, earnings data, SEC filings, and the current risk score), \
then reason step-by-step about the BUY/HOLD/SELL signal.

Tools available:
{tools}

Use the following format:
Thought: <your reasoning>
Action: <tool name>
Action Input: <tool input>
Observation: <tool output>
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I now have enough information to write a rationale.
Final Answer: <2-4 sentence natural language rationale referencing the signals used>

{agent_scratchpad}
"""


def _load_prompt() -> PromptTemplate:
    prompt_file = settings.llm_react_prompt_file
    if prompt_file:
        try:
            template = Path(prompt_file).read_text()
            return PromptTemplate.from_template(template)
        except Exception as exc:
            logger.warning("Failed to load LLM_REACT_PROMPT_FILE '%s': %s — using default", prompt_file, exc)
    return PromptTemplate.from_template(_DEFAULT_REACT_PROMPT)


# ---------------------------------------------------------------------------
# Agent factory (lazy singleton)
# ---------------------------------------------------------------------------

_agent_executor: AgentExecutor | None = None


def _get_agent_executor() -> AgentExecutor:
    global _agent_executor
    if _agent_executor is not None:
        return _agent_executor

    llm = ChatOpenAI(
        model=settings.llm_model,
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
        temperature=settings.llm_temperature,
    )

    registry = ToolRegistry.from_config()
    tools = registry.get_tools()
    prompt = _load_prompt()

    agent = create_react_agent(llm, tools, prompt)
    _agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=settings.llm_max_iterations,
        handle_parsing_errors=True,
    )
    return _agent_executor


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_llm_agent_cycle() -> None:
    """Run the LLM rationale cycle for all tickers that have changed enough."""
    async with AsyncSessionLocal() as db:
        # Collect (user_id, ticker, current_score, rationale_at_score) tuples
        candidates = await _get_candidates(db)

        if not candidates:
            logger.info("LLM agent cycle: no candidates to process")
            return

        # Delta filter + sort by largest delta, cap at LLM_MAX_TICKERS_PER_CYCLE
        delta_threshold = settings.llm_delta_threshold
        filtered = [
            (user_id, ticker, score, prev_score)
            for user_id, ticker, score, prev_score in candidates
            if abs(score - prev_score) >= delta_threshold
        ]
        filtered.sort(key=lambda x: abs(x[2] - x[3]), reverse=True)
        filtered = filtered[: settings.llm_max_tickers_per_cycle]

        if not filtered:
            logger.info("LLM agent cycle: all tickers below delta threshold %.1f", delta_threshold)
            return

        logger.info("LLM agent cycle: processing %d tickers", len(filtered))

        semaphore = asyncio.Semaphore(settings.llm_concurrency)
        tasks = [
            _process_ticker(user_id, ticker, semaphore)
            for user_id, ticker, _, _ in filtered
        ]
        await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Per-ticker processing
# ---------------------------------------------------------------------------


async def _process_ticker(user_id: str, ticker: str, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        rationale = await _generate_rationale(ticker)
        async with AsyncSessionLocal() as db:
            await _persist_rationale(db, user_id, ticker, rationale)
            from backend.ws_manager import ws_manager
            await ws_manager.broadcast_to_user(
                user_id,
                WSEvent(
                    event="rationale_update",
                    payload={
                        "ticker": ticker,
                        "rationale": rationale,
                        "rationale_at": datetime.now(tz=timezone.utc).isoformat(),
                    },
                ),
            )


async def _generate_rationale(ticker: str) -> str:
    try:
        executor = _get_agent_executor()
        result = await executor.ainvoke({"ticker": ticker, "input": ticker})
        return str(result.get("output", "")).strip() or _fallback_rationale(ticker)
    except Exception as exc:
        logger.warning("LLM agent failed for %s: %s", ticker, exc)
        return _fallback_rationale(ticker)


def _fallback_rationale(ticker: str) -> str:
    return (
        f"Automated analysis for {ticker} is temporarily unavailable. "
        "The numeric risk score reflects the latest market data."
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _get_candidates(
    db,
) -> list[tuple[str, str, float, float]]:
    """Return (user_id, ticker, current_score, score_at_last_rationale) tuples."""
    result = await db.execute(select(StockScoreORM))
    rows = result.scalars().all()
    candidates = []
    for row in rows:
        current_score = float(row.risk_score)
        # Use 0.0 as the "previous" score if no rationale has been generated yet
        # (rationale_at is None means never generated)
        prev_score = 0.0 if row.rationale_at is None else current_score
        candidates.append((row.user_id, row.ticker, current_score, prev_score))
    return candidates


async def _persist_rationale(db, user_id: str, ticker: str, rationale: str) -> None:
    now = datetime.now(tz=timezone.utc)
    await db.execute(
        text(
            "UPDATE stock_scores SET rationale = :r, rationale_at = :t "
            "WHERE user_id = :uid AND ticker = :ticker"
        ),
        {"r": rationale, "t": now, "uid": user_id, "ticker": ticker},
    )
    await db.commit()
