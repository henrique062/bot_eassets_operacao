"""
HTTP client for the Rust core service.

All communication with the Rust bot engine goes through this module.
Configured via RUST_CORE_URL env var (default: http://rust_core:8001).
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from config import RUST_CORE_URL

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


async def start(config_id: int, config_data: dict[str, Any]) -> dict[str, Any]:
    """Tell the Rust engine to start a bot session.

    Args:
        config_id: ID of the eassets_bot_config row.
        config_data: Full config dict to send as request body.

    Returns:
        Parsed JSON response from the Rust core.
    """
    payload = {"config_id": config_id, **config_data}
    logger.info("rust_bridge.start config_id={}", config_id)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{RUST_CORE_URL}/internal/start", json=payload)
        resp.raise_for_status()
        return resp.json()


async def stop(config_id: int) -> dict[str, Any]:
    """Tell the Rust engine to stop a bot session.

    Args:
        config_id: ID of the session to stop.

    Returns:
        Parsed JSON response from the Rust core.
    """
    logger.info("rust_bridge.stop config_id={}", config_id)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{RUST_CORE_URL}/internal/stop",
            json={"config_id": config_id},
        )
        resp.raise_for_status()
        return resp.json()


async def update_config(config_data: dict[str, Any]) -> dict[str, Any]:
    """Push a config update to the Rust engine (hot-reload).

    Args:
        config_data: Updated config dict.

    Returns:
        Parsed JSON response from the Rust core.
    """
    logger.info("rust_bridge.update_config")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{RUST_CORE_URL}/internal/config", json=config_data)
        resp.raise_for_status()
        return resp.json()


async def get_status() -> dict[str, Any]:
    """Fetch the current status from the Rust engine.

    Returns:
        Parsed JSON response with running sessions, positions, etc.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{RUST_CORE_URL}/internal/status")
        resp.raise_for_status()
        return resp.json()


async def notify_snapshot(snap_id: int) -> None:
    """Notify the Rust engine that a new eassets snapshot is available.

    The engine uses this to re-score open watchlist positions.

    Args:
        snap_id: ID of the newly inserted eassets_snapshots row.
    """
    logger.debug("rust_bridge.notify_snapshot snap_id={}", snap_id)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{RUST_CORE_URL}/internal/snapshot-updated",
                params={"snap_id": snap_id},
            )
            resp.raise_for_status()
    except Exception as exc:
        # Non-critical — Rust may not be running
        logger.warning("rust_bridge.notify_snapshot failed: {}", exc)
