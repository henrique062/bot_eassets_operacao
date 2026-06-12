"""
FastAPI application entry-point for the eAssets/PHOENIX bot API.

Lifespan:
  - Initialises the asyncpg connection pool and runs SQL migrations.
  - Starts the background eAssets scraper loop (if enabled).
  - Tears everything down cleanly on shutdown.

Included routers:
  /api/eassets/bot        — session management (start/stop/status)
  /api/eassets/trades     — trade history and positions
  /api/eassets/config     — bot configuration CRUD
  /api/eassets/scraper    — manual scrape trigger + loop status
  /api/eassets/watchlist  — PCL watchlist management
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from database import close_db, get_pool, init_db


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of shared resources."""
    # --- Startup ---
    logger.info("Starting up...")
    await init_db()
    logger.info("Database ready.")

    # Start background scraper loop
    pool = get_pool()
    from services.eassets_loop import run_loop
    scraper_task = asyncio.create_task(run_loop(pool), name="eassets_loop")
    logger.info("eAssets scraper loop task created.")

    yield

    # --- Shutdown ---
    logger.info("Shutting down...")
    scraper_task.cancel()
    try:
        await scraper_task
    except asyncio.CancelledError:
        pass

    await close_db()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PHOENIX Bot API",
    description="Backend API for the eAssets/PHOENIX automated trading bot.",
    version="1.0.0",
    lifespan=lifespan,
)

# Register routers
from api.routes_bot import router as bot_router
from api.routes_config import router as config_router
from api.routes_panel import router as panel_router
from api.routes_scraper import router as scraper_router
from api.routes_trades import router as trades_router

app.include_router(bot_router)
app.include_router(trades_router)
app.include_router(config_router)
app.include_router(scraper_router)
app.include_router(panel_router)


# ---------------------------------------------------------------------------
# Internal endpoints (called by the Rust core)
# ---------------------------------------------------------------------------

@app.post("/internal/position-update", include_in_schema=False)
async def internal_position_update(request: Request) -> dict[str, Any]:
    """Receive position update notifications from the Rust engine.

    The Rust core calls this endpoint whenever a position is opened,
    updated (e.g. take-profit hit), or closed.
    """
    payload = await request.json()
    logger.info("internal/position-update received: {}", payload)
    # TODO: persist update / emit websocket event
    return {"ok": True}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"], summary="Health check")
async def health() -> dict[str, str]:
    """Return 200 OK when the service is running."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on {} {}", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": str(exc)},
    )
