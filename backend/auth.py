"""Civic Auth integration: router, dependencies, and WebSocket token verification."""
from __future__ import annotations

import logging

from civic_auth.integrations.fastapi import create_auth_dependencies, create_auth_router
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Civic Auth router and FastAPI dependencies
# ---------------------------------------------------------------------------

auth_router = create_auth_router(client_id=settings.civic_client_id)
get_current_user, require_auth = create_auth_dependencies()


# ---------------------------------------------------------------------------
# User upsert helper
# ---------------------------------------------------------------------------


async def get_or_create_user(user: dict, db: AsyncSession) -> str:
    """Upsert a user row keyed on the Civic-provided user ID.

    Returns the user_id string.
    """
    user_id: str = user.get("id", "")
    if not user_id:
        raise ValueError("Civic user dict missing 'id' field")
    await db.execute(
        text("INSERT INTO users (id) VALUES (:uid) ON CONFLICT (id) DO NOTHING"),
        {"uid": user_id},
    )
    await db.commit()
    return user_id


# ---------------------------------------------------------------------------
# WebSocket token verification
# ---------------------------------------------------------------------------


async def verify_civic_token(token: str) -> dict:
    """Validate a Civic token passed as a WebSocket query parameter.

    Returns the user dict on success; raises an exception on failure.
    The civic-auth SDK exposes a verify helper — we call it here so the
    WebSocket endpoint can close with code 4001 on any exception.
    """
    from civic_auth import verify_token  # type: ignore[import]

    return await verify_token(token, client_id=settings.civic_client_id)
