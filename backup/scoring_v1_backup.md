# Backup — Algoritmo de Score v1
**Data:** 2026-02-25
**Arquivo de origem:** `backend/scoring.py`
**Motivo do backup:** Refatoração para v2 (APY ajustado por fee + Consistência histórica + Volume por exchange)

---

## Configurações Padrão (system_settings no banco)

### score_thresholds
```json
{ "forte": 75, "moderado": 50, "fraco": 30 }
```

### score_limits
```json
{ "max_volatility": 35, "min_volume": 2000000 }
```

### score_weights
```json
{ "mag": 30, "rr": 30, "vol": 20, "int": 10, "urg": 10 }
```
Total dos pesos padrão: **100 pontos**

---

## Algoritmo Completo v1

### Inputs
| Campo | Fonte | Descrição |
|---|---|---|
| `fundingRate` | Exchange API | Taxa bruta (decimal, ex: 0.00051234) |
| `fundingRatePercent` | Exchange API | Taxa em % (ex: 0.0512) |
| `price24hPcnt` | Exchange API | Variação de preço 24h em % (usado como volatilidade) |
| `volume24h` / `turnover24h` | Exchange API | Volume diário em USD |
| `fundingInterval` | Exchange API | Intervalo de pagamento em horas (geralmente 8) |
| `nextFundingTime` | Exchange API | Timestamp ms do próximo settlement |

### Vetos de Segurança (retornam score = 0 imediatamente)
```python
# Veto 1: Volatilidade extrema
if volatility > max_volatility:  # padrão: 35%
    return veto("Volatilidade extrema (>35%)")

# Veto 2: Liquidez insuficiente
if volume > 0 and volume < min_volume:  # padrão: $2M
    return veto("Liquidez baixíssima (<$2M)")
```

### Componente 1 — Magnitude do Funding (0–30 pontos)
Mede o tamanho absoluto da taxa de funding.

```python
funding_pct = abs(fundingRatePercent)

if funding_pct >= 0.1:                               # >= 0.10%
    mag_score = 30
elif funding_pct >= 0.05:                            # >= 0.05%
    mag_score = 15 + (funding_pct - 0.05) / 0.05 * 15
elif funding_pct >= 0.02:                            # >= 0.02%
    mag_score = 5 + (funding_pct - 0.02) / 0.03 * 10
elif funding_pct >= 0.01:                            # >= 0.01%
    mag_score = (funding_pct - 0.01) / 0.01 * 5
else:                                                # < 0.01%
    mag_score = 0
```

**Problema identificado na análise:** P50 (mediana) do mercado é 0.005% — 67% dos ativos ficam com mag_score = 0.

### Componente 2 — Risco/Retorno (0–30 pontos)
Mede o funding relativo à volatilidade. `ratio = funding_pct / volatility`.

```python
if volatility > 0:
    ratio = funding_pct / volatility
    if ratio >= 0.1:
        rr_score = 30
    elif ratio >= 0.05:
        rr_score = 15 + (ratio - 0.05) / 0.05 * 15
    elif ratio >= 0.02:
        rr_score = 5 + (ratio - 0.02) / 0.03 * 10
    elif ratio >= 0.005:
        rr_score = (ratio - 0.005) / 0.015 * 5
    else:
        rr_score = 0

    # Punição moderada para volatilidade perigosa
    if volatility > 15:
        rr_score = max(0, rr_score - 10)
else:
    rr_score = 25 if funding_pct > 0.01 else 0
```

**Problema identificado:** 68.9% dos ativos ficam com rr_score = 0. Correlação alta com magnitude (dupla contagem de 60% do score).

### Componente 3 — Volume/Liquidez (0–20 pontos)
```python
if volume >= 150_000_000:    # > $150M
    vol_score = 20
elif volume >= 50_000_000:   # > $50M
    vol_score = 15 + (volume - 50_000_000) / 100_000_000 * 5
elif volume >= 10_000_000:   # > $10M
    vol_score = 8 + (volume - 10_000_000) / 40_000_000 * 7
elif volume >= 2_000_000:    # > $2M
    vol_score = (volume - 2_000_000) / 8_000_000 * 8
else:
    vol_score = 0
```

