-- Migration: Adiciona colunas para reconciliação de trades com a exchange
-- Data: 2026-02-21

ALTER TABLE real_positions ADD COLUMN IF NOT EXISTS open_order_id TEXT;
ALTER TABLE real_trades ADD COLUMN IF NOT EXISTS reconciled_at TIMESTAMPTZ;
