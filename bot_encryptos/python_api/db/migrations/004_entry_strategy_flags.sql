-- =============================================================================
-- Migration 004 — Flags de estratégia de entrada
-- Idempotente. Controlam o rigor da entrada do bot (lidos pelo endpoint
-- entry-candidates, que é a fonte de decisão do motor).
-- =============================================================================

-- Exigir Reset do BTC (RSI 30m/1h <= max_rsi_btc) para liberar entradas.
-- Padrão TRUE = fiel à metodologia (nunca comprar em alta vertical).
ALTER TABLE eassets_bot_config
    ADD COLUMN IF NOT EXISTS require_btc_reset BOOLEAN NOT NULL DEFAULT TRUE;

-- Aceitar setups PARCIAL além de SETUP DE OURO. Padrão FALSE = só Setup de Ouro.
ALTER TABLE eassets_bot_config
    ADD COLUMN IF NOT EXISTS allow_partial_setup BOOLEAN NOT NULL DEFAULT FALSE;

-- Exigir funding negativo no momento da entrada (shorts pagando = munição p/ alta).
-- Padrão FALSE = não obrigatório (já é um dos 7 critérios do checklist).
ALTER TABLE eassets_bot_config
    ADD COLUMN IF NOT EXISTS require_funding_negative BOOLEAN NOT NULL DEFAULT FALSE;
