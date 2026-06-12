-- Migração: tabela de estratégias salvas pelo usuário
-- Data: 2026-02-21

CREATE TABLE IF NOT EXISTS saved_strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    config JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_saved_strategies_name ON saved_strategies(name);
