-- Migration: adiciona coluna tp_limit_price em real_positions
-- Problema: coluna ausente causava perda de rastreamento de TP Limit orders
-- Resultado: exchange_sync negativos gerados incorretamente a partir de 26/02 01:00 BRT

ALTER TABLE real_positions ADD COLUMN IF NOT EXISTS tp_limit_price NUMERIC;
ALTER TABLE real_positions ADD COLUMN IF NOT EXISTS tp_limit_order_id TEXT;

-- Índice para lookup rápido por order_id
CREATE INDEX IF NOT EXISTS idx_real_positions_tp_limit_order_id ON real_positions(tp_limit_order_id) WHERE tp_limit_order_id IS NOT NULL;

COMMENT ON COLUMN real_positions.tp_limit_price IS 'Preço alvo do TP Limit order enviado para a exchange';
COMMENT ON COLUMN real_positions.tp_limit_order_id IS 'ID da ordem TP Limit na exchange para rastreamento e cancelamento';
