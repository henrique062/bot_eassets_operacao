-- ============================================================
-- Migration: 20260221_initial_schema.sql
-- Criação do schema inicial do bot de taxa de funding
-- ============================================================

-- UP

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ------------------------------------------------------------
-- Tabela: paper_config
-- Armazena configurações de sessões de paper trading
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_config (
    id              SERIAL          PRIMARY KEY,
    session_name    VARCHAR(100)    NOT NULL DEFAULT 'default',
    symbols         TEXT[]          NOT NULL DEFAULT '{}',
    capital         NUMERIC(18, 8)  NOT NULL DEFAULT 1000.0 CHECK (capital > 0),
    balance         NUMERIC(18, 8)  NOT NULL DEFAULT 1000.0,
    leverage        SMALLINT        NOT NULL DEFAULT 1 CHECK (leverage BETWEEN 1 AND 20),
    fee_type        VARCHAR(10)     NOT NULL DEFAULT 'maker' CHECK (fee_type IN ('maker', 'taker')),
    fee_rate        NUMERIC(10, 6)  NOT NULL DEFAULT 0.0002 CHECK (fee_rate >= 0),
    auto_mode       BOOLEAN         NOT NULL DEFAULT TRUE,
    exchange        VARCHAR(20)     NOT NULL DEFAULT 'binance' CHECK (exchange IN ('binance', 'bybit')),
    active          BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_config_active_unique
    ON paper_config (active) WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_paper_config_active
    ON paper_config (active, exchange);

-- ------------------------------------------------------------
-- Tabela: paper_positions
-- Posições abertas no paper trading
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_positions (
    id                  SERIAL          PRIMARY KEY,
    config_id           INTEGER         NOT NULL REFERENCES paper_config(id) ON DELETE CASCADE,
    symbol              VARCHAR(30)     NOT NULL,
    direction           VARCHAR(5)      NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price         NUMERIC(24, 8)  NOT NULL CHECK (entry_price > 0),
    size                NUMERIC(24, 8)  NOT NULL CHECK (size > 0),
    value               NUMERIC(24, 8)  NOT NULL CHECK (value > 0),
    funding_rate        NUMERIC(14, 8)  NOT NULL DEFAULT 0,
    funding_rate_pct    NUMERIC(14, 6)  NOT NULL DEFAULT 0,
    open_time           VARCHAR(30)     NULL,
    open_timestamp      BIGINT          NOT NULL,
    exchange            VARCHAR(20)     NOT NULL DEFAULT 'binance' CHECK (exchange IN ('binance', 'bybit')),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_positions_config_symbol
    ON paper_positions (config_id, symbol);

CREATE INDEX IF NOT EXISTS idx_paper_positions_config_id
    ON paper_positions (config_id);

CREATE INDEX IF NOT EXISTS idx_paper_positions_exchange_symbol
    ON paper_positions (exchange, symbol);

-- ------------------------------------------------------------
-- Tabela: paper_trades
-- Histórico de trades fechados no paper trading
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_trades (
    id                  BIGSERIAL       PRIMARY KEY,
    config_id           INTEGER         NOT NULL REFERENCES paper_config(id) ON DELETE CASCADE,
    symbol              VARCHAR(30)     NOT NULL,
    direction           VARCHAR(5)      NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price         NUMERIC(24, 8)  NOT NULL,
    exit_price          NUMERIC(24, 8)  NOT NULL,
    funding_rate        NUMERIC(14, 6)  NOT NULL,
    funding_pnl         NUMERIC(18, 6)  NOT NULL DEFAULT 0,
    price_pnl           NUMERIC(18, 6)  NOT NULL DEFAULT 0,
    fee_cost            NUMERIC(18, 6)  NOT NULL DEFAULT 0 CHECK (fee_cost >= 0),
    total_pnl           NUMERIC(18, 6)  NOT NULL DEFAULT 0,
    total_pnl_pct       NUMERIC(14, 6)  NOT NULL DEFAULT 0,
    balance_after       NUMERIC(18, 6)  NOT NULL,
    open_time           VARCHAR(30)     NULL,
    close_time          VARCHAR(30)     NULL,
    trade_timestamp     BIGINT          NOT NULL,
    exchange            VARCHAR(20)     NOT NULL DEFAULT 'binance' CHECK (exchange IN ('binance', 'bybit')),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_config_ts
    ON paper_trades (config_id, trade_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_paper_trades_exchange_symbol
    ON paper_trades (exchange, symbol);

CREATE INDEX IF NOT EXISTS idx_paper_trades_timestamp
    ON paper_trades (trade_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_paper_trades_config_symbol
    ON paper_trades (config_id, symbol, trade_timestamp DESC);

-- ------------------------------------------------------------
-- Tabela: funding_rate_snapshots
-- Snapshots históricos de funding rates coletados pela exchange
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS funding_rate_snapshots (
    id                  BIGSERIAL       PRIMARY KEY,
    exchange            VARCHAR(20)     NOT NULL CHECK (exchange IN ('binance', 'bybit')),
    symbol              VARCHAR(30)     NOT NULL,
    funding_rate        NUMERIC(14, 8)  NOT NULL,
    funding_rate_pct    NUMERIC(14, 6)  NOT NULL,
    monthly_rate        NUMERIC(14, 4)  NOT NULL DEFAULT 0,
    last_price          NUMERIC(24, 8)  NOT NULL DEFAULT 0,
    volume_24h          NUMERIC(28, 4)  NOT NULL DEFAULT 0,
    price_24h_pcnt      NUMERIC(10, 4)  NOT NULL DEFAULT 0,
    funding_interval    SMALLINT        NOT NULL DEFAULT 8,
    captured_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_frs_exchange_symbol_captured
    ON funding_rate_snapshots (exchange, symbol, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_frs_captured_at
    ON funding_rate_snapshots (captured_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_frs_dedup
    ON funding_rate_snapshots (exchange, symbol, captured_at);

CREATE INDEX IF NOT EXISTS idx_frs_funding_rate_captured
    ON funding_rate_snapshots (funding_rate, captured_at DESC);

-- ------------------------------------------------------------
-- Função e Triggers: atualização automática de updated_at
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_paper_config_updated_at
    BEFORE UPDATE ON paper_config
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE OR REPLACE TRIGGER trg_paper_positions_updated_at
    BEFORE UPDATE ON paper_positions
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE OR REPLACE TRIGGER trg_paper_trades_updated_at
    BEFORE UPDATE ON paper_trades
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
