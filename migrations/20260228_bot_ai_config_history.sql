-- Migration: bot_ai_config_history
-- Tabela para armazenar o histórico de alterações automáticas de config de bots pela IA,
-- com comparação de desempenho antes/depois de cada mudança.

CREATE TABLE IF NOT EXISTS bot_ai_config_history (
    id SERIAL PRIMARY KEY,
    config_id INT NOT NULL REFERENCES real_config(id) ON DELETE CASCADE,
    analysis_id INT REFERENCES bot_ai_analyses(id),
    trigger_type VARCHAR(30) NOT NULL DEFAULT 'manual',
    -- Mudanças aplicadas: {param: {from: val_antigo, to: val_novo}, ...}
    changes_applied JSONB NOT NULL DEFAULT '{}',
    -- Desempenho nos 10 trades ANTES desta mudança
    perf_trades_before INT DEFAULT 0,
    perf_pnl_before FLOAT DEFAULT 0.0,
    -- Desempenho nos 10 trades DEPOIS desta mudança (preenchido na próxima análise)
    perf_trades_after INT DEFAULT 0,
    perf_pnl_after FLOAT DEFAULT 0.0,
    perf_evaluated_at TIMESTAMPTZ,
    -- Referência à mudança anterior (para comparação encadeada)
    prev_history_id INT REFERENCES bot_ai_config_history(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bot_ai_config_history_config
    ON bot_ai_config_history(config_id, created_at DESC);
