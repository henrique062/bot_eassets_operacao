-- =============================================================================
-- Migration 003 — Monitoração de moedas + modo Paper Trading
-- Idempotente (IF NOT EXISTS). Aplicada automaticamente no startup do python_api.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Monitoração: moedas que o usuário marca para acompanhar a partir do Painel.
-- Guarda o preço/score/setup no momento da marcação para calcular variação.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eassets_monitored (
    id               BIGSERIAL PRIMARY KEY,
    symbol           TEXT NOT NULL,
    note             TEXT,
    marked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mark_price       NUMERIC(24,8),
    mark_score       INTEGER,
    mark_setup       TEXT,
    mark_snapshot_id BIGINT,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    unmarked_at      TIMESTAMPTZ
);

-- Apenas uma marcação ativa por símbolo (re-marcar reativa/atualiza)
CREATE UNIQUE INDEX IF NOT EXISTS idx_eassets_monitored_active_symbol
    ON eassets_monitored(symbol) WHERE active;
CREATE INDEX IF NOT EXISTS idx_eassets_monitored_active
    ON eassets_monitored(active, marked_at DESC);

-- ---------------------------------------------------------------------------
-- Paper Trading: distingue operações simuladas (teste) das reais.
-- Por segurança, o padrão é PAPER (true) — o bot só opera de verdade quando
-- explicitamente desativado.
-- ---------------------------------------------------------------------------
ALTER TABLE eassets_bot_config
    ADD COLUMN IF NOT EXISTS paper_trading BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE eassets_positions
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'paper';

ALTER TABLE eassets_trades
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'paper';

CREATE INDEX IF NOT EXISTS idx_eassets_positions_mode ON eassets_positions(mode);
CREATE INDEX IF NOT EXISTS idx_eassets_trades_mode    ON eassets_trades(mode);
