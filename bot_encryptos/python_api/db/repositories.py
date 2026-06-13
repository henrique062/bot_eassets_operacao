"""
AsyncPG repository layer — all SQL queries live here.

Each function receives a pool (or connection) and returns plain Python
dicts/lists so that the API layer can serialise them directly.
"""

from __future__ import annotations

import re
from typing import Any

import asyncpg
from loguru import logger


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

def normalize_symbol(value: Any) -> str:
    """Normalize Binance/TradingView symbols to the panel symbol shape."""
    symbol = str(value or "").strip().upper()
    if ":" in symbol:
        symbol = symbol.rsplit(":", 1)[1]
    if symbol.endswith(".P"):
        symbol = symbol[:-2]
    return re.sub(r"[^A-Z0-9]", "", symbol)


async def get_tagged_symbols(pool: asyncpg.Pool, tag: str = "alpha") -> set[str]:
    rows = await pool.fetch(
        """
        SELECT symbol
        FROM eassets_symbol_tags
        WHERE tag = $1
        ORDER BY symbol
        """,
        tag.lower(),
    )
    return {str(r["symbol"]) for r in rows}


async def list_symbol_tags(pool: asyncpg.Pool, tag: str = "alpha") -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT symbol, tag, source, created_at, updated_at
        FROM eassets_symbol_tags
        WHERE tag = $1
        ORDER BY symbol
        """,
        tag.lower(),
    )
    return [dict(r) for r in rows]


async def upsert_symbol_tags(
    pool: asyncpg.Pool,
    symbols: list[str],
    tag: str = "alpha",
    source: str = "manual",
) -> list[str]:
    normalized = sorted({normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)})
    if not normalized:
        return []

    records = [(symbol, tag.lower(), source) for symbol in normalized]
    await pool.executemany(
        """
        INSERT INTO eassets_symbol_tags (symbol, tag, source)
        VALUES ($1, $2, $3)
        ON CONFLICT (symbol, tag) DO UPDATE SET
            updated_at = NOW(),
            source = EXCLUDED.source
        """,
        records,
    )
    return normalized


async def delete_symbol_tag(pool: asyncpg.Pool, symbol: str, tag: str = "alpha") -> bool:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return False

    result = await pool.execute(
        "DELETE FROM eassets_symbol_tags WHERE symbol = $1 AND tag = $2",
        normalized,
        tag.lower(),
    )
    return result.endswith("1")


def apply_alpha_flags(rows: list[dict[str, Any]], alpha_symbols: set[str]) -> list[dict[str, Any]]:
    """Add is_alpha to rows that carry a symbol field."""
    for row in rows:
        row["is_alpha"] = normalize_symbol(row.get("symbol")) in alpha_symbols
    return rows

async def get_positions(pool: asyncpg.Pool, config_id: int) -> list[dict[str, Any]]:
    """Return all open positions for a config session."""
    rows = await pool.fetch(
        "SELECT * FROM eassets_positions WHERE config_id = $1 ORDER BY created_at DESC",
        config_id,
    )
    return [dict(r) for r in rows]


async def _table_columns(pool: asyncpg.Pool, table_name: str) -> set[str]:
    rows = await pool.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
        """,
        table_name,
    )
    return {str(r["column_name"]) for r in rows}


