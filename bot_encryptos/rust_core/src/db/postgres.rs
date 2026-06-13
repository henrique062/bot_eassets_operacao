use crate::trading::position_manager::Position;
use crate::trading::watchlist_manager::WatchlistEntry;
use anyhow::Result;
use sqlx::PgPool;
use uuid::Uuid;

pub type DbPool = PgPool;

/// Cria o pool de conexões PostgreSQL usando DATABASE_URL.
pub async fn create_pool() -> Result<PgPool> {
    let url = std::env::var("DATABASE_URL").expect("DATABASE_URL não configurada");

    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(10)
        .connect(&url)
        .await?;

    Ok(pool)
}

// ---------------------------------------------------------------------------
// eassets_positions
// ---------------------------------------------------------------------------

pub async fn insert_position(pool: &PgPool, pos: &Position) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO eassets_positions (
            id, config_id, symbol, side, qty, entry_price, entry_score,
            stop_loss, take_profit, trailing_stop_pct, trailing_start_pct,
            order_id, opened_at, status, mode
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7,
            $8, $9, $10, $11,
            $12, $13, 'open', $14
        )
        ON CONFLICT (id) DO NOTHING
        "#,
    )
    .bind(pos.id)
    .bind(pos.config_id)
    .bind(&pos.symbol)
    .bind(&pos.side)
    .bind(pos.qty)
    .bind(pos.entry_price)
    .bind(pos.entry_score)
    .bind(pos.stop_loss)
    .bind(pos.take_profit)
    .bind(pos.trailing_stop_pct)
    .bind(pos.trailing_start_pct)
    .bind(&pos.order_id)
    .bind(pos.opened_at)
    .bind(&pos.mode)
    .execute(pool)
    .await?;

    Ok(())
}

pub async fn close_position(
    pool: &PgPool,
    id: Uuid,
    close_price: f64,
    pnl_usd: f64,
    reason: &str,
) -> Result<()> {
    sqlx::query(
        r#"
        UPDATE eassets_positions
        SET
            close_price = $2,
            pnl_usd = $3,
            close_reason = $4,
            closed_at = NOW(),
            status = 'closed'
        WHERE id = $1
        "#,
    )
    .bind(id)
    .bind(close_price)
    .bind(pnl_usd)
    .bind(reason)
    .execute(pool)
    .await?;

    Ok(())
}

// ---------------------------------------------------------------------------
// eassets_trades
// ---------------------------------------------------------------------------

pub async fn insert_trade(
    pool: &PgPool,
    pos: &Position,
    close_price: f64,
    pnl_usd: f64,
    pnl_pct: f64,
    reason: &str,
) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO eassets_trades (
            id, config_id, symbol, side, qty,
            entry_price, close_price,
            pnl_usd, pnl_pct,
            entry_score, close_reason,
            order_id, opened_at, closed_at, mode
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7,
            $8, $9,
            $10, $11,
            $12, $13, NOW(), $14
        )
        "#,
    )
    .bind(Uuid::new_v4())
    .bind(pos.config_id)
    .bind(&pos.symbol)
    .bind(&pos.side)
    .bind(pos.qty)
    .bind(pos.entry_price)
    .bind(close_price)
    .bind(pnl_usd)
    .bind(pnl_pct)
    .bind(pos.entry_score)
    .bind(reason)
    .bind(&pos.order_id)
    .bind(pos.opened_at)
    .bind(&pos.mode)
    .execute(pool)
    .await?;

    Ok(())
}

// ---------------------------------------------------------------------------
// eassets_order_logs
// ---------------------------------------------------------------------------

pub async fn insert_order_log(
    pool: &PgPool,
    config_id: i32,
    symbol: &str,
    event: &str,
    detail: &str,
) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO eassets_order_logs (
            id, config_id, symbol, event, detail, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, NOW()
        )
        "#,
    )
    .bind(Uuid::new_v4())
    .bind(config_id)
    .bind(symbol)
    .bind(event)
    .bind(detail)
    .execute(pool)
    .await?;

    Ok(())
}

// ---------------------------------------------------------------------------
// eassets_watchlist
// ---------------------------------------------------------------------------

pub async fn upsert_watchlist(pool: &PgPool, entry: &WatchlistEntry) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO eassets_watchlist (
            id, config_id, symbol, status, struct_score,
            attempt_count, cooldown_until, added_at, updated_at,
            original_position_id
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10
        )
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            struct_score = EXCLUDED.struct_score,
            attempt_count = EXCLUDED.attempt_count,
            cooldown_until = EXCLUDED.cooldown_until,
            updated_at = EXCLUDED.updated_at
        "#,
    )
    .bind(entry.id)
    .bind(entry.config_id)
    .bind(&entry.symbol)
    .bind(entry.status.to_string())
    .bind(entry.struct_score as i32)
    .bind(entry.attempt_count)
    .bind(entry.cooldown_until)
    .bind(entry.added_at)
    .bind(entry.updated_at)
    .bind(entry.original_position_id)
    .execute(pool)
    .await?;

    Ok(())
}

// ---------------------------------------------------------------------------
// get_watchlist_by_config
// ---------------------------------------------------------------------------

pub async fn get_watchlist_by_config(
    pool: &PgPool,
    config_id: i32,
) -> Result<Vec<WatchlistEntry>> {
    use crate::trading::watchlist_manager::WatchlistStatus;

    let rows = sqlx::query_as::<_, WatchlistRow>(
        r#"
        SELECT
            id, config_id, symbol, status, struct_score,
            attempt_count, cooldown_until, added_at, updated_at,
            original_position_id
        FROM eassets_watchlist
        WHERE config_id = $1
          AND status NOT IN ('Invalidated', 'Completed')
        ORDER BY added_at DESC
        "#,
    )
    .bind(config_id)
    .fetch_all(pool)
    .await?;

    let entries = rows
        .into_iter()
        .map(|r| WatchlistEntry {
            id: r.id,
            config_id: r.config_id,
            symbol: r.symbol,
            status: parse_watchlist_status(&r.status),
            struct_score: r.struct_score as u8,
            attempt_count: r.attempt_count,
            cooldown_until: r.cooldown_until,
            added_at: r.added_at,
            updated_at: r.updated_at,
            original_position_id: r.original_position_id,
        })
        .collect();

    Ok(entries)
}

#[derive(sqlx::FromRow)]
struct WatchlistRow {
    id: Uuid,
    config_id: i32,
    symbol: String,
    status: String,
    struct_score: i32,
    attempt_count: i32,
    cooldown_until: Option<chrono::DateTime<chrono::Utc>>,
    added_at: chrono::DateTime<chrono::Utc>,
    updated_at: chrono::DateTime<chrono::Utc>,
    original_position_id: Option<Uuid>,
}

fn parse_watchlist_status(s: &str) -> crate::trading::watchlist_manager::WatchlistStatus {
    use crate::trading::watchlist_manager::WatchlistStatus;
    match s {
        "Watchlist" => WatchlistStatus::Watchlist,
        "Cooldown" => WatchlistStatus::Cooldown,
        "Candidate" => WatchlistStatus::Candidate,
        "Active" => WatchlistStatus::Active,
        "Invalidated" => WatchlistStatus::Invalidated,
        "Completed" => WatchlistStatus::Completed,
        _ => WatchlistStatus::Watchlist,
    }
}
