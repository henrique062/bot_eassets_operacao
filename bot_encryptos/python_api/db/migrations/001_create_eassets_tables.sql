-- =============================================================================
-- Migration 001: Create eAssets tables
-- =============================================================================

-- Bot configuration sessions
CREATE TABLE IF NOT EXISTS eassets_bot_config (
    id              BIGSERIAL PRIMARY KEY,
    session_name    VARCHAR(100) NOT NULL,
    exchange        VARCHAR(20)  NOT NULL DEFAULT 'bybit',
    active          BOOLEAN      NOT NULL DEFAULT FALSE,
    paused          BOOLEAN      NOT NULL DEFAULT FALSE,
    capital         NUMERIC(18,6) NOT NULL,
    balance         NUMERIC(18,6) NOT NULL,
    leverage        SMALLINT      NOT NULL DEFAULT 5,
    fee_type        VARCHAR(10)   NOT NULL DEFAULT 'maker',
    fee_rate        NUMERIC(10,6) NOT NULL DEFAULT 0.0002,
    min_tpm         INTEGER       NOT NULL DEFAULT 800,
    min_oi_trend    NUMERIC(10,4) DEFAULT 0,
    max_lsr         NUMERIC(10,4) DEFAULT 1.0,
    min_rsi_btc     NUMERIC(6,2)  DEFAULT NULL,
    max_rsi_btc     NUMERIC(6,2)  DEFAULT 40.0,
    min_exp_btc     NUMERIC(10,4) DEFAULT 0,
    max_positions   SMALLINT      NOT NULL DEFAULT 5,
    min_score       NUMERIC(6,2)  NOT NULL DEFAULT 65.0,
    stop_loss_pct        NUMERIC(10,4) DEFAULT NULL,
    stop_loss_usd        NUMERIC(18,6) DEFAULT NULL,
    take_profit_pct      NUMERIC(10,4) DEFAULT NULL,
    trailing_stop_pct    NUMERIC(10,4) DEFAULT NULL,
    trailing_start_pct   NUMERIC(10,4) DEFAULT NULL,
    break_even_at_pct    NUMERIC(10,4) DEFAULT NULL,
    entry_seconds   SMALLINT NOT NULL DEFAULT 30,
    exit_seconds    SMALLINT NOT NULL DEFAULT 30,
    pcl_enabled           BOOLEAN       NOT NULL DEFAULT TRUE,
    pcl_cooldown_minutes  INTEGER       NOT NULL DEFAULT 30,
    pcl_max_attempts      SMALLINT      NOT NULL DEFAULT 3,
    pcl_min_struct_score  SMALLINT      NOT NULL DEFAULT 3,
    pcl_profit_target_usd NUMERIC(18,6) DEFAULT NULL,
    user_id         INTEGER DEFAULT NULL,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    ended_at        TIMESTAMPTZ DEFAULT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Open positions per config session
CREATE TABLE IF NOT EXISTS eassets_positions (
    id               BIGSERIAL PRIMARY KEY,
    config_id        BIGINT NOT NULL REFERENCES eassets_bot_config(id) ON DELETE CASCADE,
    symbol           VARCHAR(30) NOT NULL,
    direction        VARCHAR(5)  NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price      NUMERIC(24,8) NOT NULL,
    size             NUMERIC(24,8) NOT NULL,
    value            NUMERIC(18,6) NOT NULL,
    funding_rate     NUMERIC(14,6) NOT NULL DEFAULT 0,
    funding_rate_pct NUMERIC(14,6) NOT NULL DEFAULT 0,
    open_order_id    VARCHAR(100),
    tp_order_id      VARCHAR(100),
    tp_price         NUMERIC(24,8),
    open_time        VARCHAR(30),
    open_timestamp   BIGINT NOT NULL,
    entry_rsi_btc    NUMERIC(6,2),
    entry_exp_btc    NUMERIC(10,4),
    entry_tpm        INTEGER,
    entry_lsr        NUMERIC(10,4),
    entry_oi_trend   NUMERIC(10,4),
    entry_score      NUMERIC(6,2),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eassets_positions_config ON eassets_positions(config_id);
CREATE INDEX IF NOT EXISTS idx_eassets_positions_symbol ON eassets_positions(symbol);

-- Closed trades history
CREATE TABLE IF NOT EXISTS eassets_trades (
    id              BIGSERIAL PRIMARY KEY,
    config_id       BIGINT NOT NULL REFERENCES eassets_bot_config(id) ON DELETE CASCADE,
    symbol          VARCHAR(30) NOT NULL,
    direction       VARCHAR(5)  NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price     NUMERIC(24,8) NOT NULL,
    exit_price      NUMERIC(24,8) NOT NULL,
    size            NUMERIC(24,8) NOT NULL,
    funding_rate    NUMERIC(14,6) NOT NULL DEFAULT 0,
    funding_pnl     NUMERIC(18,6) NOT NULL DEFAULT 0,
    price_pnl       NUMERIC(18,6) NOT NULL DEFAULT 0,
    price_pnl_pct   NUMERIC(18,6) NOT NULL DEFAULT 0,
    fee_cost        NUMERIC(18,6) NOT NULL DEFAULT 0 CHECK (fee_cost >= 0),
    total_pnl       NUMERIC(18,6) NOT NULL DEFAULT 0,
    total_pnl_pct   NUMERIC(14,6) NOT NULL DEFAULT 0,
    balance_after   NUMERIC(18,6) NOT NULL,
    close_reason    VARCHAR(50),
    open_time       VARCHAR(30),
    close_time      VARCHAR(30),
    trade_timestamp BIGINT NOT NULL,
    exchange        VARCHAR(20) NOT NULL DEFAULT 'bybit',
    entry_rsi_btc   NUMERIC(6,2),
    entry_exp_btc   NUMERIC(10,4),
    entry_tpm       INTEGER,
    entry_lsr       NUMERIC(10,4),
    entry_score     NUMERIC(6,2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eassets_trades_config_id      ON eassets_trades(config_id);
CREATE INDEX IF NOT EXISTS idx_eassets_trades_config_created ON eassets_trades(config_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_eassets_trades_timestamp      ON eassets_trades(trade_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_eassets_trades_symbol         ON eassets_trades(symbol);

-- Order event logs
CREATE TABLE IF NOT EXISTS eassets_order_logs (
    id          BIGSERIAL PRIMARY KEY,
    config_id   BIGINT NOT NULL,
    log_level   VARCHAR(10) NOT NULL DEFAULT 'INFO',
    event       VARCHAR(50) NOT NULL,
    symbol      VARCHAR(30),
    direction   VARCHAR(5),
    exchange    VARCHAR(20),
    message     TEXT,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eassets_order_logs_config ON eassets_order_logs(config_id, created_at DESC);

-- Snapshot metadata (one row per scrape)
CREATE TABLE IF NOT EXISTS eassets_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TEXT UNIQUE NOT NULL,
    exchange    TEXT,
    setup       TEXT,
    mode        TEXT,
    symbols     INTEGER,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source      TEXT,
    btc_reset   BOOLEAN,
    trigger     VARCHAR(20) NOT NULL DEFAULT 'auto'
);
CREATE INDEX IF NOT EXISTS idx_eassets_snapshots_ts ON eassets_snapshots(timestamp DESC);

-- Per-symbol computed metrics for each snapshot
CREATE TABLE IF NOT EXISTS eassets_metrics (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES eassets_snapshots(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    rank            INTEGER,
    score           INTEGER,
    setup           TEXT,
    price           NUMERIC(24,8),
    price_change_1d NUMERIC(14,4),
    exp_1d          NUMERIC(10,4),
    exp_4h          NUMERIC(10,4),
    exp_1h          NUMERIC(10,4),
    oi_trend        NUMERIC(10,4),
    lsr             NUMERIC(10,4),
    lsr_trend       NUMERIC(10,4),
    rsi_4h          NUMERIC(6,2),
    oi_usd          NUMERIC(24,6),
    trades_min      NUMERIC(14,2),
    range_4h        NUMERIC(10,4),
    range_1d        NUMERIC(10,4),
    trades_1d       NUMERIC(18,2),
    toi             NUMERIC(18,2),
    setup_score     INTEGER,
    setup_grade     TEXT,
    raw_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eassets_metrics_snap   ON eassets_metrics(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_eassets_metrics_sym    ON eassets_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_eassets_metrics_rank   ON eassets_metrics(snapshot_id, rank);
CREATE INDEX IF NOT EXISTS idx_eassets_metrics_toi    ON eassets_metrics(snapshot_id, toi DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_eassets_metrics_grade  ON eassets_metrics(setup_grade) WHERE setup_grade = 'SETUP DE OURO';

-- Real-time market snapshots per symbol
CREATE TABLE IF NOT EXISTS eassets_market_snapshots (
    id           BIGSERIAL PRIMARY KEY,
    symbol       VARCHAR(30) NOT NULL,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    price        NUMERIC(24,8),
    rsi_1m       NUMERIC(6,2),
    rsi_5m       NUMERIC(6,2),
    rsi_15m      NUMERIC(6,2),
    rsi_1h       NUMERIC(6,2),
    exp_btc      NUMERIC(10,4),
    trades_min   INTEGER,
    trades_sec   NUMERIC(10,2),
    oi           NUMERIC(24,6),
    oi_trend     NUMERIC(10,4),
    lsr          NUMERIC(10,4),
    lsr_trend    NUMERIC(10,4),
    funding_rate NUMERIC(14,6),
    range_level  NUMERIC(10,4),
    score        NUMERIC(6,2)
);
CREATE INDEX IF NOT EXISTS idx_eassets_mktsnap_sym_time ON eassets_market_snapshots(symbol, captured_at DESC);

-- PCL watchlist (Position Cycle Logic)
CREATE TABLE IF NOT EXISTS eassets_watchlist (
    id                  BIGSERIAL PRIMARY KEY,
    config_id           BIGINT NOT NULL REFERENCES eassets_bot_config(id) ON DELETE CASCADE,
    symbol              VARCHAR(30) NOT NULL,
    state               VARCHAR(20) NOT NULL DEFAULT 'WATCHLIST',
    attempt_count       SMALLINT NOT NULL DEFAULT 0,
    max_attempts        SMALLINT NOT NULL DEFAULT 3,
    total_pnl_so_far    NUMERIC(18,6) NOT NULL DEFAULT 0,
    last_trade_id       BIGINT REFERENCES eassets_trades(id),
    last_stop_reason    VARCHAR(50),
    last_stop_price     NUMERIC(24,8),
    last_entry_price    NUMERIC(24,8),
    cooldown_until      TIMESTAMPTZ,
    stop_range_4h       NUMERIC(10,4),
    stop_range_1d       NUMERIC(10,4),
    stop_exp_btc_1d     NUMERIC(10,4),
    stop_toi            NUMERIC(18,2),
    stop_oi_trend       NUMERIC(10,4),
    stop_lsr            NUMERIC(10,4),
    last_check_at       TIMESTAMPTZ,
    last_check_score    NUMERIC(6,2),
    last_check_passed   BOOLEAN,
    added_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (config_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_eassets_watchlist_config   ON eassets_watchlist(config_id, state);
CREATE INDEX IF NOT EXISTS idx_eassets_watchlist_cooldown ON eassets_watchlist(cooldown_until) WHERE state = 'COOLDOWN';

-- Raw JSON blobs from each scrape
CREATE TABLE IF NOT EXISTS eassets_raw_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT REFERENCES eassets_snapshots(id) ON DELETE SET NULL,
    raw_json    TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status      VARCHAR(20) NOT NULL DEFAULT 'ok',
    error_msg   TEXT
);
CREATE INDEX IF NOT EXISTS idx_eassets_raw_snaps_time ON eassets_raw_snapshots(captured_at DESC);
