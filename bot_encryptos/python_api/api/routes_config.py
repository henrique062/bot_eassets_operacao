"""
Bot configuration CRUD endpoints.

Prefix: /api/eassets/config
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import get_pool
from db import repositories as repo
from services.bybit_account import get_wallet_balance

router = APIRouter(prefix="/api/eassets/config", tags=["config"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BotConfigPayload(BaseModel):
    """Request body for creating a new bot configuration."""

    session_name: str
    exchange: str = "bybit"
    capital: float = Field(..., gt=0)
    balance: float = Field(..., gt=0)
    leverage: int = Field(5, ge=1, le=100)
    fee_type: str = "maker"
    fee_rate: float = Field(0.0002, ge=0)
    min_tpm: int = Field(800, ge=0)
    min_oi_trend: float = 0.0
    max_lsr: float = 1.0
    min_rsi_btc: float | None = None
    max_rsi_btc: float | None = 40.0
    min_exp_btc: float = 0.0
    max_positions: int = Field(5, ge=1, le=50)
    min_score: float = Field(65.0, ge=0, le=100)
    stop_loss_pct: float | None = None
    stop_loss_usd: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    trailing_start_pct: float | None = None
    break_even_at_pct: float | None = None
    entry_seconds: int = Field(30, ge=1)
    exit_seconds: int = Field(30, ge=1)
    pcl_enabled: bool = True
    pcl_cooldown_minutes: int = Field(30, ge=1)
    pcl_max_attempts: int = Field(3, ge=1)
    pcl_min_struct_score: int = Field(3, ge=0)
    pcl_profit_target_usd: float | None = None
    user_id: int | None = None


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", summary="Create a new bot configuration")
async def create_config(body: BotConfigPayload) -> dict[str, Any]:
    """Insert a new eassets_bot_config row and return the generated id.

    This endpoint only creates the config record — to start the bot engine
    use POST /api/eassets/bot/start instead.
    """
    pool = get_pool()
    config_id = await repo.save_config(pool, body.model_dump())
    return _ok({"config_id": config_id})


@router.get("/latest", summary="Read the latest bot configuration")
async def get_latest_config() -> dict[str, Any]:
    """Return the most recent bot configuration, preferring an active session."""
    pool = get_pool()
    config = await repo.get_latest_config(pool)
    if config is None:
        raise HTTPException(status_code=404, detail="No config found")
    return _ok(config)


@router.get("/bybit/balance", summary="Read current Bybit wallet balances")
async def get_bybit_balance() -> dict[str, Any]:
    """Return live capital/balance values derived from the configured Bybit account."""
    balance = await get_wallet_balance()
    return _ok(balance)


@router.get("/{config_id}", summary="Read a bot configuration")
async def get_config(config_id: int) -> dict[str, Any]:
    """Return a single eassets_bot_config row.

    Args:
        config_id: ID of the configuration to retrieve.
    """
    pool = get_pool()
    config = await repo.get_config(pool, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")
    return _ok(config)


@router.put("/{config_id}", summary="Update an existing bot configuration")
async def update_config(config_id: int, body: BotConfigPayload) -> dict[str, Any]:
    """Update a bot configuration row in-place."""
    pool = get_pool()
    updated = await repo.update_config(pool, config_id, body.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Config not found")
    return _ok({"config_id": config_id})
