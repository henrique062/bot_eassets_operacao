-- ============================================================
-- Migration: 20260222_optimize_indexes_and_schema.sql
-- Otimização de índices para real_config, real_trades e real_positions
-- ============================================================
-- Autor: database-agent
-- Data: 2026-02-22
--
-- Contexto: Verificação do schema revelou que as tabelas de trading real
-- (real_config, real_trades, real_positions) não possuem índices nas
-- colunas de foreign key e colunas de filtro mais utilizadas pelas
-- queries do real_trader.py. As tabelas de paper trading já possuem
-- os índices equivalentes desde a migration inicial.
--
-- Colunas já existentes (confirmado no banco antes desta migration):
--   real_config.updated_at      -- presente
--   real_config.stop_loss_usd   -- presente
--   real_trades.reconciled_at   -- presente (via 20260221_reconcile_trades.sql)
--   real_positions.open_order_id -- presente (via 20260221_reconcile_trades.sql)
--
-- INTEGRIDADE: 0 real_trades órfãos, 0 real_positions órfãs (verificado)
-- ============================================================

-- ============================================================
-- UP
-- ============================================================

-- ------------------------------------------------------------
-- real_config: índice composto user_id + active
-- Justificativa: queries de busca por sessões ativas de um usuário
-- específico são a operação mais frequente do real_trader.py
-- (ex: SELECT ... FROM real_config WHERE user_id=$1 AND active=TRUE)
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_real_config_user_active
    ON real_config (user_id, active);

-- ------------------------------------------------------------
-- real_config: índice parcial para sessões ativas
-- Justificativa: o loop principal do real_trader consulta apenas
-- sessões ativas (active=TRUE). Índice parcial é mais eficiente
-- pois indexa apenas o subconjunto relevante.
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_real_config_active
    ON real_config (active) WHERE active = TRUE;

-- ------------------------------------------------------------
-- real_trades: índice em config_id (foreign key)
-- Justificativa: foreign keys sem índice causam sequential scans
-- em JOINs e lookups. Essencial para queries de histórico de trades
-- por sessão (ex: SELECT ... FROM real_trades WHERE config_id=$1)
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_real_trades_config_id
    ON real_trades (config_id);

-- ------------------------------------------------------------
-- real_trades: índice em trade_timestamp DESC
-- Justificativa: listagens de trades são sempre ordenadas por data
-- decrescente. Sem este índice, ORDER BY trade_timestamp DESC
-- exige full scan + sort em tabelas grandes.
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_real_trades_timestamp
    ON real_trades (trade_timestamp DESC);

-- ------------------------------------------------------------
-- real_positions: índice em config_id (foreign key)
-- Justificativa: o real_trader.py consulta posições abertas por
-- config_id frequentemente no loop de monitoramento
-- (ex: SELECT ... FROM real_positions WHERE config_id=$1)
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_real_positions_config_id
    ON real_positions (config_id);

-- ============================================================
-- Verificação pós-migration (comentado — execute manualmente se necessário)
-- ============================================================
-- SELECT indexname, tablename, indexdef
-- FROM pg_indexes
-- WHERE tablename IN ('real_config', 'real_trades', 'real_positions')
-- ORDER BY tablename, indexname;

-- ============================================================
-- LIMPEZA OPCIONAL: Remove snapshots de funding mais antigos que 30 dias
-- ATENÇÃO: Descomente apenas após análise do volume de dados
-- ============================================================
-- DELETE FROM funding_rate_snapshots WHERE created_at < NOW() - INTERVAL '30 days';

-- ============================================================
-- DOWN
-- Rollback: remove apenas os índices criados por esta migration
-- ============================================================
-- DROP INDEX IF EXISTS idx_real_config_user_active;
-- DROP INDEX IF EXISTS idx_real_config_active;
-- DROP INDEX IF EXISTS idx_real_trades_config_id;
-- DROP INDEX IF EXISTS idx_real_trades_timestamp;
-- DROP INDEX IF EXISTS idx_real_positions_config_id;
