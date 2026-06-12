"""
Background asyncio loop that periodically scrapes the eAssets panel and
ingests the data into PostgreSQL.

Run standalone (Docker scraper service):
    python -m services.eassets_loop

Or embed in the FastAPI lifespan:
    asyncio.create_task(run_loop(pool))
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from config import (
    EASSETS_AUTO_ENABLED,
    EASSETS_EMAIL,
    EASSETS_HEADLESS,
    EASSETS_INTERVAL_SECONDS,
    EASSETS_PASSWORD,
    EASSETS_TIMEOUT_MS,
    RUST_CORE_URL,
)

# ---------------------------------------------------------------------------
# Shared state — readable from the /scraper/status endpoint
# ---------------------------------------------------------------------------
_state: dict[str, Any] = {
    "running": False,
    "last_ok": None,      # ISO timestamp of last successful capture
    "last_error": None,   # last error message string
    "next_run_at": None,  # ISO timestamp of next scheduled run
}
_manual_scrape_task: asyncio.Task[None] | None = None

_RETRY_DELAY_SECONDS = 300  # 5 minutes on error


def get_state() -> dict[str, Any]:
    """Return a shallow copy of the current loop state."""
    return dict(_state)


async def run_loop(pool) -> None:  # noqa: ANN001
    """Infinite loop: scrape → ingest → sleep → repeat.

    Args:
        pool: asyncpg.Pool — passed in from the FastAPI lifespan or __main__.
    """
    from services.eassets_scraper import EassetsScrapeError, ingest_snapshot, scrape_eassets_json

    if not EASSETS_AUTO_ENABLED:
        logger.info("eAssets auto-scrape disabled (EASSETS_AUTO_ENABLED=0). Loop not started.")
        return

    logger.info(
        "eAssets loop started — interval={}s headless={} timeout_ms={}",
        EASSETS_INTERVAL_SECONDS,
        EASSETS_HEADLESS,
        EASSETS_TIMEOUT_MS,
    )

    while True:
        _state["running"] = True
        _state["next_run_at"] = None

        try:
            logger.info("Starting eAssets scrape...")
            loop = asyncio.get_event_loop()

            # Run the synchronous Playwright scraper in a thread pool executor
            # so it doesn't block the asyncio event loop.
            data, raw_json = await loop.run_in_executor(
                None,
                lambda: scrape_eassets_json(
                    email=EASSETS_EMAIL,
                    password=EASSETS_PASSWORD,
                    headless=EASSETS_HEADLESS,
                    timeout_ms=EASSETS_TIMEOUT_MS,
                ),
            )

            snap_id = await ingest_snapshot(data, raw_json, pool, RUST_CORE_URL)
            now_iso = datetime.now(timezone.utc).isoformat()
            _state["last_ok"] = now_iso
            _state["last_error"] = None
            logger.info("eAssets scrape OK — snap_id={} symbols={}", snap_id, data.get("symbols"))

            sleep_seconds = EASSETS_INTERVAL_SECONDS

        except EassetsScrapeError as exc:
            _state["last_error"] = str(exc)
            logger.error("eAssets scrape failed: {}. Retrying in {}s.", exc, _RETRY_DELAY_SECONDS)
            sleep_seconds = _RETRY_DELAY_SECONDS

        except Exception as exc:
            _state["last_error"] = str(exc)
            logger.exception("Unexpected error in eAssets loop. Retrying in {}s.", _RETRY_DELAY_SECONDS)
            sleep_seconds = _RETRY_DELAY_SECONDS

        finally:
            _state["running"] = False

        next_run = datetime.now(timezone.utc).timestamp() + sleep_seconds
        _state["next_run_at"] = datetime.fromtimestamp(next_run, tz=timezone.utc).isoformat()
        logger.debug("Next eAssets scrape in {}s", sleep_seconds)
        await asyncio.sleep(sleep_seconds)


async def trigger_now(pool) -> dict[str, Any]:  # noqa: ANN001
    """Trigger an immediate scrape outside of the regular loop interval.

    Args:
        pool: asyncpg.Pool.

    Returns:
        dict signalling that the manual scrape was accepted.

    Raises:
        RuntimeError: if a scrape is already in progress.
    """
    global _manual_scrape_task

    from services.eassets_scraper import ingest_snapshot, scrape_eassets_json

    if _state["running"] or (_manual_scrape_task and not _manual_scrape_task.done()):
        raise RuntimeError("A scrape is already in progress.")

    async def _worker() -> None:
        _state["running"] = True
        try:
            loop = asyncio.get_event_loop()
            data, raw_json = await loop.run_in_executor(
                None,
                lambda: scrape_eassets_json(
                    email=EASSETS_EMAIL,
                    password=EASSETS_PASSWORD,
                    headless=EASSETS_HEADLESS,
                    timeout_ms=EASSETS_TIMEOUT_MS,
                ),
            )
            snap_id = await ingest_snapshot(data, raw_json, pool, RUST_CORE_URL)
            _state["last_ok"] = datetime.now(timezone.utc).isoformat()
            _state["last_error"] = None
            logger.info(
                "Manual eAssets scrape OK - snap_id={} symbols={}",
                snap_id,
                data.get("symbols"),
            )
        except Exception as exc:
            _state["last_error"] = str(exc)
            logger.exception("Manual eAssets scrape failed.")
        finally:
            _state["running"] = False

    _manual_scrape_task = asyncio.create_task(_worker(), name="manual_eassets_scrape")
    return {"accepted": True}


# ---------------------------------------------------------------------------
# Standalone entry-point (Docker scraper service)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncpg

    from config import DATABASE_URL

    async def _main() -> None:
        pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=5)
        try:
            await run_loop(pool)
        finally:
            await pool.close()

    asyncio.run(_main())
