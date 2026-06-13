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

async def _resume_active_sessions(pool: Any) -> None:
    """Reinstrui o motor Rust a retomar as sessões marcadas como ativas no banco.

    O engine Rust começa Stopped após cada restart; aqui restauramos o estado.
    Best-effort: aguarda o Rust subir e ignora falhas (não bloqueia o startup).
    """
    from decimal import Decimal

    from db import repositories as repo
    from services import rust_bridge

    # Campos que o motor Rust lê em /internal/start (evita enviar datetime/etc).
    keys = (
        "session_name", "capital", "leverage", "max_positions", "min_score",
        "min_tpm", "max_lsr", "max_rsi_btc", "stop_loss_pct", "take_profit_pct",
        "trailing_stop_pct", "trailing_start_pct", "pcl_enabled",
        "pcl_cooldown_minutes", "pcl_max_attempts", "pcl_min_struct_score",
        "paper_trading", "require_btc_reset", "allow_partial_setup",
        "require_funding_negative",
    )

    await asyncio.sleep(5)  # dá tempo do rust_core subir
    try:
        sessions = await repo.get_active_configs(pool)
    except Exception as exc:
        logger.warning("auto-resume: falha ao ler sessões ativas: {}", exc)
        return

    for s in sessions:
        config_id = s.get("id")
        config_data: dict[str, Any] = {}
        for k in keys:
            v = s.get(k)
            config_data[k] = float(v) if isinstance(v, Decimal) else v
        for attempt in range(3):
            try:
                await rust_bridge.start(config_id, config_data)
                logger.info("auto-resume: sessão {} retomada no motor (paper={})",
                            config_id, s.get("paper_trading"))
                break
            except Exception as exc:
                logger.warning("auto-resume: tentativa {} falhou p/ sessão {}: {}",
                               attempt + 1, config_id, exc)
                await asyncio.sleep(5)


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

    # Auto-resume: religa no motor Rust as sessões que estavam ativas no banco
    # (o engine Rust perde o estado em memória a cada restart/redeploy).
    resume_task = asyncio.create_task(_resume_active_sessions(pool), name="resume_sessions")

    yield

    resume_task.cancel()
    try:
        await resume_task
    except asyncio.CancelledError:
        pass

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
