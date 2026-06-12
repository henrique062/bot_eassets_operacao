-- Adiciona colunas de Break-Even automático e TP Parcial na tabela real_config
ALTER TABLE real_config
    ADD COLUMN IF NOT EXISTS break_even_at_pct  NUMERIC,
    ADD COLUMN IF NOT EXISTS partial_tp_pct      NUMERIC,
    ADD COLUMN IF NOT EXISTS partial_tp_size     NUMERIC DEFAULT 50;

COMMENT ON COLUMN real_config.break_even_at_pct IS
    'Quando lucro de preço atingir este % move o stop loss para o preço de entrada (break-even).';
COMMENT ON COLUMN real_config.partial_tp_pct IS
    'Quando lucro de preço atingir este % fecha partial_tp_size % da posição.';
COMMENT ON COLUMN real_config.partial_tp_size IS
    'Percentual da posição a fechar no TP parcial (padrão 50%).';
