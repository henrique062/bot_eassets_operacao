-- Migration: histórico de análises IA para configuração de score.
-- Motivo: persistir análise, projeção e aplicação confirmada por modo/exchange.

CREATE TABLE IF NOT EXISTS score_ai_analyses (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange VARCHAR(30) NOT NULL,
    mode VARCHAR(30) NOT NULL,
    window_days INT NOT NULL DEFAULT 7,
    current_settings JSONB NOT NULL,
    recommended_settings JSONB NOT NULL,
    analysis_markdown TEXT NOT NULL DEFAULT '',
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    projection JSONB NOT NULL DEFAULT '{}'::jsonb,
    market_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    applied BOOLEAN NOT NULL DEFAULT FALSE,
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_score_ai_analyses_user_created
    ON score_ai_analyses(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_score_ai_analyses_applied_created
    ON score_ai_analyses(applied, created_at DESC);
