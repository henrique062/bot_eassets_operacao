-- ============================================================
-- Migration: 20260221_add_stop_loss_multi_bots.sql
-- Adiciona stop loss configurável e suporte a múltiplos bots ativos
-- ============================================================

-- 1. Remover unique index que impede múltiplos bots ativos simultaneamente
DROP INDEX IF EXISTS idx_paper_config_active_unique;

-- 2. Adicionar colunas de stop loss em paper_config
ALTER TABLE paper_config
    ADD COLUMN IF NOT EXISTS stop_loss_pct   NUMERIC(8, 4)   NULL,      -- % de variação do preço (ex: 2.0 = fechar com -2%)
    ADD COLUMN IF NOT EXISTS stop_loss_usd   NUMERIC(18, 6)  NULL,      -- Perda máxima em USD por posição
    ADD COLUMN IF NOT EXISTS started_at      TIMESTAMPTZ     NULL,      -- quando o bot foi iniciado
    ADD COLUMN IF NOT EXISTS ended_at        TIMESTAMPTZ     NULL;      -- quando o bot foi parado

-- 3. Adicionar close_reason em paper_trades para registrar o motivo do fechamento
ALTER TABLE paper_trades
    ADD COLUMN IF NOT EXISTS close_reason    VARCHAR(30)     NOT NULL DEFAULT 'funding';
    -- Valores possíveis: 'funding', 'stop_loss_pct', 'stop_loss_usd', 'manual'

-- 4. Recriar índice não único para consultas por active
DROP INDEX IF EXISTS idx_paper_config_active;
CREATE INDEX IF NOT EXISTS idx_paper_config_active ON paper_config (active, exchange);
CREATE INDEX IF NOT EXISTS idx_paper_config_active_created ON paper_config (active, created_at DESC);
