CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(255) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Inserir configurações padrão de Score caso não existam
INSERT INTO system_settings (key, value, description)
VALUES 
    ('score_thresholds', '{"forte": 75, "moderado": 50, "fraco": 30}'::jsonb, 'Pontuação mínima para classificar as Oportunidades do Scanner de Moedas.'),
    ('default_leverage', '1'::jsonb, 'Alavancagem Padrão sugerida ao criar bots.'),
    ('default_stop_loss', '1.5'::jsonb, 'Stop Loss Padrão em Porcentagem.')
ON CONFLICT (key) DO NOTHING;
