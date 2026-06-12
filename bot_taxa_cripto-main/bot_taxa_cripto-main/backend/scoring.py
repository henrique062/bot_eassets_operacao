"""
Sistema de scoring risco/retorno para funding rate trading.
Calcula um score de 0-100 para cada ativo baseado em múltiplos fatores.

Modelo v3:
- APY Líquido ajustado por fee (0-40 pontos)
- Volume/Liquidez por exchange (0-20 pontos)
- Intervalo de pagamento (0-10 pontos)
- Consistência histórica da direção (0-15 pontos)
- Momentum da taxa (−15 a +15 pontos): bônus se acelerando, penalidade se decaindo
Total máximo teórico: 100 pontos | mínimo com penalidade: 70 pontos base
"""
import json
from cachetools import TTLCache
import database as db

# Cache de configurações para não bater no DB a cada asset.
# maxsize=16 comporta todas as chaves distintas usadas no scoring
# (score_limits, score_weights, score_thresholds, …) sem eviction prematura.
_settings_cache = TTLCache(maxsize=16, ttl=60)


# Comentário de controle: invalidação explícita para refletir mudanças de settings em tempo real.
def invalidate_score_settings_cache() -> None:
    _settings_cache.clear()

async def _get_setting(key: str, default_val: dict) -> dict:
    """Busca uma configuração no banco de dados com cache de 60s."""
    if key in _settings_cache:
        return _settings_cache[key]

    try:
        val = await db.fetchval("SELECT value FROM system_settings WHERE key = $1", key)
        if val:
            parsed = json.loads(val) if isinstance(val, str) else val
            _settings_cache[key] = parsed
            return parsed
    except Exception:
        pass

    _settings_cache[key] = default_val
    return default_val


async def _get_score_thresholds() -> dict:
    return await _get_setting("score_thresholds", {"forte": 75, "moderado": 50, "fraco": 30})


async def _get_consistency_score(symbol: str, exchange: str, current_rate: float) -> tuple:
    """
    Verifica quantos dos últimos pagamentos foram na mesma direção da taxa atual.
    Retorna (score 0-15, reason_str ou None).
    Usa funding_rate_snapshots do banco.
    """
    if current_rate == 0:
        return 5, None  # taxa zero → neutro

    try:
        rows = await db.fetch(
            """
            SELECT funding_rate FROM funding_rate_snapshots
            WHERE symbol = $1 AND exchange = $2
              AND captured_at >= NOW() - INTERVAL '3 days'
            ORDER BY captured_at DESC
            LIMIT 15
            """,
            symbol, exchange
        )
        if not rows or len(rows) < 3:
            return 5, None  # dados insuficientes → neutro

        same_dir = sum(1 for r in rows if float(r["funding_rate"]) * current_rate > 0)
        ratio = same_dir / len(rows)

        if ratio >= 0.9:
            return 15, f"Taxa consistente ({same_dir}/{len(rows)} ciclos mesma direção)"
        elif ratio >= 0.7:
            return 10, f"Taxa moderadamente consistente ({same_dir}/{len(rows)} ciclos)"
        elif ratio >= 0.5:
            return 5, None
        else:
            return 0, f"Taxa inconsistente ({same_dir}/{len(rows)} ciclos na direção correta)"
    except Exception:
        return 5, None  # fallback neutro em caso de erro


async def _get_momentum_score(symbol: str, exchange: str, current_rate: float) -> tuple[float, str | None]:
    """
    Avalia a tendência (momentum) da taxa de funding nas últimas 4 horas.
    Compara a magnitude média da primeira metade dos snapshots com a segunda metade
    para determinar se a taxa está acelerando, estável ou decaindo.

    Taxa crescendo → bom para sniping (pagamento garantido no nível anunciado).
    Taxa caindo    → risco de ser pago menos ou de a taxa zerar antes do ciclo.
    Taxa caiu abruptamente agora → penalidade máxima.

    Retorna (score de −15.0 a +15.0, reason ou None).
    Requer mínimo de 4 snapshots nas últimas 4h (capturados a cada ~15 min).
    """
    if current_rate == 0:
        return 0.0, None

    try:
        rows = await db.fetch(
            """
            SELECT funding_rate FROM funding_rate_snapshots
            WHERE symbol = $1 AND exchange = $2
              AND captured_at >= NOW() - INTERVAL '4 hours'
            ORDER BY captured_at ASC
            """,
            symbol, exchange,
        )
        if not rows or len(rows) < 4:
            return 0.0, None  # dados insuficientes → neutro, sem penalidade

        # Magnitudes absolutas em ordem cronológica (mais antigo → mais recente)
        rates = [abs(float(r["funding_rate"])) for r in rows]
        current_abs = abs(current_rate)

        mid = len(rates) // 2
        avg_older  = sum(rates[:mid]) / mid
        avg_recent = sum(rates[mid:]) / len(rates[mid:])

        if avg_older == 0:
            return 0.0, None

        # Caso especial: a taxa atual caiu abruptamente em relação à média recente
        # (ex.: estava em 0.05% e agora aparece como 0.01%) → penalidade máxima
        if avg_recent > 0.0001 and current_abs < avg_recent * 0.50:
            return -15.0, (
                f"Taxa caiu abruptamente — atual {current_abs*100:.4f}% "
                f"vs média recente {avg_recent*100:.4f}%"
            )

        change_pct = (avg_recent - avg_older) / avg_older

        if change_pct >= 0.25:
            return 15.0, f"Taxa em forte aceleração (+{change_pct*100:.0f}% nas últimas horas)"
        elif change_pct >= 0.08:
            return 8.0, f"Taxa em crescimento (+{change_pct*100:.0f}%)"
        elif change_pct >= -0.08:
            return 3.0, None  # estável → pequeno bônus de confiança
        elif change_pct >= -0.25:
            return -8.0, f"Taxa em declínio ({change_pct*100:.0f}%) — funding pode ser inferior ao esperado"
        else:
            return -15.0, f"Taxa em forte queda ({change_pct*100:.0f}%) — risco elevado de pagamento abaixo do anunciado"

    except Exception:
        return 0.0, None  # fallback neutro em caso de erro


