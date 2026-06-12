"""
Sistema de scoring para estratégia counter-trend baseada em funding rate.
Identifica ativos com posicionamento extremo e persistente como candidatos a reversão.

Modelo:
- Extremidade da taxa   (0-40 pts): quanto mais extrema, mais sinal de overshooting
- Persistência          (0-30 pts): ciclos consecutivos mesma direção = posicionamento crowded
- Volume/Liquidez       (0-20 pts): precisa de liquidez para sair da posição
- Volatilidade (bônus)  (0-10 pts): mais volatilidade = mais chance de reversão

Diferenças em relação ao harvesting:
- Volatilidade alta é BÔNUS (não punição/veto)
- Não há cálculo de APY (objetivo é reversão, não coleta de funding)
- Persistência alta = sinal POSITIVO (mercado crowded)
"""
import json
from cachetools import TTLCache
import database as db

# Cache de configurações — mesmo TTL do scoring principal.
# maxsize=16 comporta todas as chaves usadas (score_limits_counter,
# score_weights_counter, score_thresholds_counter, …) sem eviction prematura.
_settings_cache = TTLCache(maxsize=16, ttl=60)
_MISSING = object()


# Comentário de controle: invalidação explícita para refletir mudanças de settings em tempo real.
def invalidate_counter_score_settings_cache() -> None:
    _settings_cache.clear()


async def _get_setting_raw(key: str):
    """Busca valor bruto da configuração; retorna None quando a chave não existe."""
    if key in _settings_cache:
        cached = _settings_cache[key]
        return None if cached is _MISSING else cached

    try:
        val = await db.fetchval("SELECT value FROM system_settings WHERE key = $1", key)
        if val is not None:
            parsed = json.loads(val) if isinstance(val, str) else val
            _settings_cache[key] = parsed
            return parsed
    except Exception:
        pass

    _settings_cache[key] = _MISSING
    return None


async def _get_setting(key: str, default_val: dict) -> dict:
    """Busca uma configuração no banco de dados com cache de 60s."""
    val = await _get_setting_raw(key)
    return val if val is not None else default_val


async def _get_setting_with_fallback(primary_key: str, fallback_key: str | None, default_val: dict) -> dict:
    """
    Busca configuração por chave primária e, se ausente, usa fallback.
    Mantém compatibilidade com instalações que só têm as chaves antigas.
    """
    primary = await _get_setting_raw(primary_key)
    if primary is not None:
        return primary

    if fallback_key:
        fallback = await _get_setting_raw(fallback_key)
        if fallback is not None:
            return fallback

    return default_val


async def _get_persistence_score(symbol: str, exchange: str, current_rate: float) -> tuple[float, str | None]:
    """
    Para counter-trend, ALTA persistência = MELHOR sinal.
    Retorna (score 0-30, reason ou None).
    """
    if current_rate == 0:
        return 0, "Taxa neutra, sem sinal de contra-tendência"

    try:
        rows = await db.fetch(
            """
            SELECT funding_rate FROM funding_rate_snapshots
            WHERE symbol = $1 AND exchange = $2
              AND captured_at >= NOW() - INTERVAL '5 days'
            ORDER BY captured_at DESC
            LIMIT 20
            """,
            symbol, exchange
        )
        if not rows or len(rows) < 3:
            return 10, None  # dados insuficientes → neutro-baixo

        same_dir = sum(1 for r in rows if float(r["funding_rate"]) * current_rate > 0)
        ratio = same_dir / len(rows)

        if ratio >= 0.95:   # quase todos os ciclos na mesma direção
            return 30, f"Posicionamento extremamente persistente ({same_dir}/{len(rows)} ciclos)"
        elif ratio >= 0.85:
            return 22, f"Alta persistência de posicionamento ({same_dir}/{len(rows)} ciclos)"
        elif ratio >= 0.70:
            return 14, f"Persistência moderada ({same_dir}/{len(rows)} ciclos)"
        elif ratio >= 0.50:
            return 7, None
        else:
            return 0, "Taxa oscila muito — sinal fraco para contra-tendência"
    except Exception:
        return 10, None


