#!/usr/bin/env python3
"""
One-shot migration script: SQLite → PostgreSQL.

Reads trading_bot.db (path via SQLITE_DB_PATH env var) and migrates:
  - trades      → eassets_trades
  - positions   → eassets_positions
  - config/sessions → eassets_bot_config

Usage:
    SQLITE_DB_PATH=/path/to/trading_bot.db DATABASE_URL=postgresql://... python 002_migrate_sqlite_data.py

The script is idempotent for inserts via ON CONFLICT DO NOTHING on the
trade_timestamp + config_id composite key (if one exists) — otherwise it
logs and skips duplicates.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from typing import Any

import asyncpg
from loguru import logger

SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "trading_bot.db")
DATABASE_URL = os.environ["DATABASE_URL"]

BATCH_SIZE = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sqlite_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    """Fetch all rows from a SQLite table as list of dicts."""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {table}")  # noqa: S608
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError as exc:
        logger.warning("SQLite table '{}' not found or error: {}", table, exc)
        return []


def batched(lst: list, size: int):
    """Yield successive slices of lst of at most `size` elements."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ---------------------------------------------------------------------------
# Per-table migration functions
# ---------------------------------------------------------------------------

async def migrate_configs(
    pg: asyncpg.Connection,
    rows: list[dict[str, Any]],
) -> dict[int, int]:
    """Insert bot config/session rows. Returns mapping old_id → new_id."""
    id_map: dict[int, int] = {}
    inserted = 0
    skipped = 0

    for row in rows:
        try:
            new_id = await pg.fetchval(
                """
                INSERT INTO eassets_bot_config (
                    session_name, exchange, capital, balance, leverage,
                    fee_type, fee_rate, min_tpm, max_positions, min_score,
                    entry_seconds, exit_seconds,
                    pcl_enabled, pcl_cooldown_minutes, pcl_max_attempts,
                    pcl_min_struct_score
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                RETURNING id
                """,
                row.get("session_name") or row.get("name") or "migrated",
                row.get("exchange", "bybit"),
                float(row.get("capital") or row.get("initial_capital") or 0),
                float(row.get("balance") or row.get("current_balance") or 0),
                int(row.get("leverage", 5)),
                row.get("fee_type", "maker"),
                float(row.get("fee_rate") or 0.0002),
                int(row.get("min_tpm") or 800),
                int(row.get("max_positions") or 5),
                float(row.get("min_score") or 65.0),
                int(row.get("entry_seconds") or 30),
                int(row.get("exit_seconds") or 30),
                bool(row.get("pcl_enabled", True)),
                int(row.get("pcl_cooldown_minutes") or 30),
                int(row.get("pcl_max_attempts") or 3),
                int(row.get("pcl_min_struct_score") or 3),
            )
            old_id = row.get("id")
            if old_id is not None and new_id is not None:
                id_map[int(old_id)] = int(new_id)
            inserted += 1
        except Exception as exc:
            logger.error("Config row skipped: {} — {}", row, exc)
            skipped += 1

    logger.info("Configs: {} inserted, {} skipped", inserted, skipped)
    return id_map


async def migrate_trades(
    pg: asyncpg.Connection,
    rows: list[dict[str, Any]],
    config_id_map: dict[int, int],
    default_config_id: int,
) -> None:
    """Insert closed trade rows."""
    inserted = 0
    skipped = 0

    for batch in batched(rows, BATCH_SIZE):
        records = []
        for row in batch:
            old_cid = row.get("config_id") or row.get("session_id")
            cid = config_id_map.get(int(old_cid), default_config_id) if old_cid else default_config_id
            try:
                records.append((
                    cid,
                    str(row.get("symbol", "UNKNOWN")).upper(),
                    str(row.get("direction", "LONG")).upper(),
                    float(row.get("entry_price") or 0),
                    float(row.get("exit_price") or 0),
                    float(row.get("size") or 0),
                    float(row.get("funding_rate") or 0),
                    float(row.get("funding_pnl") or 0),
                    float(row.get("price_pnl") or 0),
                    float(row.get("price_pnl_pct") or 0),
                    float(row.get("fee_cost") or 0),
                    float(row.get("total_pnl") or 0),
                    float(row.get("total_pnl_pct") or 0),
                    float(row.get("balance_after") or 0),
                    row.get("close_reason"),
                    row.get("open_time"),
                    row.get("close_time"),
                    int(row.get("trade_timestamp") or row.get("timestamp") or 0),
                    row.get("exchange", "bybit"),
                ))
            except Exception as exc:
                logger.warning("Trade row prep failed: {} — {}", row, exc)
                skipped += 1

        try:
            await pg.executemany(
                """
                INSERT INTO eassets_trades (
                    config_id, symbol, direction, entry_price, exit_price, size,
                    funding_rate, funding_pnl, price_pnl, price_pnl_pct,
                    fee_cost, total_pnl, total_pnl_pct, balance_after,
                    close_reason, open_time, close_time, trade_timestamp, exchange
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                    $11,$12,$13,$14,$15,$16,$17,$18,$19
                )
                ON CONFLICT DO NOTHING
                """,
                records,
            )
            inserted += len(records)
        except Exception as exc:
            logger.error("Trade batch insert failed: {}", exc)
            skipped += len(records)

    logger.info("Trades: {} inserted, {} skipped", inserted, skipped)