async def calculate_score(item: dict) -> dict:
    """
    Calcula o score de um ativo baseado em regras institucionais v3:
    - APY Líquido ajustado por fee (0-40 pontos)
    - Volume/Liquidez por exchange (0-20 pontos)
    - Bônus por intervalo menor (0-10 pontos)
    - Consistência histórica da direção (0-15 pontos)
    - Momentum da taxa nas últimas 4h (−15 a +15 pontos)

    Retorna dict com score, confiança e sinal.
    """
    funding_rate = abs(float(item.get("fundingRate", 0) or 0))
    funding_pct = abs(float(item.get("fundingRatePercent", 0) or 0))
    volatility = abs(float(item.get("price24hPcnt", 0) or 0))
    volume = float(item.get("volume24h", 0) or item.get("turnover24h", 0) or 0)
    interval = int(item.get("fundingInterval", 8) or 8)
    original_rate = float(item.get("fundingRate", 0) or 0)

    reasons = []

    limits = await _get_setting("score_limits", {"max_volatility": 35, "min_volume": 2000000, "max_funding_rate_pct": 1.0})
    weights = await _get_setting("score_weights", {"apy": 40, "vol": 20, "int": 10, "consistency": 15, "momentum": 15})

    max_volatility = limits.get("max_volatility", 35)
    min_volume = limits.get("min_volume", 2000000)
    max_funding_rate_pct = limits.get("max_funding_rate_pct")  # None = sem limite

    # ===== 0. CORTES EXTREMOS (VETOS) =====
    # Volatilidade muito alta (Risco iminente de Squeeze)
    if volatility > max_volatility:
        return _build_veto(f"Volatilidade extrema (>{max_volatility}%)", original_rate)

    # Volume praticamente nulo (Risco de Slippage severo)
    if volume > 0 and volume < min_volume:
        vol_m = min_volume / 1000000
        return _build_veto(f"Liquidez baixíssima (<${vol_m:g}M)", original_rate)

    # Taxa de funding extrema — histórico mostra win rate de 41% acima de 1%/ciclo
    if max_funding_rate_pct is not None and funding_pct > float(max_funding_rate_pct):
        return _build_veto(
            f"Taxa extrema (>{max_funding_rate_pct}%/ciclo) — risco de reversão violenta",
            original_rate,
        )

    # ===== 1. APY LÍQUIDO AJUSTADO POR FEE (0-40 pontos) =====
    # Fee round-trip maker+maker Binance: 0.04% do notional
    FEE_ROUND_TRIP_PCT = 0.04  # percentual

    payments_per_year = (24.0 / interval) * 365.0
    gross_apy = funding_pct * payments_per_year  # APY bruto em %

    # Net funding por pagamento após amortizar o custo do round-trip
    net_funding_per_payment = funding_pct - (FEE_ROUND_TRIP_PCT / payments_per_year)

    if net_funding_per_payment <= 0:
        # Taxa não cobre o fee — score zero, sem veto mas sem pontos
        apy_score = 0
        reasons.append(f"Taxa não cobre fee round-trip ({FEE_ROUND_TRIP_PCT}%)")
    elif gross_apy >= 200:    # > 200% APY bruto — elite
        apy_score = 40
    elif gross_apy >= 100:    # > 100% APY bruto — excelente
        apy_score = 25 + (gross_apy - 100) / 100 * 15
    elif gross_apy >= 40:     # > 40% APY bruto — bom
        apy_score = 10 + (gross_apy - 40) / 60 * 15
    elif gross_apy >= 15:     # > 15% APY bruto — mínimo aceitável
        apy_score = (gross_apy - 15) / 25 * 10
    else:
        apy_score = 0

    if apy_score >= 25:
        reasons.append(f"APY bruto excelente ({gross_apy:.1f}%/ano)")
    elif apy_score >= 10:
        reasons.append(f"APY bruto bom ({gross_apy:.1f}%/ano)")

    # ===== 3. VOLUME/LIQUIDEZ (0-20 pontos) — thresholds por exchange =====
    exchange_name_vol = item.get("exchange", "binance").lower()

    if exchange_name_vol == "bybit":
        V_VETO = min_volume          # usa o mínimo configurado (padrão 2M)
        V_LOW  = 8_000_000
        V_MID  = 30_000_000
        V_HIGH = 100_000_000
    else:  # binance e demais
        V_VETO = max(min_volume, 5_000_000)  # binance: mínimo 5M
        V_LOW  = 20_000_000
        V_MID  = 80_000_000
        V_HIGH = 300_000_000

    if volume >= V_HIGH:
        vol_score = 20
    elif volume >= V_MID:
        vol_score = 13 + (volume - V_MID) / (V_HIGH - V_MID) * 7
    elif volume >= V_LOW:
        vol_score = 6 + (volume - V_LOW) / (V_MID - V_LOW) * 7
    elif volume >= V_VETO:
        vol_score = (volume - V_VETO) / (V_LOW - V_VETO) * 6
    else:
        vol_score = 0

    if vol_score >= 13:
        reasons.append("Excelente liquidez")
    elif vol_score < 6 and volume > 0:
        reasons.append("Liquidez alerta (Slippage)")

    # ===== 4. BÔNUS INTERVALO (0-10) =====
    if interval <= 1:
        int_score = 10
    elif interval <= 2:
        int_score = 8
    elif interval <= 4:
        int_score = 5
    else:
        int_score = 0

    if int_score >= 5:
        reasons.append(f"Intervalo {interval}h")

    # ===== 5. CONSISTÊNCIA HISTÓRICA (0-15) =====
    symbol = item.get("symbol", "")
    exchange_name = item.get("exchange", "binance")
    consistency_score, consistency_reason = await _get_consistency_score(symbol, exchange_name, original_rate)
    if consistency_reason:
        reasons.append(consistency_reason)

    # ===== 6. MOMENTUM DA TAXA (−15 a +15) =====
    momentum_raw, momentum_reason = await _get_momentum_score(symbol, exchange_name, original_rate)
    if momentum_reason:
        reasons.append(momentum_reason)

    # ===== AJUSTE DE PESOS DINÂMICOS =====
    apy_score         = apy_score         * (weights.get("apy",         40) / 40)
    vol_score         = vol_score         * (weights.get("vol",         20) / 20)
    int_score         = int_score         * (weights.get("int",         10) / 10)
    consistency_score = consistency_score * (weights.get("consistency", 15) / 15)
    momentum_score    = momentum_raw      * (weights.get("momentum",    15) / 15)

    # ===== SCORE TOTAL =====
    total = round(apy_score + vol_score + int_score + consistency_score + momentum_score)
    total = min(100, max(0, total))

    # ===== CONFIANÇA / SINAL =====
    if original_rate > 0:
        direction = "SHORT"
    elif original_rate < 0:
        direction = "LONG"
    else:
        direction = "NEUTRO"

    thresholds = await _get_score_thresholds()
    t_forte = thresholds.get("forte", 75)
    t_moderado = thresholds.get("moderado", 50)
    t_fraco = thresholds.get("fraco", 30)

    if total >= t_forte:
        confidence = "FORTE"
        signal = f"✅ {direction}"
        should_open = True
    elif total >= t_moderado:
        confidence = "MODERADO"
        signal = f"⚠️ {direction}"
        should_open = True
    elif total >= t_fraco:
        confidence = "FRACO"
        signal = f"⚡ {direction}"
        should_open = False
    else:
        confidence = "EVITAR"
        signal = "❌ EVITAR"
        should_open = False

    return {
        "score": total,
        "confidence": confidence,
        "signal": signal,
        "shouldOpen": should_open,
        "direction": direction,
        "breakdown": {
            "apy": round(apy_score, 1),
            "volume": round(vol_score, 1),
            "interval": round(int_score, 1),
            "consistency": round(consistency_score, 1),
            "momentum": round(momentum_score, 1),
            "gross_apy": round(gross_apy, 1),   # valor informativo, não pontuação
        },
        "reasons": reasons,
    }


def _build_veto(reason: str, original_rate: float) -> dict:
    """Gera um score zero forçado devido a um veto de segurança."""
    direction = "SHORT" if original_rate > 0 else "LONG" if original_rate < 0 else "NEUTRO"
    return {
        "score": 0,
        "confidence": "VETO R/R",
        "signal": "⛔ VETADO",
        "shouldOpen": False,
        "direction": direction,
        "breakdown": {"apy": 0, "volume": 0, "interval": 0, "consistency": 0, "gross_apy": 0},
        "reasons": [reason],
    }


async def enrich_with_score(items: list) -> list:
    """Adiciona score a uma lista de itens de funding rate."""
    for item in items:
        item["scoreData"] = await calculate_score(item)
    return items
