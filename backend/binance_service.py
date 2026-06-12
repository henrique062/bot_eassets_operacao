"""
Serviço de conexão com a API pública da Binance Futures.
Busca funding rates, volume, intervalo de funding e Long/Short Ratio.
"""

import httpx
import time
from cachetools import TTLCache
import symbol_syncer

BINANCE_BASE_URL = "https://fapi.binance.com"

# Caches
_tickers_cache = TTLCache(maxsize=1, ttl=300)       # 5 minutos (funding muda a cada 8h)
_funding_info_cache = TTLCache(maxsize=1, ttl=3600)  # 1 hora
_history_cache = TTLCache(maxsize=200, ttl=300)      # 5 minutos
_lsr_cache = TTLCache(maxsize=200, ttl=120)
_klines_cache: dict[str, dict] = {}

# Cache de emergência: guarda o último resultado bem-sucedido sem expiração
# Usado quando a Binance está banindo o IP (rate limit)
_emergency_cache: dict = {}

# Cliente HTTP persistente — reutiliza conexões TCP/SSL entre requests
# Elimina overhead de handshake (100-400ms) por chamada
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
    "1m": 2.0,
    "3m": 3.0,
    "5m": 4.0,
    "15m": 5.0,
    "30m": 6.0,
    "1h": 8.0,
    "2h": 10.0,
    "4h": 12.0,
    "6h": 14.0,
    "8h": 16.0,
    "12h": 20.0,
    "1d": 25.0,
}


def _get_klines_ttl(interval: str) -> float:
    return _KLINES_TTL_BY_INTERVAL.get(interval, 8.0)


async def _fetch(endpoint: str, params: dict = None) -> list | dict:
    """Faz uma requisição GET assíncrona à API da Binance usando cliente persistente."""
    client = _get_client()
    response = await client.get(
        f"{BINANCE_BASE_URL}{endpoint}", params=params or {}
    )
    response.raise_for_status()
    return response.json()


async def _get_funding_info() -> dict:
    """
    Busca informações de intervalo de funding de todos os símbolos.
    Retorna dict: symbol -> fundingIntervalHours
    """
    cache_key = "funding_info"
    if cache_key in _funding_info_cache:
        return _funding_info_cache[cache_key]

    try:
        raw = await _fetch("/fapi/v1/fundingInfo")
        info = {}
        for item in raw:
            symbol = item.get("symbol", "")
            interval = item.get("fundingIntervalHours", 8)
            info[symbol] = int(interval)
        _funding_info_cache[cache_key] = info
        return info
    except Exception:
        return {}


async def get_all_funding_rates() -> list[dict]:
    """
    Busca todas as funding rates + dados de mercado (volume, 24h%) dos
    contratos perpétuos USDⓈ-M. Combina premiumIndex + ticker/24hr + fundingInfo.
    Em caso de ban/rate-limit da Binance, retorna os últimos dados cacheados.
    """
    cache_key = "all_tickers"
    if cache_key in _tickers_cache:
        return _tickers_cache[cache_key]

    # Buscar 2 endpoints em paralelo usando cliente persistente
    try:
        client = _get_client()
        premium_resp, ticker_resp = await asyncio.gather(
            client.get(f"{BINANCE_BASE_URL}/fapi/v1/premiumIndex"),
            client.get(f"{BINANCE_BASE_URL}/fapi/v1/ticker/24hr"),
        )
        premium_resp.raise_for_status()
        ticker_resp.raise_for_status()
    except Exception as e:
        # Se a Binance banir o IP ou der rate limit, retorna dados de emergência
        if "emergency" in _emergency_cache:
            import logging
            logging.warning(f"[binance_service] Usando cache de emergência: {e}")
            return _emergency_cache["emergency"]
        raise

    premium_data = premium_resp.json()
    ticker_data = ticker_resp.json()

    # Criar lookup de ticker por símbolo
    ticker_map = {}
    for t in ticker_data:
        ticker_map[t.get("symbol", "")] = t

    # Buscar funding intervals
    funding_info = await _get_funding_info()

    funding_data = []
    for item in premium_data:
        symbol = item.get("symbol", "")
        
        # Ignorar se o símbolo não faz parte da lista oficial da corretora
        if not symbol_syncer.is_valid_symbol("binance", symbol):
            continue
            
        funding_rate_str = item.get("lastFundingRate", "")

        if not funding_rate_str:
            continue

        try:
            funding_rate = float(funding_rate_str)
        except (ValueError, TypeError):
            continue

        mark_price = float(item.get("markPrice", 0))
        next_funding_time = item.get("nextFundingTime", "")

        # Dados do ticker 24hr
        ticker = ticker_map.get(symbol, {})
        volume = float(ticker.get("volume", 0))
        quote_volume = float(ticker.get("quoteVolume", 0))
        price_change_pct = float(ticker.get("priceChangePercent", 0))
        high_price = float(ticker.get("highPrice", 0))
        low_price = float(ticker.get("lowPrice", 0))
        last_price = float(ticker.get("lastPrice", 0)) or mark_price

        # Intervalo de funding
        interval_hours = funding_info.get(symbol, 8)

        # Taxa mensal considerando o intervalo real
        periods_per_day = 24 / interval_hours
        monthly = round(funding_rate * periods_per_day * 30 * 100, 2)

        funding_data.append({
            "symbol": symbol,
            "fundingRate": funding_rate,
            "fundingRatePercent": round(funding_rate * 100, 6),
            "monthlyRate": monthly,
            "nextFundingTime": str(next_funding_time),
            "lastPrice": last_price,
            "markPrice": mark_price,
            "volume24h": volume,
            "turnover24h": quote_volume,
            "price24hPcnt": round(price_change_pct, 4),
            "highPrice24h": high_price,
            "lowPrice24h": low_price,
            "fundingInterval": interval_hours,
        })

    # Ordenar por funding rate absoluto
    funding_data.sort(key=lambda x: abs(x["fundingRate"]), reverse=True)

    _tickers_cache[cache_key] = funding_data
    # Salvar no cache de emergência (sem expiração) para usar quando banido
    _emergency_cache["emergency"] = funding_data
    return funding_data


