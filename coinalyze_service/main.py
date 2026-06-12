"""
Microserviço Coinalyze para enriquecimento de métricas de funding/perp.
Expõe endpoints prontos para ranking sistemático e apoio à operação manual.
"""

import asyncio
import math
import os
import time
from pathlib import Path
from typing import Any

import httpx
from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


# Comentário de controle: carrega variáveis locais e também reaproveita backend/.env quando existir.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / "backend" / ".env")

COINALYZE_BASE_URL = os.getenv("COINALYZE_BASE_URL", "https://api.coinalyze.net/v1")
COINALYZE_API_KEY = os.getenv("COINALYZE_API_KEY", "").strip()
COINALYZE_TIMEOUT = float(os.getenv("COINALYZE_TIMEOUT", "20"))
COINALYZE_DEFAULT_SYMBOLS = int(os.getenv("COINALYZE_DEFAULT_SYMBOLS", "6"))
COINALYZE_MAX_SYMBOLS = int(os.getenv("COINALYZE_MAX_SYMBOLS", "8"))

# Comentário de controle: mapeia aliases legíveis para os códigos internos de exchange da Coinalyze.
EXCHANGE_ALIASES = {
    "binance": "A",
    "bybit": "6",
    "A": "A",
    "6": "6",
}

INTERVAL_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
    "2hour": 7200,
    "4hour": 14400,
    "6hour": 21600,
    "12hour": 43200,
    "daily": 86400,
}

# Comentário de controle: cacheia lista de mercados para evitar chamadas repetidas de metadata.
_markets_cache = TTLCache(maxsize=16, ttl=3600)
# Comentário de controle: cache de payload de endpoints históricos com TTL curto para reduzir consumo de rate-limit.
_endpoint_cache = TTLCache(maxsize=512, ttl=50)
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        headers = {
            # Comentário de controle: mantém múltiplos nomes de header por compatibilidade com variações de gateway.
            "api_key": COINALYZE_API_KEY,
            "X-API-KEY": COINALYZE_API_KEY,
        }
        _http_client = httpx.AsyncClient(
            base_url=COINALYZE_BASE_URL,
            timeout=COINALYZE_TIMEOUT,
            headers=headers,
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        )
    return _http_client


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        if math.isfinite(parsed):
            return parsed
    except Exception:
        pass
    return default


def _norm_symbol(raw: str) -> str:
    text = "".join(ch for ch in str(raw or "").upper() if ch.isalnum())
    return text


def _chunked(values: list[str], size: int = 20) -> list[list[str]]:
    return [values[i: i + size] for i in range(0, len(values), size)]


