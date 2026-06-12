-- Motivo: persistir entradas limit manuais pendentes para retomar monitoramento após restart.
CREATE TABLE IF NOT EXISTS real_pending_entries (
    id BIGSERIAL PRIMARY KEY,
    config_id INT NOT NULL REFERENCES real_config(id) ON DELETE CASCADE,
    user_id INT NULL REFERENCES users(id) ON DELETE SET NULL,
    exchange VARCHAR(20) NOT NULL DEFAULT 'binance',
    symbol VARCHAR(30) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    side VARCHAR(10) NOT NULL,
    size NUMERIC(24,8) NOT NULL,
    limit_price NUMERIC(24,8) NOT NULL,
    order_id TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_real_pending_entries_config_status
    ON real_pending_entries(config_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_real_pending_entries_user_exchange
    ON real_pending_entries(user_id, exchange, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_real_pending_entries_order_id
    ON real_pending_entries(order_id);
