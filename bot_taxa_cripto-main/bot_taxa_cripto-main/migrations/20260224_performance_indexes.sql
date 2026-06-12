-- Índices de performance para queries frequentes (SSE, status, trades)
-- Reduz CPU do VPS ao acelerar as queries executadas a cada 1-2s

CREATE INDEX IF NOT EXISTS idx_real_positions_config_symbol ON real_positions(config_id, symbol);
CREATE INDEX IF NOT EXISTS idx_paper_positions_config_symbol ON paper_positions(config_id, symbol);
CREATE INDEX IF NOT EXISTS idx_real_trades_config_created ON real_trades(config_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_trades_config_created ON paper_trades(config_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_real_config_active_user ON real_config(active, user_id);
CREATE INDEX IF NOT EXISTS idx_paper_config_active_user ON paper_config(active, user_id);
CREATE INDEX IF NOT EXISTS idx_real_order_logs_config_created ON real_order_logs(config_id, created_at DESC);