async def migrate_positions(
    pg: asyncpg.Connection,
    rows: list[dict[str, Any]],
    config_id_map: dict[int, int],
    default_config_id: int,
) -> None:
    """Insert open position rows (best-effort)."""
    inserted = 0
    skipped = 0

    for row in rows:
        old_cid = row.get("config_id") or row.get("session_id")
        cid = config_id_map.get(int(old_cid), default_config_id) if old_cid else default_config_id
        try:
            await pg.execute(
                """
                INSERT INTO eassets_positions (
                    config_id, symbol, direction,
                    entry_price, size, value,
                    funding_rate, funding_rate_pct,
                    open_timestamp
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT DO NOTHING
                """,
                cid,
                str(row.get("symbol", "UNKNOWN")).upper(),
                str(row.get("direction", "LONG")).upper(),
                float(row.get("entry_price") or 0),
                float(row.get("size") or 0),
                float(row.get("value") or row.get("notional") or 0),
                float(row.get("funding_rate") or 0),
                float(row.get("funding_rate_pct") or 0),
                int(row.get("open_timestamp") or row.get("timestamp") or 0),
            )
            inserted += 1
        except Exception as exc:
            logger.warning("Position row skipped: {} — {}", row, exc)
            skipped += 1

    logger.info("Positions: {} inserted, {} skipped", inserted, skipped)


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

async def main() -> None:
    if not os.path.exists(SQLITE_DB_PATH):
        logger.error("SQLite file not found: {}", SQLITE_DB_PATH)
        sys.exit(1)

    logger.info("Opening SQLite: {}", SQLITE_DB_PATH)
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)

    logger.info("Connecting to PostgreSQL...")
    pg = await asyncpg.connect(dsn=DATABASE_URL)

    try:
        # ---- Configs ----
        config_rows = sqlite_rows(sqlite_conn, "bot_config")
        if not config_rows:
            # fallback table names
            config_rows = sqlite_rows(sqlite_conn, "sessions")
        config_id_map = await migrate_configs(pg, config_rows)

        # Ensure we have at least one default config_id to attach orphan rows
        default_config_id: int
        if config_id_map:
            default_config_id = next(iter(config_id_map.values()))
        else:
            # Create a placeholder config
            default_config_id = await pg.fetchval(
                """
                INSERT INTO eassets_bot_config (session_name, capital, balance)
                VALUES ('migrated_default', 0, 0)
                RETURNING id
                """
            )
            logger.info("Created placeholder config id={}", default_config_id)

        # ---- Trades ----
        trade_rows = (
            sqlite_rows(sqlite_conn, "trades")
            or sqlite_rows(sqlite_conn, "trade_history")
            or sqlite_rows(sqlite_conn, "closed_trades")
        )
        if trade_rows:
            await migrate_trades(pg, trade_rows, config_id_map, default_config_id)
        else:
            logger.warning("No trade rows found in SQLite.")

        # ---- Positions ----
        pos_rows = (
            sqlite_rows(sqlite_conn, "positions")
            or sqlite_rows(sqlite_conn, "open_positions")
        )
        if pos_rows:
            await migrate_positions(pg, pos_rows, config_id_map, default_config_id)
        else:
            logger.warning("No position rows found in SQLite.")

        logger.info("Migration complete.")

    finally:
        sqlite_conn.close()
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
