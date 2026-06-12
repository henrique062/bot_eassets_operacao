-- Tabela para armazenar análises IA de bots
CREATE TABLE IF NOT EXISTS bot_ai_analyses (
    id SERIAL PRIMARY KEY,
    config_id INT REFERENCES real_config(id) ON DELETE CASCADE,
    analysis_text TEXT,
    suggested_config JSONB,
    applied BOOLEAN DEFAULT FALSE,
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    trigger_type VARCHAR(20) DEFAULT 'manual'
);

CREATE INDEX IF NOT EXISTS idx_bot_ai_analyses_config ON bot_ai_analyses(config_id);
