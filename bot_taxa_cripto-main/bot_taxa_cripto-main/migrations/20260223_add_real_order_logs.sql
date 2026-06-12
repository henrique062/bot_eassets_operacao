-- Tabela de logs de ordens e erros do real trader
-- Registra tentativas, respostas de API e erros por bot (config_id)

CREATE TABLE IF NOT EXISTS real_order_logs (
    id          BIGSERIAL PRIMARY KEY,
    config_id   INTEGER      NOT NULL,
    log_level   VARCHAR(10)  NOT NULL DEFAULT 'INFO',  -- INFO | WARN | ERROR
    event       VARCHAR(60)  NOT NULL,                 -- open_attempt | open_success | close_attempt | close_success | direction_skip | symbol_not_found | maker_fallback | api_error | error
    symbol      VARCHAR(30),
    direction   VARCHAR(10),
    exchange    VARCHAR(20),
    message     TEXT,
    details     JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_real_order_logs_config_id ON real_order_logs(config_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_real_order_logs_created_at ON real_order_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_real_order_logs_level ON real_order_logs(config_id, log_level);
