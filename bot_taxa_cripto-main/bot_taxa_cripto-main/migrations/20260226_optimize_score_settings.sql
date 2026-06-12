-- ============================================================
-- Otimização de parâmetros de score baseada em auditoria quantitativa
-- Período de análise: 25-26/02/2026 (86 trades reais)
-- ============================================================

-- ── COLETA DE TAXA ─────────────────────────────────────────
-- Problema identificado: score satura em 85 e FORTE iniciava em 80
-- (spread de apenas 5 pts). Aumentando thresholds para exigir qualidade real.
-- Dados: auto_highest_rate PF=0.88 — raising the bar to filter weak signals.

UPDATE system_settings SET
    value = '{"forte": 82, "moderado": 70, "fraco": 50}',
    updated_at = NOW()
WHERE key = 'score_thresholds';
-- forte: 80→82 (máx=85, exige near-perfect)
-- moderado: 60→70 (elimina zona cinza de baixo retorno)
-- fraco: 40→50 (referência mínima mais exigente)

UPDATE system_settings SET
    value = '{"max_volatility": 25, "min_volume": 2000000}',
    updated_at = NOW()
WHERE key = 'score_limits';
-- max_volatility: 35%→25% (volatilidade alta destrói price PNL na coleta)
-- min_volume: mantido em $2M

-- ── COUNTER-TENDÊNCIA ──────────────────────────────────────
-- Inserir ou atualizar configurações CT no banco
-- Problema crítico: funding_min era 0.01% — aceitava sinais fracos
-- Dados: trades com funding < -0.15%/ciclo tiveram win rate 87.5% e avg +$0.52
--        trades com funding -0.10% a -0.15% tiveram win rate 62% e avg +$0.11

INSERT INTO system_settings (key, value, description, updated_at)
VALUES (
    'score_thresholds_counter',
    '{"forte": 80, "moderado": 65, "fraco": 45}',
    'Thresholds de confiança para counter-trend. forte: 75→80 (exige sinal mais robusto), moderado: 50→65, fraco: 30→45.',
    NOW()
)
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();

INSERT INTO system_settings (key, value, description, updated_at)
VALUES (
    'score_limits_counter',
    '{"min_volume": 2000000, "min_funding_rate_pct": 0.10}',
    'Filtros de segurança para counter-trend. min_funding: 0.01%→0.10% (dados: funding<0.10%/ciclo não gera edge real).',
    NOW()
)
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();

INSERT INTO system_settings (key, value, description, updated_at)
VALUES (
    'score_weights_counter',
    '{"extremity": 40, "persistence": 30, "volume": 20, "volatility_bonus": 10}',
    'Pesos do algoritmo de counter-trend. Mantidos conforme auditoria — estrutura correta, sem saturação.',
    NOW()
)
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();

-- Verificação final
SELECT key, value FROM system_settings
WHERE key IN (
    'score_thresholds', 'score_limits', 'score_weights',
    'score_thresholds_counter', 'score_limits_counter', 'score_weights_counter'
)
ORDER BY key;
