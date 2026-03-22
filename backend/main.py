"""FastAPI application entry point: lifespan, scheduler, routers, middleware."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.settings import settings
from backend.limiter import limiter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scheduler helpers
# ---------------------------------------------------------------------------


def _parse_refresh_interval() -> int:
    raw = os.getenv("REFRESH_INTERVAL_MINUTES", "30")
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError("must be positive")
        return value
    except (ValueError, TypeError):
        logger.error(
            "Invalid REFRESH_INTERVAL_MINUTES='%s'; falling back to 30 minutes", raw
        )
        return 30


async def _run_refresh_cycle_inner() -> None:
    from backend.agent import run_data_pipeline
    from backend.llm_agent import run_llm_agent_cycle

    await run_data_pipeline()
    await run_llm_agent_cycle()


async def run_refresh_cycle() -> None:
    """Single scheduler job: Layer 1 then Layer 2, with overall timeout guard."""
    timeout_seconds = settings.refresh_cycle_timeout_minutes * 60
    try:
        await asyncio.wait_for(_run_refresh_cycle_inner(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(
            "Refresh cycle timed out after %d minutes — cycle cancelled",
            settings.refresh_cycle_timeout_minutes,
        )
    except Exception as exc:
        logger.exception("Refresh cycle failed: %s", exc)


async def run_history_cleanup() -> None:
    """Daily job: delete stock_score_history rows older than retention policy."""
    from sqlalchemy import text
    from backend.db import AsyncSessionLocal

    retention_days = settings.score_history_retention_days
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("DELETE FROM stock_score_history WHERE computed_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await db.commit()
    logger.info("History cleanup: deleted rows older than %s", cutoff.date())


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_interval = _parse_refresh_interval()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_refresh_cycle,
        trigger=IntervalTrigger(minutes=refresh_interval),
        id="refresh_cycle",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_history_cleanup,
        trigger=CronTrigger(hour=3, minute=0),
        id="history_cleanup",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("Scheduler started (refresh every %d min)", refresh_interval)
    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Stock Portfolio Advisor", lifespan=lifespan)

# Handle Chrome's private network access preflight
@app.middleware("http")
async def private_network_access(request: Request, call_next):
    response = await call_next(request)
    if request.method == "OPTIONS":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow frontend origin(s) (configure via env in production)
_frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
# Support comma-separated list of origins for multi-environment setups
_allowed_origins = [o.strip() for o in _frontend_origin.split(",") if o.strip()]
_allowed_origins.append("http://localhost:8000")
_allowed_origins.append("http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=r"https://.*\.onrender\.com",
)

# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

from backend.auth import auth_router
from backend.ws_manager import ws_router
from backend.routers.health import router as health_router
from backend.routers.portfolios import router as portfolios_router
from backend.routers.stocks import router as stocks_router
from backend.routers.preferences import router as preferences_router
from backend.routers.criteria import router as criteria_router
from backend.routers.scores import router as scores_router
from backend.routers.thresholds import router as thresholds_router
from backend.routers.chat import router as chat_router

app.include_router(auth_router)
app.include_router(ws_router)
app.include_router(health_router)
app.include_router(portfolios_router)
app.include_router(stocks_router)
app.include_router(preferences_router)
app.include_router(criteria_router)
app.include_router(scores_router)
app.include_router(thresholds_router)
app.include_router(chat_router)
