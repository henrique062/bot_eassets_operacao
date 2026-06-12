"""
Trade history and positions endpoints.

Prefix: /api/eassets
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from database import get_pool
from db import repositories as repo

router = APIRouter(prefix="/api/eassets", tags=["trades"])


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


async def _resolve_config_id(config_id: int | None) -> int | None:
    if config_id is not None:
        return config_id

    pool = get_pool()
    latest_config = await repo.get_latest_config(pool)
    if latest_config is None:
        return None

    return int(latest_config["id"])


@router.get("/positions", summary="List open positions")
async def list_positions(
    config_id: int | None = Query(None, description="Bot session id"),
) -> dict[str, Any]:
    """Return all open positions for a bot session.

    Args:
        config_id: ID of the eassets_bot_config row. Falls back to the latest config.
    """
    resolved_config_id = await _resolve_config_id(config_id)
    if resolved_config_id is None:
        return _ok([])

    pool = get_pool()
    positions = await repo.get_positions(pool, resolved_config_id)
    return _ok(positions)


@router.get("/trades", summary="Paginated trade history")
async def list_trades(
    config_id: int | None = Query(None, description="Bot session id"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """Return paginated closed trades for a bot session.

    Args:
        config_id: Bot session id. Falls back to the latest config.
        skip:      Number of rows to skip.
        limit:     Maximum rows to return (1-500).
    """
    resolved_config_id = await _resolve_config_id(config_id)
    if resolved_config_id is None:
        return _ok([])

    pool = get_pool()
    trades = await repo.get_trades(pool, resolved_config_id, skip=skip, limit=limit)
    return _ok(trades)


@router.get("/trades/{symbol}", summary="Trades for a specific symbol")
async def trades_by_symbol(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    """Return the most recent trades for a given symbol across all sessions.

    Args:
        symbol: Trading pair e.g. BTCUSDT.
        limit:  Maximum rows to return.
    """
    pool = get_pool()
    trades = await repo.get_trades_by_symbol(pool, symbol.upper(), limit=limit)
    return _ok(trades)


@router.get("/logs/{config_id}", summary="Order event logs for a session")
async def order_logs(
    config_id: int,
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    """Return order event logs for a bot session ordered by newest first.

    Args:
        config_id: Bot session id.
        limit:     Maximum rows to return.
    """
    pool = get_pool()
    logs = await repo.get_logs(pool, config_id, limit=limit)
    return _ok(logs)
