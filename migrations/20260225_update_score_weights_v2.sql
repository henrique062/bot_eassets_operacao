-- Atualiza score_weights para o modelo v2 (APY + Consistência)
-- Pesos anteriores (v1): mag=30, rr=30, vol=20, int=10, urg=10
-- Pesos novos (v2): apy=40, vol=20, int=10, consistency=15

UPDATE system_settings
SET value = '{"apy": 40, "vol": 20, "int": 10, "consistency": 15}'::jsonb,
    updated_at = NOW()
WHERE key = 'score_weights';

-- Garante que existe (caso não tenha sido inserido ainda)
INSERT INTO system_settings (key, value, description)
VALUES (
    'score_weights',
    '{"apy": 40, "vol": 20, "int": 10, "consistency": 15}',
    'Pesos dos componentes do score v2: APY líquido (0-40), Volume (0-20), Intervalo (0-10), Consistência histórica (0-15)'
)
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = NOW();
