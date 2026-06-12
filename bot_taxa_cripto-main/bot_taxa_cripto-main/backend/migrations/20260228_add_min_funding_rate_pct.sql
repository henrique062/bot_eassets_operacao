-- Motivo: permitir configurar funding rate minimo (%) por sessao de bot real.
ALTER TABLE real_config
ADD COLUMN IF NOT EXISTS min_funding_rate_pct NUMERIC DEFAULT 0.001;
