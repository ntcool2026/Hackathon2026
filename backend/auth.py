"""Civic Auth integration: router, dependencies, and WebSocket token verification."""
from __future__ import annotations

import logging
import os

from civic_auth.integrations.fastapi import create_auth_dependencies, create_auth_router, FastAPICookieStorage, CivicAuth
from civic_auth.types import AuthConfig
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.settings import settings

logger = logging.getLogger(__name__)

_FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

# ---------------------------------------------------------------------------
# Civic Auth router and FastAPI dependencies
# ---------------------------------------------------------------------------

_config: AuthConfig = {
    "client_id": settings.civic_client_id,
    "redirect_url": os.getenv("AUTH_REDIRECT_URL", "http://localhost:8000/auth/callback"),
}

_COOKIE_SETTINGS: dict = {
    "secure": True,
    "same_site": "none",
    "http_only": True,
}

# Use the civic router but override the callback to redirect to frontend
_civic_router = create_auth_router(_config)
civic_auth_dep, get_current_user, require_auth = create_auth_dependencies(_config)

# Build our own router that includes all civic routes except callback and user
auth_router = APIRouter()

# Re-register all civic routes except /auth/callback and /auth/user
for route in _civic_router.routes:
    if route.path not in ("/auth/callback", "/auth/user"):  # type: ignore[attr-defined]
        auth_router.routes.append(route)

# Custom callback that redirects to frontend after auth
@auth_router.get("/auth/callback")
async def auth_callback(code: str, state: str, request: Request):
    redirect_response = RedirectResponse(url=f"{_FRONTEND_ORIGIN}/dashboard", status_code=302)
    storage = FastAPICookieStorage(request, redirect_response, settings=_COOKIE_SETTINGS)
    civic = CivicAuth(storage, _config)
    try:
        await civic.resolve_oauth_access_code(code, state)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return redirect_response


@auth_router.get("/auth/user")
async def auth_user(request: Request, response: Response):
    storage = FastAPICookieStorage(request, response, settings=_COOKIE_SETTINGS)
    civic = CivicAuth(storage, _config)
    user = await civic.get_user()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


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