async def get_open_position_lookup(
    pool: asyncpg.Pool,
    config_id: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Return open bot positions keyed by symbol/direction for origin matching.

    The deployed DB has had more than one position schema during development.
    This query adapts to the available columns so the live Bybit reconciliation
    does not break if the bot table still uses the older shape.
    """
    columns = await _table_columns(pool, "eassets_positions")
    if not {"symbol", "config_id"}.issubset(columns):
        return {}

    if "direction" in columns:
        direction_expr = "direction"
    elif "side" in columns:
        direction_expr = (
            "CASE WHEN side = 'Buy' THEN 'LONG' WHEN side = 'Sell' THEN 'SHORT' "
            "ELSE UPPER(side) END"
        )
    else:
        direction_expr = "''"

    select_parts = [
        "id::text AS id",
        "config_id",
        "symbol",
        f"{direction_expr} AS direction",
    ]
    if "entry_score" in columns:
        select_parts.append("entry_score")
    if "open_order_id" in columns:
        select_parts.append("open_order_id AS order_id")
    elif "order_id" in columns:
        select_parts.append("order_id")

    where_parts = []
    args: list[Any] = []
    if config_id is not None:
        args.append(config_id)
        where_parts.append(f"config_id = ${len(args)}")
    if "status" in columns:
        where_parts.append("LOWER(status) = 'open'")
    if "closed_at" in columns:
        where_parts.append("closed_at IS NULL")

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    order_col = "created_at" if "created_at" in columns else "opened_at" if "opened_at" in columns else "id"
    sql = f"""
        SELECT {", ".join(select_parts)}
        FROM eassets_positions
        {where_sql}
        ORDER BY {order_col} DESC
    """
    rows = await pool.fetch(sql, *args)

    lookup: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        symbol = str(data.get("symbol") or "").upper()
        direction = str(data.get("direction") or "").upper()
        if not symbol:
            continue
        lookup.setdefault(symbol, data)
        if direction:
            lookup.setdefault(f"{symbol}:{direction}", data)
    return lookup


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

async def get_trades(
    pool: asyncpg.Pool,
    config_id: int,
    skip: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return paginated closed trades for a config session."""
    rows = await pool.fetch(
        """
        SELECT * FROM eassets_trades
        WHERE config_id = $1
        ORDER BY trade_timestamp DESC
        OFFSET $2 LIMIT $3
        """,
        config_id,
        skip,
        limit,
    )
    return [dict(r) for r in rows]


async def get_trades_by_symbol(
    pool: asyncpg.Pool,
    symbol: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return trades for a specific symbol across all sessions."""
    rows = await pool.fetch(
        """
        SELECT * FROM eassets_trades
        WHERE symbol = $1
        ORDER BY trade_timestamp DESC
        LIMIT $2
        """,
        symbol,
        limit,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

async def get_logs(
    pool: asyncpg.Pool,
    config_id: int,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return order event logs for a config session."""
    rows = await pool.fetch(
        """
        SELECT * FROM eassets_order_logs
        WHERE config_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        config_id,
        limit,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

async def get_config(pool: asyncpg.Pool, config_id: int) -> dict[str, Any] | None:
    """Return a single bot config row, or None if not found."""
    row = await pool.fetchrow(
        "SELECT * FROM eassets_bot_config WHERE id = $1",
        config_id,
    )
    return dict(row) if row else None


async def get_latest_config(pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Return the most recent config, preferring an active session when present."""
    row = await pool.fetchrow(
        """
        SELECT *
        FROM eassets_bot_config
        ORDER BY active DESC, updated_at DESC, created_at DESC, id DESC
        LIMIT 1
        """
    )
    return dict(row) if row else None


async def save_config(pool: asyncpg.Pool, data: dict[str, Any]) -> int:
    """Insert a new bot config row and return its generated id."""
    row = await pool.fetchrow(
        """
        INSERT INTO eassets_bot_config (
            session_name, exchange, capital, balance, leverage,
            fee_type, fee_rate, min_tpm, min_oi_trend, max_lsr,
            min_rsi_btc, max_rsi_btc, min_exp_btc, max_positions, min_score,
            stop_loss_pct, stop_loss_usd, take_profit_pct,
            trailing_stop_pct, trailing_start_pct, break_even_at_pct,
            entry_seconds, exit_seconds,
            pcl_enabled, pcl_cooldown_minutes, pcl_max_attempts,
            pcl_min_struct_score, pcl_profit_target_usd, user_id, paper_trading
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,
            $19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30
        )
        RETURNING id
        """,
        data.get("session_name"),
        data.get("exchange", "bybit"),
        data["capital"],
        data["balance"],
        data.get("leverage", 5),
        data.get("fee_type", "maker"),
        data.get("fee_rate", 0.0002),
        data.get("min_tpm", 800),
        data.get("min_oi_trend", 0),
        data.get("max_lsr", 1.0),
        data.get("min_rsi_btc"),
        data.get("max_rsi_btc", 40.0),
        data.get("min_exp_btc", 0),
        data.get("max_positions", 5),
        data.get("min_score", 65.0),
        data.get("stop_loss_pct"),
        data.get("stop_loss_usd"),
        data.get("take_profit_pct"),
        data.get("trailing_stop_pct"),
        data.get("trailing_start_pct"),
        data.get("break_even_at_pct"),
        data.get("entry_seconds", 30),
        data.get("exit_seconds", 30),
        data.get("pcl_enabled", True),
        data.get("pcl_cooldown_minutes", 30),
        data.get("pcl_max_attempts", 3),
        data.get("pcl_min_struct_score", 3),
        data.get("pcl_profit_target_usd"),
        data.get("user_id"),
        data.get("paper_trading", True),
    )
    return row["id"]  # type: ignore[index]


async def update_config(pool: asyncpg.Pool, config_id: int, data: dict[str, Any]) -> bool:
    """Update an existing bot config row. Returns True when a row was updated."""
    row = await pool.fetchrow(
        """
        UPDATE eassets_bot_config
        SET
            session_name = $2,
            exchange = $3,
            capital = $4,
            balance = $5,
            leverage = $6,
            fee_type = $7,
            fee_rate = $8,
            min_tpm = $9,
            min_oi_trend = $10,
            max_lsr = $11,
            min_rsi_btc = $12,
            max_rsi_btc = $13,
            min_exp_btc = $14,
            max_positions = $15,
            min_score = $16,
            stop_loss_pct = $17,
            stop_loss_usd = $18,
            take_profit_pct = $19,
            trailing_stop_pct = $20,
            trailing_start_pct = $21,
            break_even_at_pct = $22,
            entry_seconds = $23,
            exit_seconds = $24,
            pcl_enabled = $25,
            pcl_cooldown_minutes = $26,
            pcl_max_attempts = $27,
            pcl_min_struct_score = $28,
            pcl_profit_target_usd = $29,
            user_id = $30,
            paper_trading = $31,
            updated_at = NOW()
        WHERE id = $1
        RETURNING id
        """,
        config_id,
        data.get("session_name"),
        data.get("exchange", "bybit"),
        data["capital"],
        data["balance"],
        data.get("leverage", 5),
        data.get("fee_type", "maker"),
        data.get("fee_rate", 0.0002),
        data.get("min_tpm", 800),
        data.get("min_oi_trend", 0),
        data.get("max_lsr", 1.0),
        data.get("min_rsi_btc"),
        data.get("max_rsi_btc", 40.0),
        data.get("min_exp_btc", 0),
        data.get("max_positions", 5),
        data.get("min_score", 65.0),
        data.get("stop_loss_pct"),
        data.get("stop_loss_usd"),
        data.get("take_profit_pct"),
        data.get("trailing_stop_pct"),
        data.get("trailing_start_pct"),
        data.get("break_even_at_pct"),
        data.get("entry_seconds", 30),
        data.get("exit_seconds", 30),
        data.get("pcl_enabled", True),
        data.get("pcl_cooldown_minutes", 30),
        data.get("pcl_max_attempts", 3),
        data.get("pcl_min_struct_score", 3),
        data.get("pcl_profit_target_usd"),
        data.get("user_id"),
        data.get("paper_trading", True),
    )
    return row is not None


async def get_active_configs(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return all active (running) bot config sessions."""
    rows = await pool.fetch(
        "SELECT * FROM eassets_bot_config WHERE active = TRUE ORDER BY started_at DESC"
    )
    return [dict(r) for r in rows]


async def set_config_active(
    pool: asyncpg.Pool,
    config_id: int,
    active: bool,
    paused: bool = False,
) -> bool:
    """Mark a config session as active/inactive and update session timestamps."""
    row = await pool.fetchrow(
        """
        UPDATE eassets_bot_config
        SET
            active = $2,
            paused = $3,
            started_at = CASE WHEN $2 THEN NOW() ELSE started_at END,
            ended_at = CASE WHEN $2 THEN NULL ELSE NOW() END,
            updated_at = NOW()
        WHERE id = $1
        RETURNING id
        """,
        config_id,
        active,
        paused,
    )
    return row is not None


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

async def get_watchlist(pool: asyncpg.Pool, config_id: int) -> list[dict[str, Any]]:
    """Return all watchlist entries for a config session."""
    rows = await pool.fetch(
        """
        SELECT * FROM eassets_watchlist
        WHERE config_id = $1
        ORDER BY added_at DESC
        """,
        config_id,
    )
    return [dict(r) for r in rows]


async def remove_from_watchlist(pool: asyncpg.Pool, config_id: int, symbol: str) -> bool:
    """Remove a symbol from the watchlist. Returns True if a row was deleted."""
    result = await pool.execute(
        "DELETE FROM eassets_watchlist WHERE config_id = $1 AND symbol = $2",
        config_id,
        symbol,
    )
    return result.endswith("1")


# ---------------------------------------------------------------------------
# Snapshots / metrics
# ---------------------------------------------------------------------------

async def insert_snapshot(pool: asyncpg.Pool, data: dict[str, Any]) -> int:
    """Insert an eassets_snapshots row and return its id."""
    row = await pool.fetchrow(
        """
        INSERT INTO eassets_snapshots (timestamp, exchange, setup, mode, symbols, source, btc_reset, trigger)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (timestamp) DO UPDATE SET
            ingested_at = NOW(),
            source = EXCLUDED.source
        RETURNING id
        """,
        data["timestamp"],
        data.get("exchange"),
        data.get("setup"),
        data.get("mode"),
        data.get("symbols"),
        data.get("source", "scraper"),
        data.get("btc_reset"),
        data.get("trigger", "auto"),
    )
    return row["id"]  # type: ignore[index]


async def insert_metrics(
    pool: asyncpg.Pool,
    snapshot_id: int,
    rows: list[dict[str, Any]],
) -> None:
    """Batch-insert computed metrics rows for a snapshot."""
    if not rows:
        return

    records = [
        (
            snapshot_id,
            r["symbol"],
            r.get("rank"),
            r.get("score"),
            r.get("badge"),
            r.get("price_raw"),
            r.get("change"),
            r.get("exp1d"),
            r.get("exp4h"),
            r.get("exp1h"),
            r.get("oitrend"),
            r.get("lsr"),
            r.get("lsrtrend"),
            r.get("rsi4h"),
            r.get("oi_usd_raw"),
            r.get("trades"),
            r.get("range4h"),
            r.get("range1d"),
            r.get("trades1d"),
            r.get("toi"),
            r.get("entry_score"),
            r.get("entry_grade", ""),
            r.get("raw_json", "{}"),
        )
        for r in rows
    ]

    await pool.executemany(
        """
        INSERT INTO eassets_metrics (
            snapshot_id, symbol, rank, score, setup,
            price, price_change_1d, exp_1d, exp_4h, exp_1h,
            oi_trend, lsr, lsr_trend, rsi_4h, oi_usd,
            trades_min, range_4h, range_1d, trades_1d, toi,
            setup_score, setup_grade, raw_json
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
            $21,$22,$23
        )
        """,
        records,
    )


async def insert_raw_snapshot(
    pool: asyncpg.Pool,
    snapshot_id: int | None,
    raw_json: str,
    status: str = "ok",
    error_msg: str | None = None,
) -> int:
    """Insert a raw JSON blob row and return its id."""
    row = await pool.fetchrow(
        """
        INSERT INTO eassets_raw_snapshots (snapshot_id, raw_json, status, error_msg)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        snapshot_id,
        raw_json,
        status,
        error_msg,
    )
    return row["id"]  # type: ignore[index]


async def get_raw_snapshots(
    pool: asyncpg.Pool,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most recent raw snapshot records (without the full JSON blob)."""
    rows = await pool.fetch(
        """
        SELECT id, snapshot_id, captured_at, status, error_msg
        FROM eassets_raw_snapshots
        ORDER BY captured_at DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Painel (análise manual de moedas — metodologia Encryptos)
# ---------------------------------------------------------------------------

async def list_panel_snapshots(
    pool: asyncpg.Pool,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return snapshot headers (most recent first) for the panel selector."""
    rows = await pool.fetch(
        """
        SELECT id, timestamp, exchange, setup, symbols, btc_reset, ingested_at
        FROM eassets_snapshots
        ORDER BY timestamp DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


async def get_latest_snapshot_id(pool: asyncpg.Pool) -> int | None:
    """Return the id of the most recent snapshot, or None when empty."""
    row = await pool.fetchrow(
        "SELECT id FROM eassets_snapshots ORDER BY timestamp DESC LIMIT 1"
    )
    return int(row["id"]) if row else None


async def get_snapshot_meta(pool: asyncpg.Pool, snapshot_id: int) -> dict[str, Any] | None:
    """Return a single snapshot header by id."""
    row = await pool.fetchrow(
        """
        SELECT id, timestamp, exchange, setup, mode, symbols, btc_reset, ingested_at, source
        FROM eassets_snapshots
        WHERE id = $1
        """,
        snapshot_id,
    )
    return dict(row) if row else None


async def get_panel_metrics(pool: asyncpg.Pool, snapshot_id: int) -> list[dict[str, Any]]:
    """Return every per-symbol metric row for a snapshot, ranked ascending."""
    rows = await pool.fetch(
        """
        SELECT symbol, rank, score, setup, price, price_change_1d,
               exp_1d, exp_4h, exp_1h, oi_trend, lsr, lsr_trend, rsi_4h,
               oi_usd, trades_min, range_4h, range_1d, trades_1d, toi,
               setup_score, setup_grade, raw_json
        FROM eassets_metrics
        WHERE snapshot_id = $1
        ORDER BY rank ASC NULLS LAST
        """,
        snapshot_id,
    )
    return [dict(r) for r in rows]


async def get_symbol_raw(
    pool: asyncpg.Pool,
    snapshot_id: int,
    symbol: str,
) -> str | None:
    """Return the raw per-symbol JSON blob for one metric row (e.g. BTCUSDT)."""
    row = await pool.fetchrow(
        "SELECT raw_json FROM eassets_metrics WHERE snapshot_id = $1 AND symbol = $2",
        snapshot_id,
        symbol,
    )
    return row["raw_json"] if row else None


async def get_symbol_panel_history(
    pool: asyncpg.Pool,
    symbol: str,
    limit: int = 60,
) -> list[dict[str, Any]]:
    """Return the metric history of a symbol across snapshots (newest first)."""
    rows = await pool.fetch(
        """
        SELECT s.id AS snapshot_id, s.timestamp, m.rank, m.score, m.setup,
               m.price, m.price_change_1d, m.exp_1d, m.exp_4h, m.exp_1h,
               m.oi_trend, m.lsr, m.lsr_trend, m.rsi_4h, m.oi_usd, m.toi
        FROM eassets_metrics m
        JOIN eassets_snapshots s ON s.id = m.snapshot_id
        WHERE m.symbol = $1
        ORDER BY s.timestamp DESC
        LIMIT $2
        """,
        symbol,
        limit,
    )
    return [dict(r) for r in rows]


async def get_top_appearances(
    pool: asyncpg.Pool,
    top_n: int = 10,
    snapshot_limit: int = 50,
) -> list[dict[str, Any]]:
    """Aggregate how often each symbol ranked within the TOP-N across snapshots."""
    rows = await pool.fetch(
        """
        WITH recent AS (
            SELECT id FROM eassets_snapshots
            ORDER BY timestamp DESC LIMIT $2
        )
        SELECT m.symbol,
               COUNT(*)                       AS appearances,
               MIN(m.rank)                     AS best_rank,
               ROUND(AVG(m.rank), 1)           AS avg_rank,
               MAX(m.score)                    AS max_score,
               ROUND(AVG(m.score), 1)          AS avg_score
        FROM eassets_metrics m
        JOIN recent r ON r.id = m.snapshot_id
        WHERE m.rank <= $1
        GROUP BY m.symbol
        ORDER BY appearances DESC, avg_rank ASC
        LIMIT 50
        """,
        top_n,
        snapshot_limit,
    )
    return [dict(r) for r in rows]


async def get_toi_persistence(
    pool: asyncpg.Pool,
    snapshot_id: int | None = None,
    snapshot_limit: int = 30,
    top_n: int = 30,
) -> dict[str, int]:
    """Count, per symbol, in how many recent snapshots it ranked in the TOP-N by T/OI."""
    if snapshot_id is None:
        recent_sql = "SELECT id FROM eassets_snapshots ORDER BY timestamp DESC LIMIT $1"
        args: tuple[Any, ...] = (snapshot_limit, top_n)
    else:
        recent_sql = """
            SELECT id
            FROM eassets_snapshots
            WHERE timestamp <= (
                SELECT timestamp FROM eassets_snapshots WHERE id = $1
            )
            ORDER BY timestamp DESC
            LIMIT $2
        """
        args = (snapshot_id, snapshot_limit, top_n)

    rows = await pool.fetch(
        f"""
        WITH recent AS (
            {recent_sql}
        ),
        ranked AS (
            SELECT m.symbol,
                   ROW_NUMBER() OVER (
                       PARTITION BY m.snapshot_id
                       ORDER BY m.toi DESC NULLS LAST
                   ) AS toi_rank
            FROM eassets_metrics m
            JOIN recent r ON r.id = m.snapshot_id
            WHERE m.toi IS NOT NULL
        )
        SELECT symbol, COUNT(*) AS days_top
        FROM ranked
        WHERE toi_rank <= ${len(args)}
        GROUP BY symbol
        """,
        *args,
    )
    return {r["symbol"]: int(r["days_top"]) for r in rows}


async def count_snapshots(
    pool: asyncpg.Pool,
    limit: int = 30,
    snapshot_id: int | None = None,
) -> int:
    """Return the number of snapshots (capped at limit) for persistence ratios."""
    if snapshot_id is None:
        sql = """
        SELECT COUNT(*) AS n
        FROM (
            SELECT id FROM eassets_snapshots ORDER BY timestamp DESC LIMIT $1
        ) t
        """
        args: tuple[Any, ...] = (limit,)
    else:
        sql = """
        SELECT COUNT(*) AS n
        FROM (
            SELECT id
            FROM eassets_snapshots
            WHERE timestamp <= (
                SELECT timestamp FROM eassets_snapshots WHERE id = $1
            )
            ORDER BY timestamp DESC
            LIMIT $2
        ) t
        """
        args = (snapshot_id, limit)

    row = await pool.fetchrow(
        sql,
        *args,
    )
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# Monitoração de moedas (marcadas manualmente a partir do Painel)
# ---------------------------------------------------------------------------

async def add_monitored(
    pool: asyncpg.Pool,
    symbol: str,
    note: str | None,
    mark_price: float | None,
    mark_score: int | None,
    mark_setup: str | None,
    mark_snapshot_id: int | None,
) -> dict[str, Any]:
    """Marca uma moeda para monitoração. Reativa/atualiza se já houver marcação ativa."""
    row = await pool.fetchrow(
        """
        INSERT INTO eassets_monitored
            (symbol, note, mark_price, mark_score, mark_setup, mark_snapshot_id, active, marked_at)
        VALUES ($1,$2,$3,$4,$5,$6,TRUE,NOW())
        ON CONFLICT (symbol) WHERE active DO UPDATE SET
            note = EXCLUDED.note,
            mark_price = EXCLUDED.mark_price,
            mark_score = EXCLUDED.mark_score,
            mark_setup = EXCLUDED.mark_setup,
            mark_snapshot_id = EXCLUDED.mark_snapshot_id,
            marked_at = NOW()
        RETURNING *
        """,
        symbol, note, mark_price, mark_score, mark_setup, mark_snapshot_id,
    )
    return dict(row)


async def unmark_monitored(pool: asyncpg.Pool, symbol: str) -> bool:
    """Desmarca (arquiva) a moeda monitorada ativa. Retorna True se algo mudou."""
    result = await pool.execute(
        "UPDATE eassets_monitored SET active = FALSE, unmarked_at = NOW() WHERE symbol = $1 AND active",
        symbol,
    )
    return result.endswith("1")


async def list_monitored(pool: asyncpg.Pool, active_only: bool = True) -> list[dict[str, Any]]:
    """Lista moedas monitoradas (ativas por padrão), com métricas atuais do último snapshot."""
    where = "WHERE m.active" if active_only else ""
    rows = await pool.fetch(
        f"""
        WITH latest AS (
            SELECT id FROM eassets_snapshots ORDER BY timestamp DESC LIMIT 1
        )
        SELECT
            m.id, m.symbol, m.note, m.marked_at, m.mark_price, m.mark_score,
            m.mark_setup, m.active, m.unmarked_at,
            me.price AS cur_price, me.score AS cur_score, me.setup AS cur_setup,
            me.rank AS cur_rank, me.price_change_1d, me.exp_1d, me.exp_4h, me.exp_1h,
            me.oi_trend, me.lsr, me.rsi_4h, me.toi, me.oi_usd
        FROM eassets_monitored m
        LEFT JOIN latest l ON TRUE
        LEFT JOIN eassets_metrics me ON me.snapshot_id = l.id AND me.symbol = m.symbol
        {where}
        ORDER BY m.marked_at DESC
        """,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Histórico de funding (extraído do raw_json de cada snapshot)
# ---------------------------------------------------------------------------

async def get_symbol_raw_history(
    pool: asyncpg.Pool,
    symbol: str,
    limit: int = 60,
) -> list[dict[str, Any]]:
    """Retorna (timestamp, raw_json) de um símbolo nos snapshots recentes (novo->antigo)."""
    rows = await pool.fetch(
        """
        SELECT s.timestamp, m.raw_json
        FROM eassets_metrics m
        JOIN eassets_snapshots s ON s.id = m.snapshot_id
        WHERE m.symbol = $1
        ORDER BY s.timestamp DESC
        LIMIT $2
        """,
        symbol,
        limit,
    )
    return [dict(r) for r in rows]


async def get_latest_metrics_funding(pool: asyncpg.Pool, limit: int = 600) -> list[dict[str, Any]]:
    """Retorna symbol + raw_json de todas as moedas do último snapshot (para varrer funding)."""
    rows = await pool.fetch(
        """
        WITH latest AS (SELECT id FROM eassets_snapshots ORDER BY timestamp DESC LIMIT 1)
        SELECT m.symbol, m.raw_json, m.price_change_1d
        FROM eassets_metrics m JOIN latest l ON m.snapshot_id = l.id
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]