async def get_funding_history(symbol: str, limit: int = 50) -> list[dict]:
    """
    Busca o histórico de funding rates de um símbolo específico.
    """
    cache_key = f"history_{symbol}_{limit}"
    if cache_key in _history_cache:
        return _history_cache[cache_key]

    raw = await _fetch("/fapi/v1/fundingRate", {
        "symbol": symbol.upper(),
        "limit": min(limit, 1000),
    })

    history = []
    for item in raw:
        rate = float(item.get("fundingRate", 0))
        timestamp = int(item.get("fundingTime", 0))
        history.append({
            "symbol": item.get("symbol", ""),
            "fundingRate": rate,
            "fundingRatePercent": round(rate * 100, 6),
            "fundingRateTimestamp": timestamp,
            "datetime": time.strftime(
                "%Y-%m-%d %H:%M", time.gmtime(timestamp / 1000)
            ) if timestamp else "",
        })

    history.sort(key=lambda x: x["fundingRateTimestamp"], reverse=True)

    _history_cache[cache_key] = history
    return history


async def get_long_short_ratio(symbol: str, period: str = "1h", limit: int = 30) -> list[dict]:
    """
    Busca o Long/Short Ratio de um símbolo.
    period: 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
    """
    cache_key = f"lsr_{symbol}_{period}_{limit}"
    if cache_key in _lsr_cache:
        return _lsr_cache[cache_key]

    try:
        raw = await _fetch("/futures/data/globalLongShortAccountRatio", {
            "symbol": symbol.upper(),
            "period": period,
            "limit": min(limit, 500),
        })

        result = []
        for item in raw:
            timestamp = int(item.get("timestamp", 0))
            result.append({
                "symbol": symbol.upper(),
                "longShortRatio": float(item.get("longShortRatio", 0)),
                "longAccount": round(float(item.get("longAccount", 0)) * 100, 2),
                "shortAccount": round(float(item.get("shortAccount", 0)) * 100, 2),
                "timestamp": timestamp,
                "datetime": time.strftime(
                    "%Y-%m-%d %H:%M", time.gmtime(timestamp / 1000)
                ) if timestamp else "",
            })

        _lsr_cache[cache_key] = result
        return result

    except Exception as e:
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

    # Contagem por intervalo de funding
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


async def get_klines(symbol: str, interval: str = "1h", limit: int = 24) -> list[dict]:
    """
    Busca dados de candlestick (klines) de um símbolo.
    interval: 1m, 5m, 15m, 1h, 4h, 1d
    """
    cache_key = f"klines_{symbol}_{interval}_{limit}"
    now = time.time()
    cached = _klines_cache.get(cache_key)
    if cached and cached.get("expires_at", 0) > now:
        return cached.get("data", [])

    try:
        raw = await _fetch("/fapi/v1/klines", {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000),
        })

        result = []
        for k in raw:
            result.append({
                "timestamp": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        _klines_cache[cache_key] = {
            "data": result,
            "expires_at": now + _get_klines_ttl(interval),
        }

        # Limpeza simples para evitar crescimento indefinido.
        if len(_klines_cache) > 800:
            expired_keys = [
                key for key, value in _klines_cache.items()
                if value.get("expires_at", 0) <= now
            ]
            for key in expired_keys[:400]:
                _klines_cache.pop(key, None)

        return result
    except Exception:
        return []


# Importar asyncio no topo
import asyncio
