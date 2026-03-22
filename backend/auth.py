"""Civic Auth integration: router, dependencies, and WebSocket token verification."""
from __future__ import annotations

import logging
import os
from typing import Optional

from civic_auth.auth import CivicAuth
from civic_auth.integrations.fastapi import create_auth_dependencies, create_auth_router, FastAPICookieStorage
from civic_auth.storage import CookieStorage
from civic_auth.types import AuthConfig
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.settings import settings

logger = logging.getLogger(__name__)

_FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

# ---------------------------------------------------------------------------
# Hybrid storage: Bearer header → cookie fallback
# ---------------------------------------------------------------------------


class HeaderOrCookieStorage(CookieStorage):
    """Reads civic_auth_id_token from Authorization: Bearer header first,
    then falls back to the standard cookie. Writes always go to cookies."""

    def __init__(self, request: Request, response: Response) -> None:
        super().__init__({"secure": False})
        self._request = request
        self._response = response
        # Extract Bearer token once
        auth_header = request.headers.get("Authorization", "")
        self._bearer: Optional[str] = (
            auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None
        )

    async def get(self, key: str) -> Optional[str]:
        # For the id_token key, prefer the Bearer header value
        if key == CivicAuth.ID_TOKEN_KEY and self._bearer:
            return self._bearer
        return self._request.cookies.get(key)

    async def set(self, key: str, value: str) -> None:
        self._response.set_cookie(
            key=key,
            value=value,
            max_age=self.settings.get("max_age"),
            secure=self.settings.get("secure", True),
            httponly=self.settings.get("http_only", True),
            samesite=self.settings.get("same_site", "lax"),
            path=self.settings.get("path", "/"),
            domain=self.settings.get("domain"),
        )

    async def delete(self, key: str) -> None:
        self._response.delete_cookie(key=key, path=self.settings.get("path", "/"))

    async def clear(self) -> None:
        for key in self._request.cookies:
            await self.delete(key)


# ---------------------------------------------------------------------------
# Civic Auth config and dependencies
# ---------------------------------------------------------------------------

_config: AuthConfig = {
    "client_id": settings.civic_client_id,
    "redirect_url": os.getenv("AUTH_REDIRECT_URL", "http://localhost:8000/auth/callback"),
}

# Dependency that works with both cookie and Bearer token
async def civic_auth_dep(request: Request, response: Response) -> CivicAuth:
    storage = HeaderOrCookieStorage(request, response)
    return CivicAuth(storage, _config)


async def get_current_user(request: Request, response: Response) -> dict:
    civic = await civic_auth_dep(request, response)
    user = await civic.get_user()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def require_auth(request: Request, response: Response) -> None:
    civic = await civic_auth_dep(request, response)
    if not await civic.is_logged_in():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


# ---------------------------------------------------------------------------
# Auth router
# ---------------------------------------------------------------------------

# Use the civic router for login/logout/user endpoints
_civic_router = create_auth_router(_config)
auth_router = APIRouter()

# Re-register all civic routes except /auth/callback and /auth/user
for route in _civic_router.routes:
    if route.path not in ("/auth/callback", "/auth/user"):  # type: ignore[attr-defined]
        auth_router.routes.append(route)


# Override /auth/user to use our hybrid Bearer+cookie dependency
@auth_router.get("/auth/user")
async def get_user_endpoint(request: Request, response: Response):
    civic = await civic_auth_dep(request, response)
    user = await civic.get_user()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


# Custom callback: resolve code, then redirect to frontend with token in URL fragment
@auth_router.get("/auth/callback")
async def auth_callback(code: str, state: str, request: Request):
    # Capture cookies into a temp response
    temp_response = Response()
    storage = FastAPICookieStorage(request, temp_response)
    civic = CivicAuth(storage, _config)
    try:
        await civic.resolve_oauth_access_code(code, state)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Pass the id_token as a URL fragment — never sent to server, stored by frontend JS
    id_token = await storage.get(CivicAuth.ID_TOKEN_KEY)
    redirect_url = (
        f"{_FRONTEND_ORIGIN}/dashboard#token={id_token}"
        if id_token
        else f"{_FRONTEND_ORIGIN}/dashboard"
    )
    redirect_response = RedirectResponse(url=redirect_url, status_code=302)

    # Copy cookies onto redirect response (keeps local dev working)
    for key, value in temp_response.headers.items():
        if key.lower() == "set-cookie":
            redirect_response.headers.append(key, value)

    return redirect_response


# Token endpoint: returns the id_token so the frontend can store it for Bearer auth
@auth_router.get("/auth/token")
async def get_token(request: Request):
    """Return the Civic id_token from the cookie so the frontend can use Bearer auth."""
    token = request.cookies.get(CivicAuth.ID_TOKEN_KEY)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return {"token": token}


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

