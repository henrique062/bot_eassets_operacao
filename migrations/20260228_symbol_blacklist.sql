-- Migration: tabela de blacklist inteligente de símbolos por usuário
-- Rastreia losses consecutivos e cooldown decidido pela IA

CREATE TABLE IF NOT EXISTS symbol_blacklist (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(30) NOT NULL,
    consecutive_losses INT NOT NULL DEFAULT 0,
    blacklisted_until TIMESTAMPTZ,      -- NULL se decidido não bloquear
    ai_reason VARCHAR(300),
    ai_analysis TEXT,
    cleared_manually BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_symbol_blacklist_active
    ON symbol_blacklist(user_id, blacklisted_until)
    WHERE cleared_manually = FALSE;
