"""Health check endpoint — no auth required."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.db import AsyncSessionLocal

router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    """Liveness + readiness probe. Checks DB connectivity."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok"}, status_code=200)
    except Exception as exc:
        return JSONResponse(
            {"status": "degraded", "detail": str(exc)},
            status_code=503,
        )
