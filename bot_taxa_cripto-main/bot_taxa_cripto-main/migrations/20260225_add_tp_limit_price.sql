-- Adiciona persistência do preço da ordem TP limit em posições abertas
ALTER TABLE real_positions
    ADD COLUMN IF NOT EXISTS tp_limit_price NUMERIC(24, 8) DEFAULT NULL;