def _normalize_exchange_codes(raw_exchange: str) -> set[str]:
    values = [x.strip() for x in str(raw_exchange or "").split(",") if x.strip()]
    if not values:
        return set()

    out: set[str] = set()
    for value in values:
        upper_value = value.upper()
        lower_value = value.lower()
        if value in EXCHANGE_ALIASES:
            out.add(EXCHANGE_ALIASES[value])
        elif upper_value in EXCHANGE_ALIASES:
            out.add(EXCHANGE_ALIASES[upper_value])
        elif lower_value in EXCHANGE_ALIASES:
            out.add(EXCHANGE_ALIASES[lower_value])
        else:
            out.add(value)
    return out


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100.0


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _avg(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(var)


def _window_points(interval: str, window_seconds: int) -> int:
    step = INTERVAL_SECONDS.get(interval, 3600)
    return max(1, int(window_seconds // step))


def _pick_reference(series: list[float], points_back: int) -> float | None:
    if not series:
        return None
    idx = len(series) - 1 - points_back
    if idx < 0:
        return series[0]
    return series[idx]


def _to_direction_by_funding(funding_pct: float) -> str:
    return "SHORT" if funding_pct > 0 else "LONG"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# Comentário de controle: score composto para priorizar sinais com confluência multi-fator.
def _build_systematic_score(metrics: dict[str, float]) -> tuple[float, list[str]]:
    funding_pct = metrics.get("fundingRatePct", 0.0)
    predicted_pct = metrics.get("predictedFundingRatePct", 0.0)
    dislocation = metrics.get("fundingDislocationPct", 0.0)
    oi_delta_1h = metrics.get("oiDelta1hPct", 0.0)
    oi_zscore = metrics.get("oiZScore", 0.0)
    liq_imb = metrics.get("liquidationImbalance1h", 0.0)
    buy_ratio = metrics.get("buyVolumeRatio", 0.5)
    long_pct = metrics.get("longPct", 50.0)
    short_pct = metrics.get("shortPct", 50.0)

    direction = _to_direction_by_funding(funding_pct)
    reasons: list[str] = []

    # Magnitude de funding: quanto maior a taxa, maior potencial de coleta.
    funding_score = _clamp((abs(funding_pct) / 0.05) * 25.0, 0.0, 25.0)
    if funding_score >= 15:
        reasons.append(f"Funding forte ({funding_pct:+.4f}%)")

    # Dislocation: previsão alinhada/acelerando melhora confiança da taxa até o settlement.
    if funding_pct == 0 or predicted_pct == 0:
        dislocation_score = 4.0
    elif funding_pct * predicted_pct > 0:
        accel = (abs(predicted_pct) - abs(funding_pct)) / max(abs(funding_pct), 1e-9)
        if accel >= 0.20:
            dislocation_score = 20.0
            reasons.append("Predicted funding acelerando")
        elif accel >= 0.0:
            dislocation_score = 14.0
            reasons.append("Predicted funding confirmando")
        elif dislocation >= -0.01:
            dislocation_score = 9.0
        else:
            dislocation_score = 5.0
    else:
        dislocation_score = 1.0
        reasons.append("Predicted funding contra direção")

    # OI impulse: aumento de OI + z-score elevado sinaliza crowding (combustível para squeeze).
    oi_score = _clamp((abs(oi_delta_1h) / 4.0) * 12.0, 0.0, 12.0) + _clamp((abs(oi_zscore) / 2.0) * 8.0, 0.0, 8.0)
    if oi_score >= 12:
        reasons.append(f"OI em impulso ({oi_delta_1h:+.2f}% 1h)")

    # Desequilíbrio de liquidações aponta estresse do lado pressionado.
    liq_score = _clamp(abs(liq_imb) * 15.0, 0.0, 15.0)
    if liq_score >= 9:
        if liq_imb > 0:
            reasons.append("Liquidação de shorts em alta")
        else:
            reasons.append("Liquidação de longs em alta")

    # Fluxo agressor: para SHORT preferimos venda agressiva; para LONG compra agressiva.
    if direction == "SHORT":
        flow_edge = (0.50 - buy_ratio) / 0.15
    else:
        flow_edge = (buy_ratio - 0.50) / 0.15
    flow_score = _clamp(flow_edge * 10.0, 0.0, 10.0)

    # Crowding no lado oposto da entrada aumenta chance de continuidade do movimento esperado.
    if direction == "SHORT":
        crowding_edge = (long_pct - 50.0) / 15.0
    else:
        crowding_edge = (short_pct - 50.0) / 15.0
    crowding_score = _clamp(crowding_edge * 10.0, 0.0, 10.0)
    if crowding_score >= 6:
        if direction == "SHORT":
            reasons.append("Mercado excessivamente long")
        else:
            reasons.append("Mercado excessivamente short")

    total = funding_score + dislocation_score + oi_score + liq_score + flow_score + crowding_score
    total = round(_clamp(total, 0.0, 100.0), 2)
    return total, reasons


def _build_action_plan(metrics: dict[str, float], score: float, reasons: list[str]) -> dict[str, Any]:
    funding_pct = metrics.get("fundingRatePct", 0.0)
    predicted_pct = metrics.get("predictedFundingRatePct", 0.0)
    oi_delta = metrics.get("oiDelta1hPct", 0.0)
    liq_imb = metrics.get("liquidationImbalance1h", 0.0)
    buy_ratio = metrics.get("buyVolumeRatio", 0.5)
    long_pct = metrics.get("longPct", 50.0)
    short_pct = metrics.get("shortPct", 50.0)

    direction = _to_direction_by_funding(funding_pct)

    if score >= 72:
        action = "entry"
        confidence = "alta"
    elif score >= 55:
        action = "monitor"
        confidence = "media"
    else:
        action = "avoid"
        confidence = "baixa"

    checklist = [
        f"Funding atual {funding_pct:+.4f}% vs previsto {predicted_pct:+.4f}%",
        f"OI 1h {oi_delta:+.2f}% e desequilíbrio de liq {liq_imb:+.2f}",
        f"Fluxo agressor de compra {buy_ratio * 100:.1f}%",
        f"Crowding: longs {long_pct:.1f}% / shorts {short_pct:.1f}%",
    ]

    if direction == "SHORT":
        invalidation = "Invalidar se compra agressora > 56% e longs < 52%."
    else:
        invalidation = "Invalidar se compra agressora < 44% e shorts < 52%."

    if score >= 72:
        execution = "Entrada fracionada em 2 lotes, com confirmação no próximo candle do intervalo selecionado."
    elif score >= 55:
        execution = "Aguardar confirmação adicional de fluxo e manutenção do OI antes da entrada."
    else:
        execution = "Não entrar; priorizar outros ativos com maior confluência."

    return {
        "recommendedDirection": direction,
        "systematicAction": action,
        "confidence": confidence,
        "reasons": reasons,
        "manualChecklist": checklist,
        "manualInvalidation": invalidation,
        "executionHint": execution,
    }


class CoinalyzeClient:
    async def _request(self, path: str, params: dict[str, Any] | None = None, ttl: int = 45) -> Any:
        # Comentário de controle: falha explícita para evitar chamadas inúteis quando chave não foi configurada.
        if not COINALYZE_API_KEY:
            raise HTTPException(status_code=503, detail="COINALYZE_API_KEY não configurada")

        safe_params = dict(params or {})
        cache_key = (path, tuple(sorted(safe_params.items())))
        if cache_key in _endpoint_cache:
            return _endpoint_cache[cache_key]

        # Comentário de controle: também envia api_key em query para suportar ambientes que ignoram header custom.
        safe_params.setdefault("api_key", COINALYZE_API_KEY)

        client = _get_client()
        response = await client.get(path, params=safe_params)

        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="Coinalyze rate limit atingido")
        if response.status_code in (400, 401, 403):
            detail = response.text[:300]
            raise HTTPException(status_code=response.status_code, detail=f"Falha Coinalyze: {detail}")

        response.raise_for_status()
        payload = response.json()

        if ttl > 0:
            _endpoint_cache[cache_key] = payload
        return payload

    async def get_future_markets(self) -> list[dict[str, Any]]:
        if "future_markets" in _markets_cache:
            return _markets_cache["future_markets"]
        markets = await self._request("/future-markets", ttl=1800)
        _markets_cache["future_markets"] = markets
        return markets

    async def get_history(
        self,
        endpoint: str,
        symbols: list[str],
        interval: str,
        from_ts: int,
        to_ts: int,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not symbols:
            return {}

        output: dict[str, list[dict[str, Any]]] = {}

        for chunk in _chunked(symbols, 20):
            params = {
                "symbols": ",".join(chunk),
                "interval": interval,
                "from": from_ts,
                "to": to_ts,
            }
            if extra_params:
                params.update(extra_params)

            rows = await self._request(endpoint, params=params, ttl=40)
            for item in rows or []:
                sym = str(item.get("symbol") or "").upper()
                history = item.get("history") or []
                output[sym] = history

        return output


_client = CoinalyzeClient()


def _filter_markets(
    markets: list[dict[str, Any]],
    exchange: str,
    quote_asset: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    filtered: list[dict[str, Any]] = []
    symbol_map: dict[str, str] = {}

    exchange_codes = _normalize_exchange_codes(exchange)
    quote = quote_asset.upper().strip()

    for m in markets:
        m_exchange = str(m.get("exchange") or "").strip()
        if exchange_codes and m_exchange not in exchange_codes:
            continue
        if not bool(m.get("is_perpetual")):
            continue
        if quote and str(m.get("quote_asset") or "").upper() != quote:
            continue

        filtered.append(m)

        symbol_on_exchange = str(m.get("symbol_on_exchange") or "").upper()
        canonical_symbol = str(m.get("symbol") or "").upper()
        normalized = _norm_symbol(symbol_on_exchange)
        if normalized:
            symbol_map[normalized] = canonical_symbol

        base = str(m.get("base_asset") or "").upper()
        quote_code = str(m.get("quote_asset") or "").upper()
        if base and quote_code:
            symbol_map[_norm_symbol(base + quote_code)] = canonical_symbol

    return filtered, symbol_map


def _extract_last_close(history: list[dict[str, Any]], field: str = "c") -> float | None:
    if not history:
        return None
    last = history[-1]
    return _safe_float(last.get(field), default=0.0)


def _compute_metrics_for_symbol(
    interval: str,
    funding_history: list[dict[str, Any]],
    predicted_history: list[dict[str, Any]],
    oi_history: list[dict[str, Any]],
    liq_history: list[dict[str, Any]],
    lsr_history: list[dict[str, Any]],
    ohlcv_history: list[dict[str, Any]],
) -> dict[str, float]:
    funding_rate_pct = _extract_last_close(funding_history) or 0.0
    predicted_rate_pct = _extract_last_close(predicted_history) or 0.0
    dislocation_pct = predicted_rate_pct - funding_rate_pct

    oi_series = [_safe_float(x.get("c"), 0.0) for x in oi_history if _safe_float(x.get("c"), 0.0) > 0]
    oi_now = oi_series[-1] if oi_series else 0.0
    oi_prev_1h = _pick_reference(oi_series, _window_points(interval, 3600))
    oi_delta_1h = _pct_change(oi_now, oi_prev_1h) if oi_prev_1h else None

    # Comentário de controle: z-score do OI recente para detectar aceleração fora do regime normal.
    oi_sample_points = max(_window_points(interval, 24 * 3600), 6)
    oi_tail = oi_series[-oi_sample_points:] if oi_series else []
    oi_mean = _avg(oi_tail)
    oi_std = _std(oi_tail)
    oi_zscore = ((oi_now - oi_mean) / oi_std) if oi_std > 0 else 0.0

    liq_points_1h = _window_points(interval, 3600)
    liq_tail = liq_history[-liq_points_1h:] if liq_history else []
    liq_longs = sum(_safe_float(c.get("l"), 0.0) for c in liq_tail)
    liq_shorts = sum(_safe_float(c.get("s"), 0.0) for c in liq_tail)
    liq_total = liq_longs + liq_shorts
    liq_imb = ((liq_shorts - liq_longs) / liq_total) if liq_total > 0 else 0.0

    lsr_last = lsr_history[-1] if lsr_history else {}
    long_pct = _safe_float(lsr_last.get("l"), 50.0)
    short_pct = _safe_float(lsr_last.get("s"), 50.0)
    lsr_ratio = _safe_float(lsr_last.get("r"), 1.0)

    ohlcv_last = ohlcv_history[-1] if ohlcv_history else {}
    total_vol = _safe_float(ohlcv_last.get("v"), 0.0)
    buy_vol = _safe_float(ohlcv_last.get("bv"), 0.0)
    total_trades = _safe_float(ohlcv_last.get("tx"), 0.0)
    buy_trades = _safe_float(ohlcv_last.get("btx"), 0.0)

    buy_ratio = (buy_vol / total_vol) if total_vol > 0 else 0.5
    buy_trades_ratio = (buy_trades / total_trades) if total_trades > 0 else 0.5

    close_series = [_safe_float(x.get("c"), 0.0) for x in ohlcv_history if _safe_float(x.get("c"), 0.0) > 0]
    close_now = close_series[-1] if close_series else 0.0
    close_prev_1h = _pick_reference(close_series, _window_points(interval, 3600))
    price_change_1h = _pct_change(close_now, close_prev_1h) if close_prev_1h else None

    return {
        "fundingRatePct": funding_rate_pct,
        "predictedFundingRatePct": predicted_rate_pct,
        "fundingDislocationPct": dislocation_pct,
        "openInterest": oi_now,
        "oiDelta1hPct": oi_delta_1h or 0.0,
        "oiZScore": oi_zscore,
        "liqLongs1h": liq_longs,
        "liqShorts1h": liq_shorts,
        "liquidationImbalance1h": liq_imb,
        "longPct": long_pct,
        "shortPct": short_pct,
        "longShortRatio": lsr_ratio,
        "buyVolumeRatio": buy_ratio,
        "buyTradesRatio": buy_trades_ratio,
        "priceChange1hPct": price_change_1h or 0.0,
    }


app = FastAPI(
    title="Coinalyze Metrics Service",
    version="1.0.0",
    description="Microserviço de agregação de métricas Coinalyze para trading sistemático e manual.",
)

# Comentário de controle: habilita consumo local do frontend/backend em ambientes de desenvolvimento.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "coinalyze-metrics",
        "apiKeyConfigured": bool(COINALYZE_API_KEY),
        "timestamp": int(time.time()),
    }


@app.get("/v1/markets")
async def markets(
    exchange: str = Query(default="binance"),
    quote_asset: str = Query(default="USDT"),
) -> dict[str, Any]:
    all_markets = await _client.get_future_markets()
    filtered, _ = _filter_markets(all_markets, exchange=exchange, quote_asset=quote_asset)

    return {
        "success": True,
        "exchange": exchange,
        "quoteAsset": quote_asset,
        "count": len(filtered),
        "data": filtered,
    }


@app.get("/v1/opportunities")
async def opportunities(
    exchange: str = Query(default="binance"),
    symbols: str = Query(default="", description="Símbolos de exchange separados por vírgula (ex: BTCUSDT,ETHUSDT)"),
    quote_asset: str = Query(default="USDT"),
    interval: str = Query(default="1hour"),
    lookback_hours: int = Query(default=24, ge=6, le=72),
    max_rows: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    if interval not in INTERVAL_SECONDS:
        raise HTTPException(status_code=400, detail=f"Intervalo inválido: {interval}")

    requested_symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if len(requested_symbols) > 20:
        raise HTTPException(status_code=400, detail="Máximo de 20 símbolos por chamada")

    all_markets = await _client.get_future_markets()
    filtered_markets, symbol_map = _filter_markets(all_markets, exchange=exchange, quote_asset=quote_asset)

    # Comentário de controle: limita símbolos padrão para manter consumo abaixo do rate-limit da Coinalyze.
    if not requested_symbols:
        requested_symbols = [
            str(m.get("symbol_on_exchange") or "").upper()
            for m in filtered_markets[:max(1, COINALYZE_DEFAULT_SYMBOLS)]
        ]

    missing_symbols: list[str] = []
    resolved_symbols: list[str] = []
    for sym in requested_symbols:
        normalized = _norm_symbol(sym)
        canonical = symbol_map.get(normalized)
        if canonical:
            resolved_symbols.append(canonical)
        elif "_PERP" in sym or "." in sym:
            resolved_symbols.append(sym.upper())
        else:
            missing_symbols.append(sym)

    # Comentário de controle: em modo full com 6 endpoints, mantemos teto operacional seguro por requisição.
    if len(resolved_symbols) > COINALYZE_MAX_SYMBOLS:
        resolved_symbols = resolved_symbols[:COINALYZE_MAX_SYMBOLS]

    if not resolved_symbols:
        return {
            "success": True,
            "exchange": exchange,
            "interval": interval,
            "lookbackHours": lookback_hours,
            "resolvedSymbols": [],
            "missingSymbols": missing_symbols,
            "count": 0,
            "data": [],
        }

    to_ts = int(time.time())
    from_ts = to_ts - (lookback_hours * 3600)

    # Comentário de controle: consultas paralelas por endpoint para reduzir latência total de agregação.
    funding_task = _client.get_history(
        endpoint="/funding-rate-history",
        symbols=resolved_symbols,
        interval=interval,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    predicted_task = _client.get_history(
        endpoint="/predicted-funding-rate-history",
        symbols=resolved_symbols,
        interval=interval,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    oi_task = _client.get_history(
        endpoint="/open-interest-history",
        symbols=resolved_symbols,
        interval=interval,
        from_ts=from_ts,
        to_ts=to_ts,
        extra_params={"convert_to_usd": "true"},
    )
    liq_task = _client.get_history(
        endpoint="/liquidation-history",
        symbols=resolved_symbols,
        interval=interval,
        from_ts=from_ts,
        to_ts=to_ts,
        extra_params={"convert_to_usd": "true"},
    )
    lsr_task = _client.get_history(
        endpoint="/long-short-ratio-history",
        symbols=resolved_symbols,
        interval=interval,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    ohlcv_task = _client.get_history(
        endpoint="/ohlcv-history",
        symbols=resolved_symbols,
        interval=interval,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    funding_map, predicted_map, oi_map, liq_map, lsr_map, ohlcv_map = await asyncio.gather(
        funding_task,
        predicted_task,
        oi_task,
        liq_task,
        lsr_task,
        ohlcv_task,
    )

    market_by_symbol = {str(m.get("symbol") or "").upper(): m for m in filtered_markets}
    rows: list[dict[str, Any]] = []

    for coinalyze_symbol in resolved_symbols:
        funding_history = funding_map.get(coinalyze_symbol, [])
        predicted_history = predicted_map.get(coinalyze_symbol, [])
        oi_history = oi_map.get(coinalyze_symbol, [])
        liq_history = liq_map.get(coinalyze_symbol, [])
        lsr_history = lsr_map.get(coinalyze_symbol, [])
        ohlcv_history = ohlcv_map.get(coinalyze_symbol, [])

        if not funding_history:
            continue

        metrics = _compute_metrics_for_symbol(
            interval=interval,
            funding_history=funding_history,
            predicted_history=predicted_history,
            oi_history=oi_history,
            liq_history=liq_history,
            lsr_history=lsr_history,
            ohlcv_history=ohlcv_history,
        )

        score, reasons = _build_systematic_score(metrics)
        plan = _build_action_plan(metrics, score, reasons)

        market = market_by_symbol.get(coinalyze_symbol, {})

        rows.append(
            {
                "coinalyzeSymbol": coinalyze_symbol,
                "exchange": str(market.get("exchange") or exchange),
                "symbol": str(market.get("symbol_on_exchange") or coinalyze_symbol),
                "baseAsset": str(market.get("base_asset") or ""),
                "quoteAsset": str(market.get("quote_asset") or quote_asset),
                "isPerpetual": bool(market.get("is_perpetual", True)),
                "score": score,
                "metrics": metrics,
                "plan": plan,
            }
        )

    rows.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)

    return {
        "success": True,
        "exchange": exchange,
        "interval": interval,
        "lookbackHours": lookback_hours,
        "requestedSymbols": requested_symbols,
        "resolvedSymbols": resolved_symbols,
        "missingSymbols": missing_symbols,
        "count": len(rows[:max_rows]),
        "data": rows[:max_rows],
        "limits": {
            "defaultSymbols": COINALYZE_DEFAULT_SYMBOLS,
            "maxSymbols": COINALYZE_MAX_SYMBOLS,
            "maxApiSymbolsPerCall": 20,
        },
    }


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)
