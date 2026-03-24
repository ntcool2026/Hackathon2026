"""Layer 2 — LLM agent cycle: multi-phase agentic loop via OpenRouter (httpx).

Phases per ticker:
  1. Load memory (previous ai_risk_score / ai_recommendation / rationale)
  2. Tool-call phase — LLM decides which adapters to invoke via function calling
  3. Initial analysis — parse AI_RISK_SCORE, AI_RECOMMENDATION, RATIONALE
  4. Reflection loop — LLM critiques its own output up to LLM_MAX_REFLECTION_ROUNDS
  5. Persist & broadcast rationale_update WS event

After all per-ticker loops: run_portfolio_analysis per user.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select, text

from backend.db import AsyncSessionLocal
from backend.models import PortfolioAnalysisResult, WSEvent
from backend.models_orm import StockData as StockDataORM
from backend.models_orm import StockScore as StockScoreORM
from backend.settings import settings

logger = logging.getLogger(__name__)

_CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

# Cerebras AI model
_CEREBRAS_MODEL = "qwen-3-235b-a22b-instruct-2507"

# ---------------------------------------------------------------------------
# Tool schema builder
# ---------------------------------------------------------------------------


def _build_tool_schemas(registry) -> list[dict]:
    """Build OpenRouter-compatible function schemas from ToolRegistry adapters."""
    schemas = []
    for tool in registry.get_tools():
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol",
                            }
                        },
                        "required": ["ticker"],
                    },
                },
            }
        )
    return schemas


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_system_prompt(ticker: str, memory: dict | None) -> str:
    """Build the system message, optionally injecting previous cycle memory."""
    base = (
        "You are a financial risk scoring API.\n"
        "OUTPUT EXACTLY THREE LINES. NOTHING ELSE.\n"
        "Do not include any reasoning, analysis, data summary, or explanation.\n"
        "Do not repeat the input data.\n\n"
        "AI_RISK_SCORE: <integer 0-100>\n"
        "AI_RECOMMENDATION: <BUY or HOLD or SELL>\n"
        "RATIONALE: <one factual sentence>"
    )
    if memory is None:
        return base

    prev_score = memory.get("ai_risk_score")
    prev_rec = memory.get("ai_recommendation", "N/A")
    prev_rationale = memory.get("rationale") or ""
    if len(prev_rationale) > 20 and not _looks_like_leaked_prompt(prev_rationale):
        prev_rationale = prev_rationale[:300]
        memory_section = (
            f"\n\nPrevious cycle for {ticker}: "
            f"score={prev_score}, rec={prev_rec}, rationale={prev_rationale}"
        )
        combined = base + memory_section
        return combined[:16000]

    return base


def _build_critique_message(score: float, rec: str, rationale: str) -> str:
    return (
        f"Previous: score={score:.1f}, rec={rec}, rationale={rationale}\n"
        f"Revise if needed. Output only:\n"
        f"AI_RISK_SCORE:\n"
        f"AI_RECOMMENDATION:\n"
        f"RATIONALE:"
    )


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

# Patterns that indicate the LLM echoed the prompt template instead of real content
_LEAKED_PROMPT_PATTERNS = [
    r"\[one sentence\]",
    r"<one sentence",
    r"<2-3 sentences",
    r"\[0-100\]",
    r"\[BUY\|HOLD\|SELL\]",
    r"<integer",
    r"output (only|exactly) (these|three)",
    r"from the previous analysis.*it says",
    r"in the output format",
    r"should be one sentence",
    r"quant_score=",
    r"quant risk score is \d",
]

_LEAKED_RE = re.compile("|".join(_LEAKED_PROMPT_PATTERNS), re.IGNORECASE)


def _looks_like_leaked_prompt(text: str) -> bool:
    return bool(_LEAKED_RE.search(text))


def _extract_structured_block(raw: str) -> str:
    """Extract only the AI_RISK_SCORE/AI_RECOMMENDATION/RATIONALE lines from raw LLM output.

    Strips <think>...</think> reasoning blocks, preamble, and any text after the
    three structured lines. Returns the cleaned block, or the original if no
    structured lines are found.
    """
    # Remove <think>...</think> blocks emitted by reasoning models (DeepSeek, etc.)
    raw = re.sub(
        r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE
    ).strip()

    # Find the first occurrence of any of the three keys and take from there
    match = re.search(r"(AI_RISK_SCORE\s*:)", raw, re.IGNORECASE)
    if match:
        result = raw[match.start() :]
        # Extract only the three lines (AI_RISK_SCORE, AI_RECOMMENDATION, RATIONALE)
        lines = []
        for line in result.split("\n"):
            line = line.strip()
            if re.match(
                r"^(AI_RISK_SCORE|AI_RECOMMENDATION|RATIONALE)\s*:", line, re.IGNORECASE
            ):
                lines.append(line)
            elif lines and not re.match(
                r"^(AI_RISK_SCORE|AI_RECOMMENDATION|RATIONALE)\s*:", line, re.IGNORECASE
            ):
                # If we have lines and this is a continuation, append to the last line
                if lines:
                    lines[-1] += " " + line
            if len(lines) >= 3:
                break
        if lines:
            return "\n".join(lines)
        return raw[match.start() :]

    return raw


def _sanitize_rationale(
    rationale: str | None, ticker: str, score: float, rec: str | None
) -> str:
    """Return a clean rationale, replacing leaked/empty content with a score-derived fallback."""
    if (
        not rationale
        or _looks_like_leaked_prompt(rationale)
        or len(rationale.strip()) < 15
    ):
        rec_str = rec or "HOLD"
        if score < 35:
            return f"{ticker} shows low quantitative risk (score {score:.0f}/100), supporting a {rec_str} signal."
        elif score < 65:
            return f"{ticker} carries moderate risk (score {score:.0f}/100); mixed signals suggest a cautious {rec_str} stance."
        else:
            return f"{ticker} exhibits elevated risk (score {score:.0f}/100), warranting a {rec_str} position review."
    return rationale.strip()


async def _call_cerebras(
    messages: list[dict],
    tool_schemas: list[dict] | None = None,
) -> dict:
    """Call Cerebras AI and return the full response dict."""
    headers = {
        "Authorization": f"Bearer {settings.cerebras_api_key}",
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {
        "model": _CEREBRAS_MODEL,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": 300,
    }
    if tool_schemas:
        payload["tools"] = tool_schemas
        payload["tool_choice"] = "auto"

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(_CEREBRAS_URL, json=payload, headers=headers)

        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})

        logger.info("Cerebras AI success with model: %s", _CEREBRAS_MODEL)
        return data

    except httpx.HTTPStatusError as exc:
        logger.error("Cerebras AI HTTP error: %s", exc.response.status_code)
        raise
    except Exception as exc:
        logger.error("Cerebras AI error: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Tool-call phase
# ---------------------------------------------------------------------------


async def _run_tool_call_phase(
    messages: list[dict],
    ticker: str,
    tool_schemas: list[dict],
    adapter_map: dict,
) -> tuple[list[dict], int]:
    """Execute the tool-call loop. Returns updated messages and tool call count."""
    tool_call_count = 0
    max_calls = settings.llm_max_tool_calls

    while tool_call_count < max_calls:
        data = await _call_cerebras(messages, tool_schemas)
        choice = data["choices"][0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            # No more tool calls — LLM is ready to produce final answer
            # Append the assistant message so the conversation is complete
            messages.append({"role": "assistant", "content": msg.get("content", "")})
            break

        # Append the assistant message with tool_calls
        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            }
        )

        # Execute each tool call
        for tc in tool_calls:
            tool_call_count += 1
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            tool_call_id = tc.get("id", "")

            adapter = adapter_map.get(tool_name)
            if adapter is None:
                result_content = f'{{"error": "unknown tool {tool_name}"}}'
            else:
                try:
                    raw = await adapter.fetch(ticker)
                    validated = adapter.validate_output(raw)
                    result_content = json.dumps(validated)[:4000]  # cap per tool result
                except Exception as exc:
                    logger.warning(
                        "Tool call %s failed for %s: %s", tool_name, ticker, exc
                    )
                    result_content = f'{{"error": "fetch failed: {exc}"}}'

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_content,
                }
            )

            if tool_call_count >= max_calls:
                break

    return messages, tool_call_count


# ---------------------------------------------------------------------------
# Reflection loop
# ---------------------------------------------------------------------------


async def _run_reflection_loop(
    messages: list[dict],
    initial_score: float,
    initial_rec: str,
    initial_rationale: str,
) -> tuple[float, str, str]:
    """Run up to LLM_MAX_REFLECTION_ROUNDS critique rounds. Returns (score, rec, rationale)."""
    score, rec, rationale = initial_score, initial_rec, initial_rationale
    max_rounds = settings.llm_max_reflection_rounds
    delta_threshold = settings.llm_reflection_delta

    for round_num in range(max_rounds):
        critique_msg = _build_critique_message(score, rec, rationale)
        messages.append({"role": "user", "content": critique_msg})

        try:
            data = await _call_cerebras(messages)
            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = _extract_structured_block((msg.get("content") or "").strip())
            reasoning = _extract_structured_block((msg.get("reasoning") or "").strip())
            text = (
                content
                if "AI_RISK_SCORE" in content.upper()
                else (reasoning if "AI_RISK_SCORE" in reasoning.upper() else content)
            )

            new_score, new_rec, new_rationale = _parse_structured_output(text)

            if new_score is None:
                logger.warning(
                    "Reflection round %d parse failure for score — stopping reflection",
                    round_num + 1,
                )
                break

            messages.append({"role": "assistant", "content": content})

            delta = abs(new_score - score)
            score, rec, rationale = (
                new_score,
                new_rec or rec,
                new_rationale or rationale,
            )

            logger.info(
                "Reflection round %d: score=%.1f delta=%.1f",
                round_num + 1,
                score,
                delta,
            )

            if delta < delta_threshold:
                logger.info(
                    "Reflection stopping early (delta %.1f < threshold %.1f)",
                    delta,
                    delta_threshold,
                )
                break

        except Exception as exc:
            logger.warning(
                "Reflection round %d failed: %s — stopping", round_num + 1, exc
            )
            break

    return score, rec, rationale


# ---------------------------------------------------------------------------
# Response parser (shared)
# ---------------------------------------------------------------------------


def _parse_structured_output(raw: str) -> tuple[float | None, str | None, str | None]:
    """Extract AI_RISK_SCORE, AI_RECOMMENDATION, RATIONALE from LLM text."""
    ai_score: float | None = None
    ai_rec: str | None = None
    rationale: str | None = None

    score_match = re.search(
        r"AI_RISK_SCORE\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)", raw, re.IGNORECASE
    )
    rec_match = re.search(
        r"AI_RECOMMENDATION\s*:\s*(BUY|HOLD|SELL)", raw, re.IGNORECASE
    )
    rat_match = re.search(
        r"RATIONALE\s*:\s*(.+?)(?=\nAI_|\Z)", raw, re.IGNORECASE | re.DOTALL
    )

    if score_match:
        try:
            ai_score = max(0.0, min(100.0, float(score_match.group(1))))
        except ValueError:
            pass

    if rec_match:
        ai_rec = rec_match.group(1).upper()

    if rat_match:
        rationale = rat_match.group(1).strip()

    # Fallback score extraction
    if ai_score is None:
        fb = re.search(
            r"(?:risk\s+score\s+(?:of\s+)?|score[:\s]+|final\s+score[:\s]+)([0-9]+(?:\.[0-9]+)?)",
            raw,
            re.IGNORECASE,
        ) or re.search(r"\b([0-9]{2}(?:\.[0-9]+)?)\s*/\s*100\b", raw)
        if fb:
            try:
                ai_score = max(0.0, min(100.0, float(fb.group(1))))
            except ValueError:
                pass

    # Fallback recommendation
    if ai_rec is None:
        fb_rec = re.search(
            r"(?:recommend(?:ation)?(?:\s+is)?|conclusion[:\s]+)[:\s]*(BUY|HOLD|SELL)",
            raw,
            re.IGNORECASE,
        )
        if fb_rec:
            ai_rec = fb_rec.group(1).upper()
        else:
            counts = {
                k: len(re.findall(rf"\b{k}\b", raw, re.IGNORECASE))
                for k in ("BUY", "HOLD", "SELL")
            }
            best = max(counts, key=lambda k: counts[k])
            if counts[best] > 0:
                ai_rec = best

    # Fallback rationale
    if rationale is None:
        sentences = re.split(r"(?<=[.!?])\s+", raw.strip())
        rationale = (
            " ".join(sentences[-3:]).strip() if len(sentences) >= 3 else raw.strip()
        )
        if len(rationale) > 600:
            rationale = rationale[:600].rsplit(" ", 1)[0] + "…"

    return ai_score, ai_rec, rationale


# Keep backward-compatible alias used by existing tests
def _parse_llm_response(raw: str) -> tuple[str, float | None, str | None]:
    """Legacy wrapper — returns (rationale, ai_score, ai_rec)."""
    score, rec, rationale = _parse_structured_output(raw)
    return (rationale or raw.strip(), score, rec)


# ---------------------------------------------------------------------------
# Per-ticker processing
# ---------------------------------------------------------------------------


async def _prefetch_tool_data(ticker: str, adapter_map: dict) -> dict[str, Any]:
    """Fetch all adapter data concurrently. Returns a dict of tool_name → result (or error string)."""
    if not adapter_map:
        return {}

    async def _fetch_one(tool_name: str, adapter) -> tuple[str, Any]:
        try:
            raw = await adapter.fetch(ticker)
            validated = adapter.validate_output(raw)
            return tool_name, validated
        except Exception as exc:
            logger.warning("Prefetch %s failed for %s: %s", tool_name, ticker, exc)
            return tool_name, None

    results = await asyncio.gather(
        *[_fetch_one(name, adapter) for name, adapter in adapter_map.items()]
    )
    return {name: data for name, data in results if data is not None}


def _build_analysis_user_message(
    ticker: str, risk_score: float, tool_data: dict[str, Any] | None = None
) -> str:
    """Build the user message, injecting pre-fetched tool data when available."""
    if not tool_data:
        return (
            f"{ticker} quant_risk_score={risk_score:.1f}/100.\n"
            f"AI_RISK_SCORE:\n"
            f"AI_RECOMMENDATION:\n"
            f"RATIONALE:"
        )

    # Summarise each tool result compactly
    data_lines: list[str] = []
    for tool_name, data in tool_data.items():
        if isinstance(data, dict):
            # Keep only the most relevant keys, cap length
            summary = json.dumps(data, default=str)[:800]
        else:
            summary = str(data)[:400]
        data_lines.append(f"[{tool_name}] {summary}")

    data_block = "\n".join(data_lines)
    return (
        f"{ticker} quant_risk_score={risk_score:.1f}/100.\n\n"
        f"Market data:\n{data_block}\n\n"
        f"AI_RISK_SCORE:\n"
        f"AI_RECOMMENDATION:\n"
        f"RATIONALE:"
    )


async def _generate_rationale(
    ticker: str,
    risk_score: float,
    memory: dict | None,
    tool_schemas: list[dict],
    adapter_map: dict,
) -> tuple[str, float | None, str | None]:
    """Run the full agent loop for one ticker. Returns (rationale, ai_score, ai_rec)."""
    try:
        # Pre-fetch all tool data concurrently in Python — no function calling required
        tool_data = await _prefetch_tool_data(ticker, adapter_map)
        tool_call_count = len(tool_data)
        if tool_data:
            logger.info(
                "Prefetched %d tool(s) for %s: %s",
                tool_call_count,
                ticker,
                list(tool_data.keys()),
            )
        else:
            logger.info(
                "No tool data available for %s — using quant score only", ticker
            )

        system_prompt = _build_system_prompt(ticker, memory)
        user_msg = _build_analysis_user_message(ticker, risk_score, tool_data)
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        # Phase 2: initial analysis — get structured output from last assistant message
        # If tool phase ended with an assistant message containing AI_RISK_SCORE, use it
        last_assistant = next(
            (
                m["content"]
                for m in reversed(messages)
                if m["role"] == "assistant" and m.get("content")
            ),
            None,
        )

        if last_assistant and "AI_RISK_SCORE" in last_assistant.upper():
            raw_analysis = _extract_structured_block(last_assistant)
        else:
            # Ask for final analysis explicitly
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"{ticker} final output:\n"
                        f"AI_RISK_SCORE:\n"
                        f"AI_RECOMMENDATION:\n"
                        f"RATIONALE:"
                    ),
                }
            )
            data = await _call_cerebras(messages)
            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = _extract_structured_block((msg.get("content") or "").strip())
            reasoning = _extract_structured_block((msg.get("reasoning") or "").strip())
            raw_analysis = (
                content
                if "AI_RISK_SCORE" in content.upper()
                else (reasoning if "AI_RISK_SCORE" in reasoning.upper() else content)
            )
            messages.append({"role": "assistant", "content": raw_analysis})

        initial_score, initial_rec, initial_rationale = _parse_structured_output(
            raw_analysis
        )

        if initial_score is None:
            logger.warning(
                "Initial parse failed for %s — using quant score as fallback", ticker
            )
            initial_score = risk_score
            initial_rec = initial_rec or "HOLD"
            initial_rationale = initial_rationale or ""

        # Sanitize before reflection so critique doesn't see leaked prompt text
        initial_rationale = _sanitize_rationale(
            initial_rationale, ticker, initial_score, initial_rec
        )

        # Phase 3: reflection loop
        final_score, final_rec, final_rationale = await _run_reflection_loop(
            messages, initial_score, initial_rec or "HOLD", initial_rationale
        )

        # Final sanitize pass — catches anything the reflection loop may have introduced
        final_rationale = _sanitize_rationale(
            final_rationale, ticker, final_score, final_rec
        )

        logger.info(
            "LLM agent loop complete for %s: tool_calls=%d reflection_rounds=%d ai_score=%.1f",
            ticker,
            tool_call_count,
            settings.llm_max_reflection_rounds,
            final_score,
        )

        return final_rationale, final_score, final_rec

    except Exception as exc:
        logger.warning("LLM agent loop failed for %s: %s", ticker, exc)
        return (
            f"Automated analysis for {ticker} is temporarily unavailable. "
            "The numeric risk score reflects the latest market data.",
            None,
            None,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_llm_agent_cycle() -> None:
    """Run the LLM rationale cycle for all tickers that need a rationale."""
    # Build tool schemas and adapter map once per cycle
    try:
        from backend.tool_registry import ToolRegistry

        registry = ToolRegistry.from_config()
        tool_schemas = _build_tool_schemas(registry)
        # Build adapter_map: tool_name → adapter instance
        from backend.adapters import ADAPTER_REGISTRY

        adapter_map: dict = {}
        for tool in registry.get_tools():
            # Find the adapter backing this tool by matching tool_name
            for adapter_name, adapter_cls in ADAPTER_REGISTRY.items():
                instance = adapter_cls()
                if instance.tool_name == tool.name:
                    adapter_map[tool.name] = instance
                    break
    except Exception as exc:
        logger.warning(
            "Failed to build tool registry for LLM cycle: %s — proceeding without tools",
            exc,
        )
        tool_schemas = []
        adapter_map = {}

    async with AsyncSessionLocal() as db:
        candidates = await _get_candidates(db)

    if not candidates:
        logger.info("LLM agent cycle: no candidates to process")
        return

    delta_threshold = settings.llm_delta_threshold
    filtered = [
        (user_id, ticker, score, prev_score)
        for user_id, ticker, score, prev_score in candidates
        if abs(score - prev_score) >= delta_threshold
    ]
    filtered.sort(key=lambda x: abs(x[2] - x[3]), reverse=True)
    filtered = filtered[: settings.llm_max_tickers_per_cycle]

    if not filtered:
        logger.info(
            "LLM agent cycle: all tickers below delta threshold %.1f", delta_threshold
        )
        return

    # Deduplicate by ticker
    ticker_to_users: dict[str, list[tuple[str, float]]] = {}
    for user_id, ticker, score, _ in filtered:
        ticker_to_users.setdefault(ticker, []).append((user_id, score))

    logger.info("LLM agent cycle: %d unique tickers", len(ticker_to_users))

    semaphore = asyncio.Semaphore(settings.llm_concurrency)
    tasks = [
        _process_ticker_for_users(
            ticker, user_scores, semaphore, tool_schemas, adapter_map
        )
        for ticker, user_scores in ticker_to_users.items()
    ]
    await asyncio.gather(*tasks)

    # Portfolio analysis pass — per user
    user_ticker_map: dict[str, list[tuple[str, float]]] = {}
    for user_id, ticker, score, _ in filtered:
        user_ticker_map.setdefault(user_id, []).append((ticker, score))

    portfolio_tasks = [
        _run_portfolio_analysis_for_user(user_id, tickers_scores)
        for user_id, tickers_scores in user_ticker_map.items()
    ]
    await asyncio.gather(*portfolio_tasks)


async def _process_ticker_for_users(
    ticker: str,
    user_scores: list[tuple[str, float]],
    semaphore: asyncio.Semaphore,
    tool_schemas: list[dict],
    adapter_map: dict,
) -> None:
    avg_score = sum(s for _, s in user_scores) / len(user_scores)

    # Load memory from first user (scores are per-user but rationale is shared)
    first_user_id = user_scores[0][0]
    memory = await _load_memory(first_user_id, ticker)

    async with semaphore:
        logger.info("LLM processing ticker: %s (avg_score=%.1f)", ticker, avg_score)
        rationale, ai_risk_score, ai_recommendation = await _generate_rationale(
            ticker, avg_score, memory, tool_schemas, adapter_map
        )
        await asyncio.sleep(12)  # rate limit guard for free-tier models

    now = datetime.now(tz=timezone.utc)
    from backend.ws_manager import ws_manager

    for user_id, _ in user_scores:
        async with AsyncSessionLocal() as db:
            await _persist_rationale(
                db, user_id, ticker, rationale, ai_risk_score, ai_recommendation
            )
        await ws_manager.broadcast_to_user(
            user_id,
            WSEvent(
                event="rationale_update",
                payload={
                    "ticker": ticker,
                    "rationale": rationale,
                    "ai_risk_score": ai_risk_score,
                    "ai_recommendation": ai_recommendation,
                    "rationale_at": now.isoformat(),
                },
            ),
        )


# ---------------------------------------------------------------------------
# Portfolio analysis
# ---------------------------------------------------------------------------


async def run_portfolio_analysis(user_id: str, ticker_data: list[dict]) -> None:
    """Cross-ticker portfolio reasoning. Skips users with < 2 tickers."""
    if len(ticker_data) < 2:
        return

    # Compute concentration flags locally (no LLM needed for the math)
    sector_counts: dict[str, int] = {}
    total = len(ticker_data)
    for td in ticker_data:
        sector = td.get("sector") or "Unknown"
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    concentration_flags = [
        sector for sector, count in sector_counts.items() if count / total > 0.40
    ]

    # Build prompt for LLM summary
    ticker_lines = "\n".join(
        f"- {td['ticker']} (sector={td.get('sector', '?')}, ai_score={td.get('ai_risk_score', '?')}, rec={td.get('ai_recommendation', '?')})"
        for td in ticker_data
    )
    messages = [
        {
            "role": "system",
            "content": "You are a portfolio risk analyst. Output a single concise sentence (max 500 chars) summarising the portfolio's key risks.",
        },
        {
            "role": "user",
            "content": (
                f"Portfolio holdings:\n{ticker_lines}\n\n"
                f"Concentration flags (>40% in one sector): {concentration_flags or 'none'}\n\n"
                f"Output ONE sentence summarising the main portfolio-level risk."
            ),
        },
    ]

    try:
        data = await _call_cerebras(messages)
        choice = data["choices"][0]
        summary_raw = (choice.get("message", {}).get("content") or "").strip()
        summary = summary_raw[:500]
    except Exception as exc:
        logger.warning(
            "Portfolio analysis LLM call failed for user %s: %s", user_id, exc
        )
        summary = (
            f"Portfolio contains {total} holdings across {len(sector_counts)} sectors."
        )

    result = PortfolioAnalysisResult(
        summary=summary, concentration_flags=concentration_flags
    )

    from backend.ws_manager import ws_manager

    await ws_manager.broadcast_to_user(
        user_id,
        WSEvent(
            event="portfolio_analysis",
            payload={
                "summary": result.summary,
                "concentration_flags": result.concentration_flags,
            },
        ),
    )


async def _run_portfolio_analysis_for_user(
    user_id: str,
    tickers_scores: list[tuple[str, float]],
) -> None:
    """Wrapper that loads sector data and calls run_portfolio_analysis with timeout."""
    if len(tickers_scores) < 2:
        return
    try:
        async with AsyncSessionLocal() as db:
            ticker_data = []
            for ticker, score in tickers_scores:
                row = await db.execute(
                    select(StockScoreORM).where(
                        StockScoreORM.user_id == user_id,
                        StockScoreORM.ticker == ticker,
                    )
                )
                score_row = row.scalar_one_or_none()
                data_row = await db.execute(
                    select(StockDataORM).where(StockDataORM.ticker == ticker)
                )
                data_obj = data_row.scalar_one_or_none()
                ticker_data.append(
                    {
                        "ticker": ticker,
                        "sector": data_obj.sector if data_obj else None,
                        "ai_risk_score": float(score_row.ai_risk_score)
                        if score_row and score_row.ai_risk_score
                        else score,
                        "ai_recommendation": score_row.ai_recommendation
                        if score_row
                        else None,
                    }
                )

        await asyncio.wait_for(
            run_portfolio_analysis(user_id, ticker_data),
            timeout=60,
        )
    except asyncio.TimeoutError:
        logger.warning("Portfolio analysis timed out for user %s", user_id)
    except Exception as exc:
        logger.warning("Portfolio analysis failed for user %s: %s", user_id, exc)


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------


async def _load_memory(user_id: str, ticker: str) -> dict | None:
    """Load previous ai_risk_score, ai_recommendation, rationale from stock_scores."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(StockScoreORM).where(
                StockScoreORM.user_id == user_id,
                StockScoreORM.ticker == ticker,
            )
        )
        row = result.scalar_one_or_none()
    if row is None or row.ai_risk_score is None:
        return None
    return {
        "ai_risk_score": float(row.ai_risk_score),
        "ai_recommendation": row.ai_recommendation,
        "rationale": row.rationale,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _get_candidates(db) -> list[tuple[str, str, float, float]]:
    from datetime import timedelta

    result = await db.execute(select(StockScoreORM))
    rows = result.scalars().all()
    now = datetime.now(tz=timezone.utc)
    stale_after = timedelta(hours=1)
    candidates = []
    for row in rows:
        current_score = float(row.risk_score)
        if row.ai_risk_score is None:
            prev_score = -999.0
        elif row.rationale_at is None:
            prev_score = -999.0
        else:
            rationale_age = (
                now - row.rationale_at
                if row.rationale_at.tzinfo is not None
                else now - row.rationale_at.replace(tzinfo=timezone.utc)
            )
            prev_score = -999.0 if rationale_age >= stale_after else current_score
        candidates.append((row.user_id, row.ticker, current_score, prev_score))
    return candidates


async def _persist_rationale(
    db,
    user_id: str,
    ticker: str,
    rationale: str,
    ai_risk_score: float | None,
    ai_recommendation: str | None,
) -> None:
    now = datetime.now(tz=timezone.utc)
    if ai_recommendation is None:
        row = await db.execute(
            select(StockScoreORM.recommendation).where(
                StockScoreORM.user_id == user_id,
                StockScoreORM.ticker == ticker,
            )
        )
        ai_recommendation = row.scalar_one_or_none()

    rationale_at_value = now if ai_risk_score is not None else None
    set_clause = "rationale = :r, ai_risk_score = :ai, ai_recommendation = :airec"
    params: dict = {
        "r": rationale,
        "ai": ai_risk_score,
        "airec": ai_recommendation,
        "uid": user_id,
        "ticker": ticker,
    }
    if rationale_at_value is not None:
        set_clause += ", rationale_at = :t"
        params["t"] = rationale_at_value

    await db.execute(
        text(
            f"UPDATE stock_scores SET {set_clause} WHERE user_id = :uid AND ticker = :ticker"
        ),
        params,
    )
    await db.commit()
