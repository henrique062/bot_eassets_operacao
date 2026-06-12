"""
eAssets scraper control and status endpoints.

Prefix: /api/eassets/scraper  (+ /api/eassets/raw-snapshots)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from database import get_pool
from db import repositories as repo

router = APIRouter(tags=["scraper"])


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


@router.post("/api/eassets/scraper/capture", summary="Trigger a manual scrape")
async def capture_now() -> dict[str, Any]:
    """Trigger an immediate eAssets panel scrape outside the regular interval.

    Returns an immediate acceptance payload; scrape result is reflected in /status.

    Raises:
        HTTPException 409: if a scrape is already running.
        HTTPException 502: if the scrape itself fails.
    """
    from services.eassets_loop import trigger_now
    from services.eassets_scraper import EassetsScrapeError

    pool = get_pool()
    try:
        result = await trigger_now(pool)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EassetsScrapeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _ok(result)


@router.get("/api/eassets/scraper/status", summary="Scraper loop state")
async def scraper_status() -> dict[str, Any]:
    """Return the current state of the background scraper loop.

    Fields:
    - running:      True while a scrape is in progress.
    - last_ok:      ISO timestamp of the last successful capture.
    - last_error:   Last error message, or null.
    - next_run_at:  ISO timestamp when the next automatic scrape is scheduled.
    """
    from services.eassets_loop import get_state
    return _ok(get_state())


@router.get("/api/eassets/raw-snapshots", summary="List raw snapshot records")
async def list_raw_snapshots(
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """Return the most recent raw snapshot records (metadata only, not the full JSON).

    Args:
        limit: Maximum rows to return (1-500).
    """
    pool = get_pool()
    rows = await repo.get_raw_snapshots(pool, limit=limit)
    return _ok(rows)


@router.get("/api/eassets/watchlist", summary="Watchlist entries for a session")
async def get_watchlist(
    config_id: int | None = Query(None, description="Bot session id"),
) -> dict[str, Any]:
    """Return all PCL watchlist entries for a bot session.

    Args:
        config_id: ID of the eassets_bot_config row. Falls back to the latest config.
    """
    resolved_config_id = await _resolve_config_id(config_id)
    if resolved_config_id is None:
        return _ok([])

    pool = get_pool()
    entries = await repo.get_watchlist(pool, resolved_config_id)
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    return _ok(repo.apply_alpha_flags(entries, alpha_symbols))


@router.delete("/api/eassets/watchlist/{config_id}/{symbol}", summary="Remove symbol from watchlist")
async def remove_watchlist_entry(config_id: int, symbol: str) -> dict[str, Any]:
    """Remove a symbol from the PCL watchlist for a session.

    Args:
        config_id: Bot session id.
        symbol:    Trading pair to remove e.g. SOLUSDT.
    """
    pool = get_pool()
    deleted = await repo.remove_from_watchlist(pool, config_id, symbol.upper())
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found in watchlist")
    return _ok({"deleted": True})
