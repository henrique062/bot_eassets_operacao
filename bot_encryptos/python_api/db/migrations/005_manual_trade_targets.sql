-- =============================================================================
-- Migration 005 - Alvos manuais de trade pelo painel
-- Idempotente. Permite armar moedas especificas manualmente, sempre com foco
-- inicial em paper trading.
-- =============================================================================

CREATE TABLE IF NOT EXISTS eassets_trade_targets (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    mode            TEXT NOT NULL DEFAULT 'paper',
    note            TEXT,
    source          TEXT NOT NULL DEFAULT 'panel',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    activated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deactivated_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_eassets_trade_targets_symbol_mode UNIQUE (symbol, mode)
);

CREATE INDEX IF NOT EXISTS idx_eassets_trade_targets_active
    ON eassets_trade_targets(active, mode, updated_at DESC);
