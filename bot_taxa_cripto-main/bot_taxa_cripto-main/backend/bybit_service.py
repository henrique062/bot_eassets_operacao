"""
Serviço de conexão com a API pública da Bybit v5.
Busca funding rates, dados de mercado e Long/Short Ratio.
"""

import httpx
import time
from cachetools import TTLCache
import symbol_syncer

BYBIT_BASE_URL = "https://api.bybit.com"

# Cache
_tickers_cache = TTLCache(maxsize=1, ttl=5)
_history_cache = TTLCache(maxsize=200, ttl=120)
_lsr_cache = TTLCache(maxsize=200, ttl=120)
_klines_cache: dict[str, dict] = {}

# Cliente HTTP persistente — reutiliza conexões TCP/SSL entre requests
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _http_client

_KLINES_TTL_BY_INTERVAL = {
    "1": 2.0,
    "3": 3.0,
    "5": 4.0,
    "15": 5.0,
    "30": 6.0,
    "60": 8.0,
    "120": 10.0,
    "240": 12.0,
    "360": 14.0,
    "720": 16.0,
    "D": 25.0,
}


def _get_klines_ttl(interval: str) -> float:
    return _KLINES_TTL_BY_INTERVAL.get(interval, 8.0)


async def _fetch(endpoint: str, params: dict) -> dict:
    """Faz uma requisição GET assíncrona à API da Bybit usando cliente persistente."""
    client = _get_client()
    response = await client.get(f"{BYBIT_BASE_URL}{endpoint}", params=params)
    response.raise_for_status()
    data = response.json()
    if data.get("retCode") != 0:
        raise Exception(f"Bybit API error: {data.get('retMsg', 'Unknown error')}")
    return data["result"]


async def get_all_funding_rates() -> list[dict]:
    """
    Busca todas as funding rates atuais dos contratos perpétuos lineares.
    """
    cache_key = "all_tickers"
    if cache_key in _tickers_cache:
        return _tickers_cache[cache_key]

    result = await _fetch("/v5/market/tickers", {"category": "linear"})
    tickers = result.get("list", [])

    funding_data = []
    for ticker in tickers:
        symbol = ticker.get("symbol", "")
        
        # Ignorar se o símbolo não faz parte da lista oficial da corretora
        if not symbol_syncer.is_valid_symbol("bybit", symbol):
            continue
            
        funding_rate = ticker.get("fundingRate", "")

        if not funding_rate:
            continue

        fr = float(funding_rate)

        # Bybit padrão 8h, mas inferir do nextFundingTime
        interval_hours = 8

        funding_data.append({
            "symbol": symbol,
            "fundingRate": fr,
            "fundingRatePercent": round(fr * 100, 6),
            "monthlyRate": round(fr * (24 / interval_hours) * 30 * 100, 2),
            "nextFundingTime": ticker.get("nextFundingTime", ""),
            "lastPrice": float(ticker.get("lastPrice", 0)),
            "volume24h": float(ticker.get("volume24h", 0)),
            "turnover24h": float(ticker.get("turnover24h", 0)),
            "price24hPcnt": round(float(ticker.get("price24hPcnt", 0)) * 100, 4),
            "highPrice24h": float(ticker.get("highPrice24h", 0)),
            "lowPrice24h": float(ticker.get("lowPrice24h", 0)),
            "fundingInterval": interval_hours,
        })

    funding_data.sort(key=lambda x: abs(x["fundingRate"]), reverse=True)

    _tickers_cache[cache_key] = funding_data
    return funding_data


async def get_funding_history(symbol: str, limit: int = 50) -> list[dict]:
    """
    Busca o histórico de funding rates de um símbolo específico.
    """
    cache_key = f"history_{symbol}_{limit}"
    if cache_key in _history_cache:
        return _history_cache[cache_key]

    result = await _fetch("/v5/market/funding/history", {
        "category": "linear",
        "symbol": symbol.upper(),
        "limit": min(limit, 200),
    })

    history = []
    for item in result.get("list", []):
        rate = float(item.get("fundingRate", 0))
        timestamp = int(item.get("fundingRateTimestamp", 0))
        history.append({
            "symbol": item.get("symbol", ""),
            "fundingRate": rate,
            "fundingRatePercent": round(rate * 100, 6),
            "fundingRateTimestamp": timestamp,
            "datetime": time.strftime(
                "%Y-%m-%d %H:%M", time.gmtime(timestamp / 1000)
            ) if timestamp else "",
        })

    _history_cache[cache_key] = history
    return history


