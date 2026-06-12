"""
Trade history and positions endpoints.

Prefix: /api/eassets
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from loguru import logger

from database import get_pool
from db import repositories as repo
from services.bybit_account import get_open_positions

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
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    return _ok(repo.apply_alpha_flags(positions, alpha_symbols))


@router.get("/positions/live", summary="List live Bybit open positions")
async def list_live_positions(
    config_id: int | None = Query(None, description="Bot session id used for origin matching"),
) -> dict[str, Any]:
    """Return real-time open account positions split by origin.

    Bybit is the source of truth for currently open positions. The local bot DB
    is used only to classify matching symbols/directions as BOT; everything
    else is marked MANUAL.
    """
    resolved_config_id = config_id
    pool = get_pool()
    try:
        bot_lookup = await repo.get_open_position_lookup(pool, resolved_config_id)
    except Exception as exc:
        logger.warning("Failed to classify live positions against bot DB: {}", exc)
        bot_lookup = {}
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    account = await get_open_positions()

    positions: list[dict[str, Any]] = []
    for position in account.get("positions", []):  # type: ignore[union-attr]
        item = dict(position)
        symbol = str(item.get("symbol") or "").upper()
        direction = str(item.get("direction") or "").upper()
        bot_position = bot_lookup.get(f"{symbol}:{direction}") or bot_lookup.get(symbol)
        item["source"] = "BOT" if bot_position else "MANUAL"
        item["source_config_id"] = bot_position.get("config_id") if bot_position else None
        item["bot_position_id"] = bot_position.get("id") if bot_position else None
        item["is_alpha"] = repo.normalize_symbol(symbol) in alpha_symbols
        positions.append(item)

    bot_count = sum(1 for p in positions if p.get("source") == "BOT")
    manual_count = len(positions) - bot_count

    return _ok({
        "connected": account.get("connected", False),
        "error": account.get("error"),
        "fetched_at": account.get("fetched_at"),
        "bot_count": bot_count,
        "manual_count": manual_count,
        "positions": positions,
    })


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
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    return _ok(repo.apply_alpha_flags(trades, alpha_symbols))


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
    trades = await repo.get_trades_by_symbol(pool, repo.normalize_symbol(symbol), limit=limit)
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    return _ok(repo.apply_alpha_flags(trades, alpha_symbols))


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
