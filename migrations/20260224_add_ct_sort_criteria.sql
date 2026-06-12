-- Adiciona coluna ct_sort_criteria em real_config
-- Armazena o critério de seleção de símbolos para estratégia Contra-Tendência:
-- 'score'        → ordena pelo score composto (padrão)
-- 'funding_rate' → ordena pelo maior funding rate absoluto

ALTER TABLE real_config
    ADD COLUMN IF NOT EXISTS ct_sort_criteria VARCHAR(20) NOT NULL DEFAULT 'score';
