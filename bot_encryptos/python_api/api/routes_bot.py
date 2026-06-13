"""
Bot session management endpoints.

Prefix: /api/eassets/bot
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from database import get_pool
from db import repositories as repo
from services import rust_bridge
from services.bybit_account import get_wallet_balance

router = APIRouter(prefix="/api/eassets/bot", tags=["bot"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StartBotRequest(BaseModel):
    session_name: str
    exchange: str = "bybit"
    capital: float
    balance: float
    leverage: int = 5
    fee_type: str = "maker"
    fee_rate: float = 0.0002
    min_tpm: int = 800
    min_oi_trend: float = 0.0
    max_lsr: float = 1.0
    min_rsi_btc: float | None = None
    max_rsi_btc: float | None = 40.0
    min_exp_btc: float = 0.0
    max_positions: int = 5
    min_score: float = 65.0
    stop_loss_pct: float | None = None
    stop_loss_usd: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    trailing_start_pct: float | None = None
    break_even_at_pct: float | None = None
    entry_seconds: int = 30
    exit_seconds: int = 30
    pcl_enabled: bool = True
    pcl_cooldown_minutes: int = 30
    pcl_max_attempts: int = 3
    pcl_min_struct_score: int = 3
    pcl_profit_target_usd: float | None = None
    user_id: int | None = None
    paper_trading: bool = True
    require_btc_reset: bool = True
    allow_partial_setup: bool = False
    require_funding_negative: bool = False


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start", summary="Start a new bot session")
async def start_bot(body: StartBotRequest) -> dict[str, Any]:
    """Create a new eassets_bot_config row and instruct the Rust engine to start trading.

    Returns the generated config_id.
    """
    pool = get_pool()
    config_data = body.model_dump()

    if config_data.get("exchange", "bybit").lower() == "bybit" and not body.paper_trading:
        bybit_balance = await get_wallet_balance()
        if not bybit_balance.get("connected"):
            raise HTTPException(
                status_code=502,
                detail=str(bybit_balance.get("error") or "Saldo Bybit indisponivel."),
            )

        config_data["capital"] = bybit_balance["capital"]
        config_data["balance"] = bybit_balance["balance"]

    config_id = await repo.save_config(pool, config_data)
    logger.info("Bot session created config_id={}", config_id)

    try:
        await rust_bridge.start(config_id, config_data)
    except Exception as exc:
        logger.error("rust_bridge.start failed for config_id={}: {}", config_id, exc)
        raise HTTPException(status_code=502, detail=f"Rust core unreachable: {exc}") from exc

    await repo.set_config_active(pool, config_id, True)

    return _ok({"config_id": config_id, "session_name": body.session_name})


@router.post("/stop/{config_id}", summary="Stop a bot session")
async def stop_bot(config_id: int) -> dict[str, Any]:
    """Instruct the Rust engine to stop the given session.

    Args:
        config_id: ID of the eassets_bot_config row to stop.
    """
    try:
        result = await rust_bridge.stop(config_id)
    except Exception as exc:
        logger.error("rust_bridge.stop failed config_id={}: {}", config_id, exc)
        raise HTTPException(status_code=502, detail=f"Rust core unreachable: {exc}") from exc

    pool = get_pool()
    await repo.set_config_active(pool, config_id, False)

    return _ok(result)


@router.get("/status", summary="List all active sessions")
async def list_active_sessions() -> dict[str, Any]:
    """Return all bot sessions with active=TRUE."""
    pool = get_pool()
    sessions = await repo.get_active_configs(pool)
    return _ok(sessions)


@router.get("/status/{config_id}", summary="Detailed status for one session")
async def session_status(config_id: int) -> dict[str, Any]:
    """Return config, open positions, and cumulative PnL for a session.

    Args:
        config_id: ID of the session.
    """
    pool = get_pool()
    config = await repo.get_config(pool, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Session not found")

    positions = await repo.get_positions(pool, config_id)
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    positions = repo.apply_alpha_flags(positions, alpha_symbols)
    total_pnl = sum(float(p.get("total_pnl") or 0) for p in positions)

    return _ok({
        "config": config,
        "positions": positions,
        "open_positions": len(positions),
        "unrealised_pnl": total_pnl,
    })


@router.get("/market/signals", summary="Score of all tracked symbols")
async def market_signals() -> dict[str, Any]:
    """Return the latest per-symbol metrics ordered by score.

    Reads from the most recent eassets_metrics snapshot.
    """
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT m.*
        FROM eassets_metrics m
        INNER JOIN (
            SELECT MAX(id) AS max_id FROM eassets_snapshots
        ) s ON m.snapshot_id = s.max_id
        ORDER BY m.rank ASC NULLS LAST
        LIMIT 200
        """
    )
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    return _ok(repo.apply_alpha_flags([dict(r) for r in rows], alpha_symbols))


@router.get("/market/btc-status", summary="Current BTC RSI state")
async def btc_status() -> dict[str, Any]:
    """Return the latest BTC metrics from the most recent snapshot."""
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT m.*
        FROM eassets_metrics m
        INNER JOIN (
            SELECT MAX(id) AS max_id FROM eassets_snapshots
        ) s ON m.snapshot_id = s.max_id
        WHERE m.symbol = 'BTCUSDT'
        LIMIT 1
        """
    )
    if not row:
        return _ok(None)
    return _ok(dict(row))
