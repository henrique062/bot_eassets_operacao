-- Adiciona configurações dedicadas ao scoring do modo counter-trend.
-- Mantém separado do modo de coleta de taxa para permitir calibração independente.

INSERT INTO system_settings (key, value, description)
VALUES
    (
        'score_thresholds_counter',
        '{"forte": 75, "moderado": 50, "fraco": 30}'::jsonb,
        'Thresholds de confiança do score no modo counter-trend'
    ),
    (
        'score_limits_counter',
        '{"min_volume": 2000000, "min_funding_rate_pct": 0.01}'::jsonb,
        'Vetos do counter-trend: volume mínimo e funding mínimo'
    ),
    (
        'score_weights_counter',
        '{"extremity": 40, "persistence": 30, "volume": 20, "volatility_bonus": 10}'::jsonb,
        'Pesos do counter-trend: extremidade, persistência, volume e bônus de volatilidade'
    )
ON CONFLICT (key) DO NOTHING;