async def calculate_score_counter_trend(item: dict) -> dict:
    """
    Calcula o score counter-trend de um ativo.
    """
    funding_pct = abs(float(item.get("fundingRatePercent", 0) or 0))
    volatility = abs(float(item.get("price24hPcnt", 0) or 0))
    volume = float(item.get("volume24h", 0) or item.get("turnover24h", 0) or 0)
    original_rate = float(item.get("fundingRate", 0) or 0)
    symbol = item.get("symbol", "")
    exchange_name = item.get("exchange", "binance").lower()

    reasons = []

    # Configurações próprias do modo counter-trend (com fallback para legado).
    limits = await _get_setting_with_fallback(
        "score_limits_counter",
        "score_limits",
        {"min_volume": 2000000, "min_funding_rate_pct": 0.05},
    )
    weights = await _get_setting_with_fallback(
        "score_weights_counter",
        None,
        {"extremity": 40, "persistence": 30, "volume": 20, "volatility_bonus": 10},
    )
    min_volume = limits.get("min_volume", 2000000)
    min_funding_rate_pct = limits.get("min_funding_rate_pct", 0.01)

    # Veto: volume insuficiente (não dá para sair da posição)
    if volume > 0 and volume < min_volume:
        vol_m = min_volume / 1_000_000
        return _build_veto_ct(f"Liquidez insuficiente para reversão (<${vol_m:g}M)", original_rate)

    # Veto: taxa muito baixa para ser sinal de distorção extrema
    if funding_pct < min_funding_rate_pct:
        return _build_veto_ct(
            f"Taxa muito baixa para sinal de contra-tendência (<{min_funding_rate_pct:.4f}%)",
            original_rate,
        )

    # ===== 1. EXTREMIDADE DA TAXA (0-40 pts) =====
    if funding_pct >= 0.15:
        extreme_score = 40
        reasons.append(f"Taxa extremamente alta ({funding_pct:.4f}%) — forte sinal de distorção extrema")
    elif funding_pct >= 0.10:
        extreme_score = 30 + (funding_pct - 0.10) / 0.05 * 10
        reasons.append(f"Taxa muito alta ({funding_pct:.4f}%)")
    elif funding_pct >= 0.05:
        extreme_score = 15 + (funding_pct - 0.05) / 0.05 * 15
    elif funding_pct >= 0.02:
        extreme_score = 5 + (funding_pct - 0.02) / 0.03 * 10
    elif funding_pct >= 0.01:
        extreme_score = (funding_pct - 0.01) / 0.01 * 5
    else:
        extreme_score = 0

    # ===== 2. PERSISTÊNCIA (0-30 pts) =====
    persistence_score, persistence_reason = await _get_persistence_score(symbol, exchange_name, original_rate)
    if persistence_reason:
        reasons.append(persistence_reason)

    # ===== 3. VOLUME/LIQUIDEZ (0-20 pts) — thresholds por exchange =====
    if exchange_name == "bybit":
        V_VETO, V_LOW, V_MID, V_HIGH = min_volume, 8_000_000, 30_000_000, 100_000_000
    else:
        V_VETO, V_LOW, V_MID, V_HIGH = max(min_volume, 5_000_000), 20_000_000, 80_000_000, 300_000_000

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
        reasons.append("Boa liquidez para reversão")

    # ===== 4. VOLATILIDADE COMO BÔNUS (0-10 pts) =====
    # Ao contrário do harvesting, aqui volatilidade alta = mais chance de reversão
    if volatility >= 20:
        volat_bonus = 10
        reasons.append(f"Alta volatilidade favorece reversão ({volatility:.1f}%)")
    elif volatility >= 10:
        volat_bonus = 7
    elif volatility >= 5:
        volat_bonus = 4
    elif volatility >= 2:
        volat_bonus = 2
    else:
        volat_bonus = 0  # mercado muito quieto, sem reversão esperada

    # Ajuste dinâmico de pesos do counter-trend.
    extreme_score = extreme_score * (weights.get("extremity", 40) / 40)
    persistence_score = persistence_score * (weights.get("persistence", 30) / 30)
    vol_score = vol_score * (weights.get("volume", 20) / 20)
    volat_bonus = volat_bonus * (weights.get("volatility_bonus", 10) / 10)

    # ===== SCORE TOTAL =====
    total = round(extreme_score + persistence_score + vol_score + volat_bonus)
    total = min(100, max(0, total))

    # ===== DIREÇÃO =====
    # rate > 0 → longs pagando shorts → reversão esperada para baixo → SHORT
    if original_rate > 0:
        direction = "SHORT"
    elif original_rate < 0:
        direction = "LONG"
    else:
        direction = "NEUTRO"

    # ===== CONFIANÇA =====
    thresholds = await _get_setting_with_fallback(
        "score_thresholds_counter",
        "score_thresholds",
        {"forte": 75, "moderado": 50, "fraco": 30},
    )
    t_forte = thresholds.get("forte", 75)
    t_moderado = thresholds.get("moderado", 50)
    t_fraco = thresholds.get("fraco", 30)

    if total >= t_forte:
        confidence = "FORTE"
        signal = f"↩ {direction}"
        should_open = True
    elif total >= t_moderado:
        confidence = "MODERADO"
        signal = f"↪ {direction}"
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
        "mode": "counter_trend",
        "breakdown": {
            "extremity": round(extreme_score, 1),
            "persistence": round(persistence_score, 1),
            "volume": round(vol_score, 1),
            "volatility_bonus": round(volat_bonus, 1),
        },
        "reasons": reasons,
    }


def _build_veto_ct(reason: str, original_rate: float) -> dict:
    """Gera um score zero forçado devido a um veto de segurança (counter-trend)."""
    direction = "SHORT" if original_rate > 0 else "LONG" if original_rate < 0 else "NEUTRO"
    return {
        "score": 0,
        "confidence": "VETO",
        "signal": "⛔ VETADO",
        "shouldOpen": False,
        "direction": direction,
        "mode": "counter_trend",
        "breakdown": {"extremity": 0, "persistence": 0, "volume": 0, "volatility_bonus": 0},
        "reasons": [reason],
    }


async def enrich_with_score_counter_trend(items: list[dict]) -> list[dict]:
    """Adiciona scoreData counter-trend a uma lista de itens de funding rate."""
    for item in items:
        item["scoreData"] = await calculate_score_counter_trend(item)
    return items
