-- ============================================================
-- Migration: 20260221_add_users_auth.sql
-- Sistema de autenticação multi-usuário
-- ============================================================

-- Tabela de usuários
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL          PRIMARY KEY,
    email           VARCHAR(255)    NOT NULL UNIQUE,
    password_hash   TEXT            NOT NULL,
    role            VARCHAR(20)     NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    active          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Trigger updated_at para users
CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- Tabela de configurações por usuário (substitui system_settings para dados sensíveis)
CREATE TABLE IF NOT EXISTS user_settings (
    id          SERIAL          PRIMARY KEY,
    user_id     INTEGER         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key         VARCHAR(255)    NOT NULL,
    value       JSONB           NOT NULL DEFAULT '{}'::jsonb,
    description TEXT,
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_user_settings_user_key ON user_settings (user_id, key);

-- Adicionar user_id em paper_config (nullable para não quebrar dados existentes)
ALTER TABLE paper_config
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_paper_config_user_id ON paper_config (user_id);

-- Adicionar user_id em real_config
ALTER TABLE real_config
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_real_config_user_id ON real_config (user_id);

-- Adicionar user_id em saved_strategies
ALTER TABLE saved_strategies
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_saved_strategies_user_id ON saved_strategies (user_id);

-- ============================================================
-- Inserir usuário master (senha: b91318244 com bcrypt via pgcrypto)
-- ============================================================
INSERT INTO users (email, password_hash, role)
VALUES (
    'henriquedev062@gmail.com',
    crypt('b91318244', gen_salt('bf', 12)),
    'admin'
)
ON CONFLICT (email) DO NOTHING;

-- Migrar dados existentes para o usuário master
DO $$
DECLARE
    master_id INTEGER;
BEGIN
    SELECT id INTO master_id FROM users WHERE email = 'henriquedev062@gmail.com';

    IF master_id IS NOT NULL THEN
        UPDATE paper_config SET user_id = master_id WHERE user_id IS NULL;
        UPDATE real_config SET user_id = master_id WHERE user_id IS NULL;
        UPDATE saved_strategies SET user_id = master_id WHERE user_id IS NULL;

        -- Migrar api_keys de system_settings para user_settings
        INSERT INTO user_settings (user_id, key, value, description)
        SELECT master_id, key, value, description
        FROM system_settings
        WHERE key IN ('api_keys_binance', 'api_keys_bybit')
        ON CONFLICT (user_id, key) DO NOTHING;
    END IF;
END $$;