**Problema identificado:** Thresholds favoráveis à Binance. Bybit tem 27.7% dos ativos vetados por volume (P25 da Bybit = $1.6M < $2M).

### Componente 4 — Bônus Intervalo (0–10 pontos)
```python
if interval <= 1:     int_score = 10
elif interval <= 2:   int_score = 8
elif interval <= 4:   int_score = 5
else:                 int_score = 0   # > 4h (inclui 8h padrão)
```

### Componente 5 — Urgência / Timing (-10 a +10 pontos)
```python
if next_funding_time > 0:
    hours_left = (next_funding_time - now_ms) / 3_600_000
    if hours_left <= 1:    urgency_score = 10
    elif hours_left <= 2:  urgency_score = 5
    elif hours_left >= 6:  urgency_score = -10
    elif hours_left >= 4:  urgency_score = -5
    else:                  urgency_score = 0
```

**Problema identificado:** Valor esperado = **-1.875 pts por ativo** em ciclos de 8h (50% do tempo o ativo tem penalidade de -5 ou -10 pts).

### Ajuste de Pesos Dinâmicos
```python
mag_score      = mag_score      * (weights.get("mag", 30) / 30)
rr_score       = rr_score       * (weights.get("rr",  30) / 30)
vol_score      = vol_score      * (weights.get("vol", 20) / 20)
int_score      = int_score      * (weights.get("int", 10) / 10)
urgency_score  = urgency_score  * (weights.get("urg", 10) / 10)
```

### Score Final
```python
total = min(100, max(0, round(mag_score + rr_score + vol_score + int_score + urgency_score)))
```

### Classificação por Thresholds
| Score | Confidence | Signal | shouldOpen |
|---|---|---|---|
| >= forte (75) | FORTE | ✅ SHORT/LONG | True |
| >= moderado (50) | MODERADO | ⚠️ SHORT/LONG | True |
| >= fraco (30) | FRACO | ⚡ SHORT/LONG | False |
| < fraco | EVITAR | ❌ EVITAR | False |
| veto ativo | VETO R/R | ⛔ VETADO | False |

### Estrutura do Retorno
```python
{
    "score": int,          # 0-100
    "confidence": str,     # FORTE | MODERADO | FRACO | EVITAR | VETO R/R
    "signal": str,         # ✅ SHORT | ⚠️ LONG | ❌ EVITAR | ⛔ VETADO
    "shouldOpen": bool,
    "direction": str,      # SHORT | LONG | NEUTRO
    "breakdown": {
        "magnitude": float,    # 0-30
        "riskReward": float,   # 0-30
        "volume": float,       # 0-20
        "interval": float,     # 0-10
        "urgency": float,      # -10 a +10
    },
    "reasons": [str]
}
```

---

## Análise de Qualidade (dados reais — 186.180 snapshots)

| Exchange | P50 funding | P90 funding | P99 funding |
|---|---|---|---|
| Binance | 0.0050% | 0.0288% | 0.2311% |
| Bybit | 0.0050% | 0.0319% | 0.3045% |

| Threshold de Magnitude | % dos snapshots |
|---|---|
| >= 0.10% (score máx) | 3.06% |
| >= 0.05% | 6.27% |
| >= 0.01% (mínimo com score) | 33.31% |
| **< 0.01% (score zero)** | **66.69%** |

**Score do sistema v1: 4.5/10** — funciona mais como filtro binário via vetos do que como ranqueador fino.

---

## O que muda na v2

| Componente v1 | Substituído por | Razão |
|---|---|---|
| Magnitude (0-30) + R/R (0-30) | APY líquido ajustado por fee (0-40) | Elimina dupla contagem e introduz métrica economicamente correta |
| Urgência (-10 a +10) | Consistência histórica (0-15) | Elimina viés negativo estrutural de -1.875 pts/ativo |
| Volume único threshold | Volume por exchange (Binance/Bybit separados) | Corrige veto excessivo na Bybit (27.7% dos ativos) |

Novos pesos padrão (score_weights v2): `{ "apy": 40, "vol": 20, "int": 10, "consistency": 15 }`
