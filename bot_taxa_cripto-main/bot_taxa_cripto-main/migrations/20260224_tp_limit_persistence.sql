-- Adiciona coluna tp_limit_order_id em real_positions
-- Armazena o ID da ordem TP limit colocada na exchange no momento da abertura.
-- Permite rastrear e retomar o monitoramento da TP após restart do servidor.

ALTER TABLE real_positions
    ADD COLUMN IF NOT EXISTS tp_limit_order_id TEXT DEFAULT NULL;
