-- Adiciona coluna trailing_stop_pct na tabela real_config
-- Trailing stop: fecha posição se o preço recuar X% do pico (LONG) ou do vale (SHORT)
ALTER TABLE real_config
    ADD COLUMN IF NOT EXISTS trailing_stop_pct NUMERIC(10, 2) DEFAULT NULL;
