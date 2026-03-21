"""Chat router: conversational interface for portfolio questions."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from backend.auth import get_current_user, get_or_create_user, require_auth
from backend.db import AsyncSessionLocal, get_db
from backend.limiter import limiter
from backend.models import ChatRequest, ChatResponse
from backend.models_orm import StockScore as StockScoreORM
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/chat", dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)

# In-memory session store: user_id → list of message dicts (role/content)
_chat_sessions: dict[str, list[dict[str, str]]] = {}
_MAX_TURNS = 5  # 5 user + 5 assistant = 10 messages max

_NO_HOLDINGS_REPLY = (
    "You have no holdings in your portfolio yet. Add some tickers to get started."
)


def _trim_history(history: list[dict]) -> list[dict]:
    """Keep at most _MAX_TURNS turns (2 messages per turn)."""
    max_messages = _MAX_TURNS * 2
    if len(history) > max_messages:
        return history[-max_messages:]
    return history


async def _load_portfolio_context(user_id: str) -> list[dict[str, Any]]:
    """Load current scores for all user tickers."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(StockScoreORM).where(StockScoreORM.user_id == user_id)
        )
        rows = result.scalars().all()
    return [
        {
            "ticker": row.ticker,
            "ai_risk_score": float(row.ai_risk_score) if row.ai_risk_score is not None else float(row.risk_score),
            "ai_recommendation": row.ai_recommendation or (row.recommendation.value if hasattr(row.recommendation, "value") else row.recommendation),
            "rationale": row.rationale or "",
        }
        for row in rows
    ]


def _build_chat_system_prompt(portfolio: list[dict]) -> str:
    if not portfolio:
        return "You are a helpful portfolio advisor. The user has no holdings yet."

    holdings = "\n".join(
        f"- {h['ticker']}: score={h['ai_risk_score']:.1f}, "
        f"recommendation={h['ai_recommendation']}, "
        f"rationale={h['rationale'][:200]}"
        for h in portfolio
    )
    return (
        "You are a helpful portfolio advisor. Answer the user's questions about their portfolio.\n\n"
        f"Current holdings:\n{holdings}"
    )


@router.post("", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    user_id: str = await get_or_create_user(user, db)

    portfolio = await _load_portfolio_context(user_id)

    if not portfolio:
        return ChatResponse(answer=_NO_HOLDINGS_REPLY)

    # Load or initialise session history
    history = _chat_sessions.get(user_id, [])

    # Append user message
    history.append({"role": "user", "content": body.message})

    # Build messages for OpenRouter
    system_prompt = _build_chat_system_prompt(portfolio)
    messages = [{"role": "system", "content": system_prompt}] + history

    try:
        from backend.llm_agent import _call_openrouter_with_tools
        data = await _call_openrouter_with_tools(messages)
        choice = data["choices"][0]
        answer = (choice.get("message", {}).get("content") or "").strip()
        if not answer:
            answer = "I wasn't able to generate a response. Please try again."
    except Exception as exc:
        logger.warning("Chat LLM call failed for user %s: %s", user_id, exc)
        answer = "I'm having trouble connecting to the analysis service right now. Please try again shortly."

    # Append assistant reply and trim history
    history.append({"role": "assistant", "content": answer})
    _chat_sessions[user_id] = _trim_history(history)

    return ChatResponse(answer=answer)