async def get_long_short_ratio(symbol: str, period: str = "1h", limit: int = 30) -> list[dict]:
    """
    Busca o Long/Short Ratio de um símbolo na Bybit.
    period: 5min, 15min, 30min, 1h, 4h, 1d
    """
    # Mapear periods do estilo Binance para Bybit
    period_map = {
        "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "1h", "2h": "1h", "4h": "4h",
        "6h": "4h", "12h": "1d", "1d": "1d",
        # Aceitar formatos Bybit diretamente
        "5min": "5min", "15min": "15min", "30min": "30min",
    }
    bybit_period = period_map.get(period, "1h")

    cache_key = f"lsr_{symbol}_{bybit_period}_{limit}"
    if cache_key in _lsr_cache:
        return _lsr_cache[cache_key]

    try:
        result = await _fetch("/v5/market/account-ratio", {
            "category": "linear",
            "symbol": symbol.upper(),
            "period": bybit_period,
            "limit": min(limit, 500),
        })

        data = []
        for item in result.get("list", []):
            timestamp = int(item.get("timestamp", 0))
            buy = float(item.get("buyRatio", 0))
            sell = float(item.get("sellRatio", 0))
            ratio = round(buy / sell, 4) if sell > 0 else 0

            data.append({
                "symbol": symbol.upper(),
                "longShortRatio": ratio,
                "longAccount": round(buy * 100, 2),
                "shortAccount": round(sell * 100, 2),
                "timestamp": timestamp,
                "datetime": time.strftime(
                    "%Y-%m-%d %H:%M", time.gmtime(timestamp / 1000)
                ) if timestamp else "",
            })

        _lsr_cache[cache_key] = data
        return data

    except Exception:
        return []


async def get_stats() -> dict:
    """
    Calcula estatísticas gerais sobre as funding rates atuais.
    """
    rates = await get_all_funding_rates()

    if not rates:
        return {
            "totalPairs": 0,
            "positiveCount": 0,
            "negativeCount": 0,
            "neutralCount": 0,
            "avgRate": 0,
            "avgRatePercent": 0,
            "maxRate": None,
            "minRate": None,
            "top10Positive": [],
            "top10Negative": [],
            "intervals": {},
        }

    funding_values = [r["fundingRate"] for r in rates]
    positive = [r for r in rates if r["fundingRate"] > 0]
    negative = [r for r in rates if r["fundingRate"] < 0]
    neutral = [r for r in rates if r["fundingRate"] == 0]

    interval_counts = {}
    for r in rates:
        h = r.get("fundingInterval", 8)
        key = f"{h}h"
        interval_counts[key] = interval_counts.get(key, 0) + 1

    sorted_by_rate = sorted(rates, key=lambda x: x["fundingRate"], reverse=True)

    max_rate = sorted_by_rate[0] if sorted_by_rate else None
    min_rate = sorted_by_rate[-1] if sorted_by_rate else None

    return {
        "totalPairs": len(rates),
        "positiveCount": len(positive),
        "negativeCount": len(negative),
        "neutralCount": len(neutral),
        "avgRate": round(sum(funding_values) / len(funding_values), 8),
        "avgRatePercent": round(
            sum(funding_values) / len(funding_values) * 100, 6
        ),
        "maxRate": {
            "symbol": max_rate["symbol"],
            "fundingRate": max_rate["fundingRate"],
            "fundingRatePercent": max_rate["fundingRatePercent"],
        } if max_rate else None,
        "minRate": {
            "symbol": min_rate["symbol"],
            "fundingRate": min_rate["fundingRate"],
            "fundingRatePercent": min_rate["fundingRatePercent"],
        } if min_rate else None,
        "top10Positive": [
            {"symbol": r["symbol"], "fundingRate": r["fundingRate"],
             "fundingRatePercent": r["fundingRatePercent"]}
            for r in sorted_by_rate[:10]
        ],
        "top10Negative": [
            {"symbol": r["symbol"], "fundingRate": r["fundingRate"],
             "fundingRatePercent": r["fundingRatePercent"]}
            for r in sorted_by_rate[-10:]
        ],
        "intervals": interval_counts,
    }


async def get_klines(symbol: str, interval: str = "60", limit: int = 24) -> list[dict]:
    """
    Busca dados de candlestick (klines) de um símbolo na Bybit.
    interval: 1, 5, 15, 60, 240, D
    """
    # Mapear intervalos Binance-style para Bybit
    interval_map = {
        "1m": "1", "5m": "5", "15m": "15", "30m": "30",
        "1h": "60", "4h": "240", "1d": "D",
        "1": "1", "5": "5", "15": "15", "60": "60", "240": "240", "D": "D",
    }
    bybit_interval = interval_map.get(interval, "60")

    cache_key = f"klines_{symbol}_{bybit_interval}_{limit}"
    now = time.time()
    cached = _klines_cache.get(cache_key)
    if cached and cached.get("expires_at", 0) > now:
        return cached.get("data", [])

    try:
        result = await _fetch("/v5/market/kline", {
            "category": "linear",
            "symbol": symbol.upper(),
            "interval": bybit_interval,
            "limit": min(limit, 1000),
        })

        klines = []
        for k in result.get("list", []):
            klines.append({
                "timestamp": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        # Bybit retorna em ordem decrescente, inverter
        klines.reverse()

        _klines_cache[cache_key] = {
            "data": klines,
            "expires_at": now + _get_klines_ttl(bybit_interval),
        }

        # Limpeza simples para evitar crescimento indefinido.
        if len(_klines_cache) > 800:
            expired_keys = [
                key for key, value in _klines_cache.items()
                if value.get("expires_at", 0) <= now
            ]
            for key in expired_keys[:400]:
                _klines_cache.pop(key, None)

        return klines
    except Exception:
        return []
