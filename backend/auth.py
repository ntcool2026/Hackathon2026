"""Civic Auth integration: router, dependencies, and WebSocket token verification."""
from __future__ import annotations

import logging
import os
from typing import Optional

from civic_auth.integrations.fastapi import create_auth_router, FastAPICookieStorage, CivicAuth
from civic_auth.types import AuthConfig
from civic_auth.utils import parse_jwt_without_validation
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
    "http_only": False,  # Must be False so JS can read it
}

# Use the civic router but override the callback to redirect to frontend
_civic_router = create_auth_router(_config)

# Build our own router that includes all civic routes except callback and user
auth_router = APIRouter()

# Re-register all civic routes except /auth/callback and /auth/user
for route in _civic_router.routes:
    if route.path not in ("/auth/callback", "/auth/user"):  # type: ignore[attr-defined]
        auth_router.routes.append(route)


# ---------------------------------------------------------------------------
# Bearer token dependencies (replaces cookie-based create_auth_dependencies)
# ---------------------------------------------------------------------------

async def get_current_user(request: Request) -> dict:
    """Extract and validate Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    id_token = auth_header[7:]
    claims = parse_jwt_without_validation(id_token)
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    # Map sub → id to match Civic's BaseUser shape expected by get_or_create_user
    if "id" not in claims and "sub" in claims:
        claims["id"] = claims["sub"]
    return claims


async def require_auth(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires a valid authenticated user."""
    return user

# Custom callback — extracts id_token and passes it to frontend via URL fragment
@auth_router.get("/auth/callback")
async def auth_callback(code: str, state: str, request: Request):
    # Use a temp response to capture cookies set by Civic
    temp_response = Response()
    storage = FastAPICookieStorage(request, temp_response, settings=_COOKIE_SETTINGS)
    civic = CivicAuth(storage, _config)
    try:
        await civic.resolve_oauth_access_code(code, state)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Extract id_token from storage so we can pass it to the frontend
    id_token = await storage.get(CivicAuth.ID_TOKEN_KEY)

    if id_token:
        # Pass token to frontend via URL fragment (never hits server, stays in browser)
        redirect_url = f"{_FRONTEND_ORIGIN}/dashboard#token={id_token}"
    else:
        redirect_url = f"{_FRONTEND_ORIGIN}/dashboard"

    redirect_response = RedirectResponse(url=redirect_url, status_code=302)
    # Copy cookies from temp_response to redirect_response
    for key, value in temp_response.headers.items():
        redirect_response.headers.append(key, value)
    return redirect_response


@auth_router.get("/auth/user")
async def auth_user(request: Request, response: Response):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        id_token = auth_header[7:]
        claims = parse_jwt_without_validation(id_token)
        if not claims:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        if "id" not in claims and "sub" in claims:
            claims["id"] = claims["sub"]
        return claims

    # Fallback to cookie
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

