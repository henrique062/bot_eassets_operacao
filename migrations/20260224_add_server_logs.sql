-- Migration: cria tabela de logs do servidor
-- Data: 2026-02-24

CREATE TABLE IF NOT EXISTS server_logs (
    id         SERIAL PRIMARY KEY,
    level      VARCHAR(10)  NOT NULL,          -- INFO / WARNING / ERROR / DEBUG
    module     VARCHAR(100),                   -- Snapshot, uvicorn, asyncpg, etc.
    message    TEXT         NOT NULL,
    created_at TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_server_logs_created_at ON server_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_server_logs_level      ON server_logs(level);
