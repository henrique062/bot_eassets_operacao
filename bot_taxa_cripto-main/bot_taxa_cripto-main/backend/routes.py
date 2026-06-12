"""
Rotas da API para o dashboard de funding rates (Binance + Bybit).
Inclui anÃ¡lise com IA Gemini e batch LSR.
"""

import asyncio
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

import httpx

import binance_service
import bybit_service
import database as db
from ai_service import analyze_funding_opportunities
from auth import get_current_user, get_current_user_sse
from score_ai_service import run_score_ai_analysis, apply_score_ai_recommendation
from scoring import enrich_with_score, calculate_score, invalidate_score_settings_cache
from scoring_counter_trend import enrich_with_score_counter_trend, invalidate_counter_score_settings_cache

router = APIRouter(prefix="/api")

# Sub-routers com tags para o Swagger
_market_router = APIRouter(tags=["Market Data"])
_real_router = APIRouter(tags=["Real Trading"])
_ai_router = APIRouter(tags=["AI Analysis"])
_settings_router = APIRouter(tags=["Settings"])
_strategies_router = APIRouter(tags=["Strategies"])
_logs_router = APIRouter(tags=["Logs"])
_admin_router = APIRouter(tags=["Admin"])

EXCHANGES = {
    "binance": binance_service,
    "bybit": bybit_service,
}

# Comentário de controle: URL base do microserviço Coinalyze para desacoplar coleta/derivação de métricas.
COINALYZE_SERVICE_URL = os.getenv("COINALYZE_SERVICE_URL", "http://localhost:8010").rstrip("/")
_coinalyze_http_client: httpx.AsyncClient | None = None

# ConfiguraÃ§Ãµes padrÃ£o exibidas no painel administrativo.
# MantÃ©m compatibilidade entre modo coleta de taxa e modo counter-trend.
DEFAULT_SYSTEM_SETTINGS = {
    "score_thresholds": {
        "value": {"forte": 75, "moderado": 50, "fraco": 30},
        "description": "Thresholds de confianÃ§a do score para coleta de funding.",
    },
    "score_limits": {
        "value": {"max_volatility": 35, "min_volume": 2000000},
        "description": "Vetos de risco do score para coleta de funding.",
    },
    "score_weights": {
        "value": {"apy": 40, "vol": 20, "int": 10, "consistency": 15, "momentum": 15},
        "description": "Pesos dos componentes do score de coleta: APY, volume, intervalo, consistÃªncia e momentum.",
    },
    "score_thresholds_counter": {
        "value": {"forte": 75, "moderado": 50, "fraco": 30},
        "description": "Thresholds de confianÃ§a do score no modo counter-trend.",
    },
    "score_limits_counter": {
        "value": {"min_volume": 2000000, "min_funding_rate_pct": 0.01},
        "description": "Vetos de risco do counter-trend: liquidez mÃ­nima e funding mÃ­nimo.",
    },
    "score_weights_counter": {
        "value": {"extremity": 40, "persistence": 30, "volume": 20, "volatility_bonus": 10},
        "description": "Pesos do counter-trend: extremidade, persistÃªncia, volume e bÃ´nus de volatilidade.",
    },
}


def _get_service(exchange: str):
    svc = EXCHANGES.get(exchange.lower())
    if not svc:
        raise HTTPException(
            status_code=400,
            detail=f"Exchange invÃ¡lida: '{exchange}'. Use: {', '.join(EXCHANGES.keys())}",
        )
    return svc


# ComentÃ¡rio de controle: validaÃ§Ã£o de perfil para rotas administrativas sensÃ­veis.
def _require_admin(current_user: dict) -> None:
    if str(current_user.get("role", "")).lower() != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


# ComentÃ¡rio de controle: invalidaÃ§Ã£o imediata dos caches de score apÃ³s updates.
def _invalidate_score_settings_caches() -> None:
    invalidate_score_settings_cache()
    invalidate_counter_score_settings_cache()


def _derive_entry_margin(total_pnl, total_pnl_pct, price_pnl=None, price_pnl_pct=None):
    # Motivo: padronizar cÃ¡lculo da margem da operaÃ§Ã£o para relatÃ³rios de trades.
    try:
        pnl = float(total_pnl)
        pct = float(total_pnl_pct)
        if abs(pct) > 1e-9:
            return abs(pnl / (pct / 100.0))
    except Exception:
        pass

    try:
        pnl = float(price_pnl)
        pct = float(price_pnl_pct)
        if abs(pct) > 1e-9:
            return abs(pnl / (pct / 100.0))
    except Exception:
        pass

    return None


def _get_coinalyze_client() -> httpx.AsyncClient:
    global _coinalyze_http_client
    if _coinalyze_http_client is None or _coinalyze_http_client.is_closed:
        # Comentário de controle: cliente persistente para reduzir overhead de conexão entre backend e microserviço.
        _coinalyze_http_client = httpx.AsyncClient(
            timeout=35.0,
            limits=httpx.Limits(max_keepalive_connections=6, max_connections=10),
        )
    return _coinalyze_http_client


async def _coinalyze_get(path: str, params: dict | None = None) -> dict:
    client = _get_coinalyze_client()
    url = f"{COINALYZE_SERVICE_URL}{path}"
    try:
        response = await client.get(url, params=params or {})
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Microserviço Coinalyze indisponível em {COINALYZE_SERVICE_URL}: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail = None
        try:
            payload = response.json()
            detail = payload.get("detail") or payload.get("message")
        except Exception:
            detail = response.text[:400]
        raise HTTPException(status_code=response.status_code, detail=detail or "Falha ao consultar microserviço Coinalyze")

    try:
        return response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Resposta inválida do microserviço Coinalyze: {exc}") from exc


async def close_routes_http_clients() -> None:
    global _coinalyze_http_client
    # Comentário de controle: fecha cliente HTTP compartilhado das rotas para evitar warning de conexão pendente no shutdown.
    if _coinalyze_http_client is not None and not _coinalyze_http_client.is_closed:
        await _coinalyze_http_client.aclose()
        _coinalyze_http_client = None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROTAS PÃšBLICAS (dados de mercado â€” sem autenticaÃ§Ã£o)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_market_router.get("/funding-rates")
async def list_funding_rates(
    exchange: str = Query(default="binance"),
    search: str = Query(default=""),
    sort_by: str = Query(default="fundingRate"),
    sort_order: str = Query(default="desc"),
    scoring_mode: str = Query(default="harvesting"),
):
    try:
        svc = _get_service(exchange)
        rates = await svc.get_all_funding_rates()

        if scoring_mode == "counter_trend":
            rates = await enrich_with_score_counter_trend(rates)
        else:
            rates = await enrich_with_score(rates)

        if search:
            search_upper = search.upper()
            rates = [r for r in rates if search_upper in r["symbol"]]

        reverse = sort_order.lower() == "desc"
        numeric_fields = (
            "fundingRate", "fundingRatePercent", "lastPrice", "volume24h", "price24hPcnt",
            "monthlyRate", "turnover24h", "fundingInterval", "nextFundingTime",
        )
        if sort_by == "score":
            rates = sorted(rates, key=lambda x: x.get("scoreData", {}).get("score", 0), reverse=reverse)
        elif sort_by in numeric_fields:
            rates = sorted(rates, key=lambda x: float(x.get(sort_by, 0) or 0), reverse=reverse)
        elif sort_by == "symbol":
            rates = sorted(rates, key=lambda x: x.get("symbol", ""), reverse=reverse)

        return {"success": True, "exchange": exchange, "count": len(rates), "data": rates}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_market_router.get("/funding-rates/{symbol}/history")
async def funding_rate_history(
    symbol: str,
    exchange: str = Query(default="binance"),
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        svc = _get_service(exchange)
        history = await svc.get_funding_history(symbol, limit)
        return {
            "success": True, "exchange": exchange,
            "symbol": symbol.upper(), "count": len(history), "data": history,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_market_router.get("/funding-rates/{symbol}/lsr")
async def long_short_ratio(
    symbol: str,
    exchange: str = Query(default="binance"),
    period: str = Query(default="1h"),
    limit: int = Query(default=30, ge=1, le=500),
):
    try:
        svc = _get_service(exchange)
        data = await svc.get_long_short_ratio(symbol, period, limit)
        return {
            "success": True, "exchange": exchange,
            "symbol": symbol.upper(), "period": period,
            "count": len(data), "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_market_router.get("/funding-rates/{symbol}/klines")
async def klines(
    symbol: str,
    exchange: str = Query(default="binance"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=24, ge=1, le=1000),
):
    try:
        svc = _get_service(exchange)
        data = await svc.get_klines(symbol, interval, limit)
        return {
            "success": True, "exchange": exchange,
            "symbol": symbol.upper(), "interval": interval,
            "count": len(data), "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_market_router.get("/batch-lsr")
async def batch_lsr(
    symbols: str = Query(description="SÃ­mbolos separados por vÃ­rgula"),
    exchange: str = Query(default="binance"),
):
    try:
        svc = _get_service(exchange)
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()][:20]

        async def fetch_one(sym):
            try:
                data = await svc.get_long_short_ratio(sym, "1h", 1)
                if data:
                    return sym, data[0]
            except Exception:
                pass
            return sym, None

        results = await asyncio.gather(*[fetch_one(s) for s in symbol_list])
        lsr_map = {}
        for sym, data in results:
            if data:
                lsr_map[sym] = data

        return {"success": True, "data": lsr_map}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_market_router.get("/backtest")
async def backtest(
    symbol: str = Query(description="Par para backtesting (ex: BTCUSDT)"),
    exchange: str = Query(default="binance"),
    capital: float = Query(default=1000.0, ge=10),
    days: int = Query(default=7, ge=1, le=90),
    leverage: int = Query(default=1, ge=1, le=20),
    fee_type: str = Query(default="maker"),
    mode: str = Query(default="normal", description="normal ou sniping"),
    target_take_profit_pct: float | None = Query(default=None, description="Take profit (%)"),
):
    from backtester import run_backtest
    try:
        svc = _get_service(exchange)
        sym = symbol.upper()
        if not sym.endswith("USDT") and not sym.endswith("USDC"):
            sym += "USDT"
        result = await run_backtest(
            service=svc, symbol=sym, capital=capital,
            days=days, leverage=leverage, fee_type=fee_type, mode=mode,
            target_take_profit_pct=target_take_profit_pct,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_market_router.get("/stats")
async def funding_stats(exchange: str = Query(default="binance")):
    try:
        svc = _get_service(exchange)
        stats = await svc.get_stats()
        return {"success": True, "exchange": exchange, "data": stats}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_market_router.get("/coinalyze/markets")
async def coinalyze_markets(
    exchange: str = Query(default="binance"),
    quote_asset: str = Query(default="USDT"),
):
    # Comentário de controle: rota de passthrough para expor o catálogo de mercados filtrado pelo microserviço.
    return await _coinalyze_get(
        "/v1/markets",
        params={
            "exchange": exchange.lower(),
            "quote_asset": quote_asset.upper(),
        },
    )


@_market_router.get("/coinalyze/opportunities")
async def coinalyze_opportunities(
    exchange: str = Query(default="binance"),
    quote_asset: str = Query(default="USDT"),
    interval: str = Query(default="1hour"),
    lookback_hours: int = Query(default=24, ge=6, le=72),
    symbols_limit: int = Query(default=6, ge=1, le=20),
    max_rows: int = Query(default=20, ge=1, le=100),
    min_volume_24h: float = Query(default=0, ge=0),
):
    try:
        svc = _get_service(exchange)
        rates = await svc.get_all_funding_rates()

        # Comentário de controle: pré-seleciona símbolos mais extremos de funding para caber no rate-limit da Coinalyze.
        filtered = []
        quote_upper = quote_asset.upper()
        for row in rates:
            symbol = str(row.get("symbol") or "").upper()
            if quote_upper and not symbol.endswith(quote_upper):
                continue
            volume = float(row.get("turnover24h", 0) or row.get("volume24h", 0) or 0)
            if min_volume_24h > 0 and volume < min_volume_24h:
                continue
            filtered.append(row)

        filtered.sort(key=lambda x: abs(float(x.get("fundingRate", 0) or 0)), reverse=True)
        picked = filtered[:symbols_limit]
        picked_symbols = [str(x.get("symbol") or "").upper() for x in picked if x.get("symbol")]

        response = await _coinalyze_get(
            "/v1/opportunities",
            params={
                "exchange": exchange.lower(),
                "symbols": ",".join(picked_symbols),
                "quote_asset": quote_upper,
                "interval": interval,
                "lookback_hours": lookback_hours,
                "max_rows": max_rows,
            },
        )

        # Comentário de controle: anexa dados locais (preço/next funding/volume) para decisão operacional na UI.
        local_map = {str(item.get("symbol") or "").upper(): item for item in picked}
        enriched_rows = []
        for item in response.get("data", []):
            symbol = str(item.get("symbol") or "").upper()
            local = local_map.get(symbol, {})
            enriched_rows.append(
                {
                    **item,
                    "localSnapshot": {
                        "lastPrice": float(local.get("lastPrice", 0) or 0),
                        "fundingRatePercentLocal": float(local.get("fundingRatePercent", 0) or 0),
                        "nextFundingTime": local.get("nextFundingTime"),
                        "volume24h": float(local.get("turnover24h", 0) or local.get("volume24h", 0) or 0),
                    },
                }
            )

        response["selectedSymbolsFromFunding"] = picked_symbols
        response["data"] = enriched_rows
        response["backendHint"] = {
            "exchange": exchange.lower(),
            "symbolsLimit": symbols_limit,
            "quoteAsset": quote_upper,
            "minVolume24h": min_volume_24h,
        }
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Comentário de controle: endpoint de análise IA de configurações de score (modo atual).
@_settings_router.post("/settings/score-ai/analyze")
async def score_ai_analyze(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    try:
        _require_admin(current_user)
        result = await run_score_ai_analysis(user_id=current_user["id"], payload=payload or {})
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Comentário de controle: endpoint de aplicação confirmada das sugestões de score.
@_settings_router.post("/settings/score-ai/apply")
async def score_ai_apply(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    try:
        _require_admin(current_user)
        analysis_id = int((payload or {}).get("analysisId") or 0)
        if analysis_id <= 0:
            raise HTTPException(status_code=400, detail="analysisId é obrigatório")
        result = await apply_score_ai_recommendation(user_id=current_user["id"], analysis_id=analysis_id)
        _invalidate_score_settings_caches()
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROTAS PROTEGIDAS â€” Real Trading
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_real_router.get("/real-trading")
async def real_trading_status(current_user: dict = Depends(get_current_user)):
    from real_trader import get_status
    return await get_status(user_id=current_user["id"])


@_real_router.get("/real-trading/sessions")
async def real_trading_sessions(current_user: dict = Depends(get_current_user)):
    from real_trader import get_sessions
    return {"success": True, "data": await get_sessions(user_id=current_user["id"])}


@_real_router.get("/real-trading/events")
async def real_trading_events(
    request: Request,
    current_user: dict = Depends(get_current_user_sse),
):
    from real_trader import get_status

    async def generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                status = await get_status(user_id=current_user["id"])
                yield f"data: {json.dumps(status)}\n\n"
            except Exception:
                pass
            await asyncio.sleep(2)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@_real_router.get("/real-trading/validate-keys")
async def real_trading_validate_keys(
    exchange: str = Query(default="binance"),
    current_user: dict = Depends(get_current_user),
):
    """Valida se as chaves de API do usuÃ¡rio para a exchange estÃ£o funcionando."""
    import ccxt.async_support as ccxt
    from real_trader import _get_api_keys

    try:
        keys = await _get_api_keys(exchange, user_id=current_user["id"])
        api_key = keys.get("apiKey", "")
        api_secret = keys.get("apiSecret", "")

        if not api_key or not api_secret:
            return {"success": False, "connected": False, "message": "Chaves de API nÃ£o configuradas"}

        exchange_class = getattr(ccxt, exchange.lower())
        ex = exchange_class({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        try:
            await ex.load_markets()
            balance = await ex.fetch_balance()
            usdt = balance.get("USDT", {}).get("free", 0) or 0
            return {
                "success": True,
                "connected": True,
                "message": f"Conectado â€” Saldo disponÃ­vel: ${float(usdt):.2f} USDT",
            }
        finally:
            await ex.close()

    except Exception as e:
        return {"success": False, "connected": False, "message": f"Erro de autenticaÃ§Ã£o: {str(e)[:120]}"}


@_real_router.get("/real-trading/logs")
async def get_real_global_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session_id: int = Query(default=None),
    exchange: str = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        conditions = ["c.user_id = $1"]
        params: list = [current_user["id"]]
        idx = 2

        if session_id is not None:
            conditions.append(f"t.config_id = ${idx}")
            params.append(session_id)
            idx += 1

        if exchange:
            conditions.append(f"t.exchange = ${idx}")
            params.append(exchange.lower())
            idx += 1

        where = "WHERE " + " AND ".join(conditions)

        rows = await db.fetch(
            f"""
            SELECT
                t.id, t.config_id, t.symbol, t.direction,
                t.entry_price, t.exit_price, t.funding_rate,
                t.funding_pnl, t.price_pnl, t.price_pnl_pct,
                t.fee_cost, t.total_pnl, t.total_pnl_pct,
                t.balance_after, t.open_time, t.close_time,
                t.trade_timestamp, t.exchange, t.close_reason, t.created_at,
                c.session_name, c.capital, c.leverage, c.fee_type
            FROM real_trades t
            LEFT JOIN real_config c ON c.id = t.config_id
            {where}
            ORDER BY t.id DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, offset,
        )

        total = await db.fetchval(
            f"""
            SELECT COUNT(*) FROM real_trades t
            LEFT JOIN real_config c ON c.id = t.config_id
            {where}
            """,
            *params,
        )

        data = [
            {
                "id": r["id"],
                "configId": r["config_id"],
                "sessionName": r["session_name"] or f"Bot #{r['config_id']}",
                "symbol": r["symbol"],
                "direction": r["direction"],
                "entryPrice": float(r["entry_price"] or 0),
                "exitPrice": float(r["exit_price"] or 0),
                "fundingRate": float(r["funding_rate"] or 0),
                "fundingPnl": float(r["funding_pnl"] or 0),
                "pricePnl": float(r["price_pnl"] or 0),
                "pricePnlPct": float(r["price_pnl_pct"] or 0),
                "feeCost": float(r["fee_cost"] or 0),
                "totalPnl": float(r["total_pnl"] or 0),
                "totalPnlPct": float(r["total_pnl_pct"] or 0),
                # Motivo: expÃµe margem usada na entrada para todos os relatÃ³rios de operaÃ§Ãµes.
                "entryMargin": _derive_entry_margin(
                    r["total_pnl"],
                    r["total_pnl_pct"],
                    r["price_pnl"],
                    r["price_pnl_pct"],
                ),
                "balanceAfter": float(r["balance_after"] or 0),
                "openTime": r["open_time"],
                "closeTime": r["close_time"],
                "tradeTimestamp": r["trade_timestamp"],
                "exchange": r["exchange"],
                "closeReason": r["close_reason"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
                "capital": float(r["capital"] or 0),
                "leverage": r["leverage"],
                "feeType": r["fee_type"],
            }
            for r in rows
        ]

        return {"success": True, "data": data, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_real_router.get("/real-trading/chart-operations")
async def real_trading_chart_operations(
    exchange: str = Query(default="binance"),
    # Motivo: suportar visÃ£o global no painel da operaÃ§Ã£o manual (todos os pares),
    # mantendo compatibilidade com o modo por sÃ­mbolo usado nos overlays do grÃ¡fico.
    symbol: str | None = Query(default=None, description="SÃ­mbolo opcional (ex: BTCUSDT)"),
    limit_closed: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    from real_trader import get_chart_operations

    try:
        return await get_chart_operations(
            exchange=exchange,
            symbol=symbol,
            user_id=current_user["id"],
            limit_closed=limit_closed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_real_router.get("/real-trading/{session_id}")
async def real_trading_session_status(
    session_id: int,
    current_user: dict = Depends(get_current_user),
):
    from real_trader import get_session_status
    result = await get_session_status(session_id, user_id=current_user["id"])
    if not result:
        raise HTTPException(status_code=404, detail="SessÃ£o Real nÃ£o encontrada")
    return result


@_real_router.post("/real-trading/start")
async def real_trading_start(
    exchange: str = Query(default="binance"),
    config: dict = None,
    current_user: dict = Depends(get_current_user),
):
    from real_trader import start_trading
    try:
        svc = _get_service(exchange)
        cfg = config or {}
        cfg["exchange"] = exchange
        cfg["user_id"] = current_user["id"]
        return await start_trading(svc, exchange, cfg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@_real_router.post("/real-trading/stop")
async def real_trading_stop(
    session_id: int = Query(description="ID da sessÃ£o a parar"),
    current_user: dict = Depends(get_current_user),
):
    from real_trader import stop_trading
    try:
        return await stop_trading(session_id, user_id=current_user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@_real_router.patch("/real-trading/sessions/{session_id}")
async def real_trading_edit_session(
    session_id: int,
    config: dict,
    current_user: dict = Depends(get_current_user),
):
    """Edita configuraÃ§Ãµes de uma sessÃ£o ativa (stop loss, min profit, nome)."""
    from real_trader import edit_session
    try:
        return await edit_session(session_id, config, user_id=current_user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@_real_router.post("/real-trading/{session_id}/close-all")
async def real_trading_close_all(
    session_id: int,
    current_user: dict = Depends(get_current_user),
):
    from real_trader import close_all_positions
    try:
        return await close_all_positions(session_id, user_id=current_user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@_real_router.post("/real-trading/{session_id}/manual-trigger")
async def real_trading_manual_trigger(
    session_id: int,
    payload: dict | None = None,
    current_user: dict = Depends(get_current_user),
):
    from real_trader import trigger_manual_trade
    try:
        symbol = None
        if isinstance(payload, dict):
            symbol = payload.get("symbol")
        return await trigger_manual_trade(
            session_id=session_id,
            symbol=symbol,
            user_id=current_user["id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@_real_router.delete("/real-trading/sessions/{session_id}")
async def real_trading_delete_session(
    session_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Deleta uma sessÃ£o de real trading inativa."""
    from real_trader import delete_session
    try:
        return await delete_session(session_id, user_id=current_user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@_real_router.post("/real-trading/{session_id}/ai-analyze")
async def real_trading_ai_analyze(
    session_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Analisa o desempenho do bot com IA e retorna sugestÃµes de configuraÃ§Ã£o."""
    from ai_service import analyze_bot_cycle

    try:
        # Verificar permissÃ£o
        row = await db.fetchrow(
            "SELECT * FROM real_config WHERE id=$1 AND user_id=$2",
            session_id, current_user["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="SessÃ£o nÃ£o encontrada")

        # Buscar trades recentes desse bot
        trades_rows = await db.fetch(
            """
            SELECT id, symbol, direction, entry_price, exit_price, funding_rate,
                   funding_pnl, price_pnl, price_pnl_pct, fee_cost, total_pnl,
                   total_pnl_pct, balance_after, open_time, close_time, exchange,
                   close_reason, created_at
            FROM real_trades
            WHERE config_id = $1
            ORDER BY id DESC
            LIMIT 50
            """,
            session_id,
        )

        trades = [
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "direction": r["direction"],
                "entryPrice": float(r["entry_price"] or 0),
                "exitPrice": float(r["exit_price"] or 0),
                "fundingPnl": float(r["funding_pnl"] or 0),
                "pricePnl": float(r["price_pnl"] or 0),
                "pricePnlPct": float(r["price_pnl_pct"] or 0),
                "feeCost": float(r["fee_cost"] or 0),
                "totalPnl": float(r["total_pnl"] or 0),
                "totalPnlPct": float(r["total_pnl_pct"] or 0),
                "closeReason": r["close_reason"],
                "openTime": r["open_time"],
                "closeTime": r["close_time"],
            }
            for r in trades_rows
        ]

        bot_config = {
            "operationMode": row["operation_mode"],
            "exchange": row["exchange"],
            "capital": float(row["capital"] or 0),
            "leverage": row["leverage"],
            "feeType": row["fee_type"],
            "entrySeconds": row.get("entry_seconds", 30),
            "exitSeconds": row.get("exit_seconds", 30),
            "stopLossPct": float(row["stop_loss_pct"]) if row["stop_loss_pct"] is not None else None,
            "minProfitPct": float(row["min_profit_pct"]) if row["min_profit_pct"] is not None else None,
            "trailingStartProfitPct": float(row["trailing_start_profit_pct"]) if row.get("trailing_start_profit_pct") is not None else None,
            "autoMaxSymbols": row.get("auto_max_symbols", 8),
            "makerTimeoutSeconds": row.get("maker_timeout_seconds", 8),
            "symbols": list(row["symbols"] or []),
        }

        result = await analyze_bot_cycle(bot_config, trades, trigger_type="manual")

        # Salvar no banco
        analysis_id = await db.fetchval(
            """
            INSERT INTO bot_ai_analyses (config_id, analysis_text, suggested_config, trigger_type)
            VALUES ($1, $2, $3::jsonb, $4)
            RETURNING id
            """,
            session_id,
            result.get("analysis", ""),
            json.dumps(result.get("suggested_config", {})),
            "manual",
        )

        return {
            "success": True,
            "id": analysis_id,
            "analysis": result.get("analysis", ""),
            "suggestedConfig": result.get("suggested_config", {}),
            "currentConfig": bot_config,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_real_router.post("/real-trading/{session_id}/ai-apply")
async def real_trading_ai_apply(
    session_id: int,
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """Aplica as sugestÃµes da IA nas configuraÃ§Ãµes do bot."""
    from real_trader import edit_session

    try:
        suggested = payload.get("suggestedConfig", {})
        if not suggested:
            raise HTTPException(status_code=400, detail="Nenhuma sugestÃ£o para aplicar")

        result = await edit_session(session_id, suggested, user_id=current_user["id"])

        # Marcar anÃ¡lise como aplicada
        analysis_id = payload.get("analysisId")
        if analysis_id:
            await db.execute(
                "UPDATE bot_ai_analyses SET applied = TRUE, applied_at = NOW() WHERE id = $1",
                analysis_id,
            )

        return {"success": True, "message": "SugestÃµes aplicadas com sucesso", "session": result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_real_router.get("/real-trading/{session_id}/ai-analyses")
async def real_trading_ai_analyses(
    session_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Lista as anÃ¡lises IA passadas de um bot."""
    try:
        # Verificar permissÃ£o
        owner = await db.fetchrow(
            "SELECT id FROM real_config WHERE id=$1 AND user_id=$2",
            session_id, current_user["id"],
        )
        if not owner:
            raise HTTPException(status_code=404, detail="SessÃ£o nÃ£o encontrada")

        rows = await db.fetch(
            """
            SELECT id, analysis_text, suggested_config, applied, applied_at,
                   created_at, trigger_type
            FROM bot_ai_analyses
            WHERE config_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            session_id, limit,
        )

        data = [
            {
                "id": r["id"],
                "analysis": r["analysis_text"],
                "suggestedConfig": json.loads(r["suggested_config"]) if isinstance(r["suggested_config"], str) else r["suggested_config"],
                "applied": r["applied"],
                "appliedAt": r["applied_at"].isoformat() if r["applied_at"] else None,
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
                "triggerType": r["trigger_type"],
            }
            for r in rows
        ]

        return {"success": True, "data": data}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_real_router.get("/real-trading/{session_id}/order-logs")
async def real_trading_order_logs(
    session_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    level: str = Query(default=""),
    event: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
):
    """Logs de ordens e erros de API de um bot de real trading, com filtros opcionais."""
    owner = await db.fetchrow(
        "SELECT id FROM real_config WHERE id=$1 AND user_id=$2",
        session_id, current_user["id"],
    )
    if not owner:
        raise HTTPException(status_code=404, detail="SessÃ£o nÃ£o encontrada")

    conditions = ["config_id = $1"]
    params: list = [session_id]

    if level:
        params.append(level.upper())
        conditions.append(f"log_level = ${len(params)}")
    if event:
        params.append(event.lower())
        conditions.append(f"event = ${len(params)}")

    params.append(limit)
    where = " AND ".join(conditions)
    rows = await db.fetch(
        f"""
        SELECT id, log_level, event, symbol, direction, exchange, message, details, created_at
        FROM real_order_logs
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${len(params)}
        """,
        *params,
    )
    data = [
        {
            "id": r["id"],
            "level": r["log_level"],
            "event": r["event"],
            "symbol": r["symbol"],
            "direction": r["direction"],
            "exchange": r["exchange"],
            "message": r["message"],
            "details": r["details"],
            "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"success": True, "sessionId": session_id, "total": len(data), "data": data}


@_real_router.post("/real-trading/manual/start")
async def real_trading_manual_start(
    config: dict,
    exchange: str = Query(default="binance"),
    current_user: dict = Depends(get_current_user),
):
    """
    OperaÃ§Ã£o manual real: abre posiÃ§Ã£o imediata com proteÃ§Ã£o por SL/Trailing.
    """
    from real_trader import execute_manual_trade
    try:
        symbol = str(config.get("symbol", "")).upper().strip()
        direction = str(config.get("direction", "LONG")).upper()
        fee_type = str(config.get("feeType", "maker"))
        capital = float(config.get("capital", 10.0))
        leverage = int(config.get("leverage", 1))
        maker_timeout_s = int(config.get("makerTimeout", 8))
        stop_loss_pct = config.get("stopLossPct")
        stop_loss_usd = config.get("stopLossUsd")
        trailing_stop_pct = config.get("trailingStopPct")
        trailing_start_profit_pct = config.get("trailingStartProfitPct")
        break_even_at_pct = config.get("breakEvenAtPct")
        partial_tp_pct = config.get("partialTpPct")
        partial_tp_size = config.get("partialTpSize")
        entry_limit_price = config.get("entryLimitPrice")

        # Motivo: entrada limit manual deve ser preÃ§o positivo quando informado.
        if entry_limit_price is not None and str(entry_limit_price).strip() != "":
            try:
                if float(entry_limit_price) <= 0:
                    raise ValueError
            except Exception:
                raise ValueError("Campo 'entryLimitPrice' invÃ¡lido. Informe um preÃ§o maior que zero.")
        return await execute_manual_trade(
            exchange=exchange,
            symbol=symbol,
            direction=direction,
            fee_type=fee_type,
            capital=capital,
            leverage=leverage,
            user_id=current_user["id"],
            maker_timeout_s=maker_timeout_s,
            stop_loss_pct=stop_loss_pct,
            stop_loss_usd=stop_loss_usd,
            trailing_stop_pct=trailing_stop_pct,
            trailing_start_profit_pct=trailing_start_profit_pct,
            break_even_at_pct=break_even_at_pct,
            partial_tp_pct=partial_tp_pct,
            partial_tp_size=partial_tp_size,
            entry_limit_price=entry_limit_price,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@_real_router.post("/real-trading/test")
async def real_trading_test(
    config: dict,
    exchange: str = Query(default="binance"),
    current_user: dict = Depends(get_current_user),
):
    """
    Compatibilidade legada: mantÃ©m endpoint antigo, agora delegando para operaÃ§Ã£o manual real.
    """
    from real_trader import execute_test_trade
    try:
        symbol = str(config.get("symbol", "")).upper().strip()
        direction = str(config.get("direction", "LONG")).upper()
        fee_type = str(config.get("feeType", "maker"))
        capital = float(config.get("capital", 10.0))
        leverage = int(config.get("leverage", 1))
        maker_timeout_s = int(config.get("makerTimeout", 8))
        stop_loss_pct = config.get("stopLossPct")
        stop_loss_usd = config.get("stopLossUsd")
        trailing_stop_pct = config.get("trailingStopPct")
        trailing_start_profit_pct = config.get("trailingStartProfitPct")
        return await execute_test_trade(
            exchange=exchange,
            symbol=symbol,
            direction=direction,
            fee_type=fee_type,
            capital=capital,
            leverage=leverage,
            user_id=current_user["id"],
            maker_timeout_s=maker_timeout_s,
            stop_loss_pct=stop_loss_pct,
            stop_loss_usd=stop_loss_usd,
            trailing_stop_pct=trailing_stop_pct,
            trailing_start_profit_pct=trailing_start_profit_pct,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROTAS PROTEGIDAS â€” IA / Smart Reports
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_ai_router.get("/ai-analysis")
async def ai_analysis(
    exchange: str = Query(default="binance"),
    current_user: dict = Depends(get_current_user),
):
    try:
        svc = _get_service(exchange)
        rates = await svc.get_all_funding_rates()
        stats = await svc.get_stats()

        sorted_rates = sorted(rates, key=lambda x: x["fundingRate"], reverse=True)
        top_positive = sorted_rates[:10]
        top_negative = sorted_rates[-10:]

        key_symbols = [r["symbol"] for r in (top_positive[:5] + top_negative[:5])]

        async def fetch_lsr(sym):
            try:
                data = await svc.get_long_short_ratio(sym, "1h", 1)
                if data:
                    return sym, data[0]
            except Exception:
                pass
            return sym, None

        lsr_results = await asyncio.gather(*[fetch_lsr(s) for s in key_symbols])
        lsr_data = {}
        for sym, data in lsr_results:
            if data:
                lsr_data[sym] = {
                    "longShortRatio": data["longShortRatio"],
                    "longAccount": data["longAccount"],
                    "shortAccount": data["shortAccount"],
                }

        async def simplify(item):
            score_data = await calculate_score(item)
            return {
                "symbol": item["symbol"],
                "fundingRatePercent": item["fundingRatePercent"],
                "monthlyRate": item["monthlyRate"],
                "lastPrice": item["lastPrice"],
                "volume24h": item.get("volume24h", 0),
                "price24hPcnt": item.get("price24hPcnt", 0),
                "fundingInterval": item.get("fundingInterval", 8),
                "lsr": lsr_data.get(item["symbol"]),
                "score": score_data["score"],
                "confidence": score_data["confidence"],
                "signal": score_data["signal"],
                "shouldOpen": score_data["shouldOpen"],
                "reasons": score_data["reasons"],
            }

        top_pos_simple = await asyncio.gather(*[simplify(r) for r in top_positive])
        top_neg_simple = await asyncio.gather(*[simplify(r) for r in top_negative])

        result = await analyze_funding_opportunities(
            top_pos_simple, top_neg_simple, lsr_data, stats, exchange
        )

        analysis_text = result.get("analysis", "")
        recommended_coins = result.get("recommended_coins", [])

        report_row = await db.fetchrow(
            """
            INSERT INTO ai_reports (exchange, general_stats, market_overview, recommended_coins)
            VALUES ($1, $2::jsonb, $3, $4::jsonb)
            RETURNING id, created_at
            """,
            exchange,
            json.dumps(stats),
            analysis_text,
            json.dumps(recommended_coins),
        )

        return {
            "success": True,
            "exchange": exchange,
            "report_id": report_row["id"],
            "created_at": report_row["created_at"].isoformat() if report_row["created_at"] else None,
            "analysis": analysis_text,
            "recommended_coins": recommended_coins,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_ai_router.get("/smart-reports")
async def list_smart_reports(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    try:
        rows = await db.fetch(
            """
            SELECT id, exchange, created_at, is_accurate
            FROM ai_reports
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset,
        )
        total = await db.fetchval("SELECT COUNT(*) FROM ai_reports")

        data = [
            {
                "id": r["id"],
                "exchange": r["exchange"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
                "isAccurate": r["is_accurate"],
            }
            for r in rows
        ]
        return {"success": True, "data": data, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_ai_router.get("/smart-reports/{report_id}")
async def get_smart_report(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    try:
        r = await db.fetchrow("SELECT * FROM ai_reports WHERE id = $1", report_id)
        if not r:
            raise HTTPException(status_code=404, detail="RelatÃ³rio nÃ£o encontrado")

        return {
            "success": True,
            "data": {
                "id": r["id"],
                "exchange": r["exchange"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
                "generalStats": json.loads(r["general_stats"]) if isinstance(r["general_stats"], str) else r["general_stats"],
                "marketOverview": r["market_overview"],
                "recommendedCoins": json.loads(r["recommended_coins"]) if isinstance(r["recommended_coins"], str) else r["recommended_coins"],
                "isAccurate": r["is_accurate"],
                "accuracyDetails": r["accuracy_details"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# BLACKLIST INTELIGENTE DE SÃMBOLOS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_ai_router.get("/symbols/blacklist")
async def get_symbol_blacklist(
    current_user: dict = Depends(get_current_user),
):
    """Lista blacklists de sÃ­mbolos do usuÃ¡rio atual."""
    try:
        from symbol_blacklist import get_user_blacklist
        user_id = current_user["id"]
        data = await get_user_blacklist(user_id)
        active = [d for d in data if d["isActive"]]
        return {"success": True, "data": data, "activeCount": len(active)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_ai_router.delete("/symbols/blacklist/{symbol}")
async def clear_symbol_blacklist_endpoint(
    symbol: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove manualmente a blacklist de um sÃ­mbolo."""
    try:
        from symbol_blacklist import clear_symbol_blacklist
        user_id = current_user["id"]
        ok = await clear_symbol_blacklist(user_id, symbol.upper())
        if not ok:
            raise HTTPException(status_code=404, detail=f"SÃ­mbolo {symbol} nÃ£o encontrado na blacklist")
        return {"success": True, "symbol": symbol.upper(), "message": "Blacklist removida com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# GERAÃ‡ÃƒO DE CONFIG DE BOT VIA IA
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_ai_router.post("/ai/generate-bot-config")
async def generate_bot_config_from_report(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Gera configuraÃ§Ã£o de bot otimizada pela IA a partir de um relatÃ³rio.
    NÃƒO inicia o bot â€” retorna a config para o usuÃ¡rio revisar antes de criar.
    """
    try:
        from ai_service import generate_bot_config
        body = await request.json()

        report_id = body.get("reportId")
        capital = float(body.get("capital", 100))
        leverage = int(body.get("leverage", 5))
        exchange = str(body.get("exchange", "binance")).lower()
        operation_mode = body.get("operationMode", "auto_strongest")

        if not report_id:
            raise HTTPException(status_code=400, detail="reportId Ã© obrigatÃ³rio")

        r = await db.fetchrow("SELECT recommended_coins FROM ai_reports WHERE id = $1", report_id)
        if not r:
            raise HTTPException(status_code=404, detail="RelatÃ³rio nÃ£o encontrado")

        recommended_coins = (
            json.loads(r["recommended_coins"])
            if isinstance(r["recommended_coins"], str)
            else (r["recommended_coins"] or [])
        )
        if not recommended_coins:
            raise HTTPException(status_code=400, detail="RelatÃ³rio nÃ£o possui moedas recomendadas")

        user_id = current_user["id"]
        trades_rows = await db.fetch(
            """
            SELECT rc.stop_loss_pct, rc.fee_type
            FROM real_trades rt
            JOIN real_config rc ON rc.id = rt.config_id
            WHERE rc.user_id = $1 AND rt.total_pnl > 0
            ORDER BY rt.trade_timestamp DESC
            LIMIT 50
            """,
            user_id,
        )

        historical_stats = {}
        if trades_rows:
            stop_losses = [float(r["stop_loss_pct"] or 2.0) for r in trades_rows if r["stop_loss_pct"]]
            fee_types = [r["fee_type"] for r in trades_rows if r["fee_type"]]
            historical_stats = {
                "avgStopLossPct": round(sum(stop_losses) / len(stop_losses), 2) if stop_losses else 2.0,
                "mostUsedFeeType": max(set(fee_types), key=fee_types.count) if fee_types else "maker",
                "totalWinningTrades": len(trades_rows),
            }

        config = await generate_bot_config(
            recommended_coins=recommended_coins,
            capital=capital,
            leverage=leverage,
            exchange=exchange,
            operation_mode=operation_mode,
            historical_stats=historical_stats,
        )

        ai_justification = config.pop("ai_justification", "")
        return {
            "success": True,
            "config": config,
            "ai_justification": ai_justification,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ANÃLISE DE MERCADO AO VIVO PARA GERAÃ‡ÃƒO DE BOT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_ai_router.post("/ai/analyze-market-for-bot")
async def analyze_market_for_bot(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """Analisa mercado ao vivo e gera config de bot via IA (sem relatÃ³rio prÃ©vio)."""
    try:
        from ai_service import analyze_market_for_bot_config

        capital = float(payload.get("capital", 100.0))
        leverage = int(payload.get("leverage", 5))
        exchange = str(payload.get("exchange", "binance")).lower()

        if capital < 10:
            raise HTTPException(status_code=400, detail="Capital mÃ­nimo Ã© $10")
        if leverage < 1 or leverage > 20:
            raise HTTPException(status_code=400, detail="Alavancagem deve ser entre 1 e 20")

        # Busca Ãºltimas taxas do banco (snapshot mais recente)
        rates = await db.fetch(
            """
            SELECT symbol, funding_rate, funding_rate_pct, funding_interval,
                   last_price, volume_24h, price_24h_pcnt
            FROM funding_rate_snapshots
            WHERE exchange=$1
              AND captured_at=(SELECT MAX(captured_at) FROM funding_rate_snapshots WHERE exchange=$1)
            ORDER BY ABS(funding_rate_pct) DESC
            LIMIT 30
            """,
            exchange,
        )
        if not rates:
            raise HTTPException(status_code=404, detail=f"Nenhum dado de funding rate encontrado para {exchange}")

        # HistÃ³rico de sucesso do usuÃ¡rio
        user_id = current_user["id"]
        hist_rows = await db.fetch(
            """
            SELECT rc.stop_loss_pct, rc.fee_type
            FROM real_trades rt
            JOIN real_config rc ON rc.id = rt.config_id
            WHERE rc.user_id = $1 AND rt.total_pnl > 0
            ORDER BY rt.trade_timestamp DESC
            LIMIT 50
            """,
            user_id,
        )

        historical_stats = {}
        if hist_rows:
            stop_losses = [float(r["stop_loss_pct"] or 2.0) for r in hist_rows if r["stop_loss_pct"]]
            fee_types = [r["fee_type"] for r in hist_rows if r["fee_type"]]
            historical_stats = {
                "avgStopLossPct": round(sum(stop_losses) / len(stop_losses), 2) if stop_losses else 2.0,
                "mostUsedFeeType": max(set(fee_types), key=fee_types.count) if fee_types else "maker",
                "totalWinningTrades": len(hist_rows),
            }

        live_rates = [
            {
                "symbol": r["symbol"],
                "rate_percent": float(r["funding_rate_pct"] or 0),
                "funding_interval_hours": int(r["funding_interval"] or 8),
                "volume_24h_usd": float(r["volume_24h"] or 0),
                "price_24h_pcnt": float(r["price_24h_pcnt"] or 0),
            }
            for r in rates
        ]

        result = await analyze_market_for_bot_config(capital, leverage, exchange, historical_stats, live_rates)
        ai_justification = result.pop("ai_justification", "")
        return {"success": True, "config": result, "ai_justification": ai_justification}

    except HTTPException:
        raise
    except Exception as e:
        status = 400 if "Capital" in str(e) or "Alavancagem" in str(e) else 500
        raise HTTPException(status_code=status, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# HISTÃ“RICO DE ALTERAÃ‡Ã•ES DE CONFIG PELA IA
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_real_router.get("/real-trading/{session_id}/ai-config-history")
async def get_ai_config_history(
    session_id: int,
    current_user: dict = Depends(get_current_user),
):
    """HistÃ³rico de alteraÃ§Ãµes automÃ¡ticas de config pela IA, com comparaÃ§Ã£o antes/depois."""
    try:
        owner = await db.fetchrow(
            "SELECT id FROM real_config WHERE id=$1 AND user_id=$2",
            session_id, current_user["id"],
        )
        if not owner:
            raise HTTPException(status_code=404, detail="SessÃ£o nÃ£o encontrada")

        rows = await db.fetch(
            """
            SELECT id, analysis_id, trigger_type, changes_applied,
                   perf_trades_before, perf_pnl_before,
                   perf_trades_after, perf_pnl_after, perf_evaluated_at,
                   prev_history_id, created_at
            FROM bot_ai_config_history
            WHERE config_id = $1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            session_id,
        )

        data = [
            {
                "id": r["id"],
                "analysisId": r["analysis_id"],
                "triggerType": r["trigger_type"],
                "changesApplied": json.loads(r["changes_applied"]) if isinstance(r["changes_applied"], str) else r["changes_applied"],
                "perfTradesBefore": r["perf_trades_before"],
                "perfPnlBefore": r["perf_pnl_before"],
                "perfTradesAfter": r["perf_trades_after"],
                "perfPnlAfter": r["perf_pnl_after"],
                "perfEvaluatedAt": r["perf_evaluated_at"].isoformat() if r["perf_evaluated_at"] else None,
                "prevHistoryId": r["prev_history_id"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

        return {"success": True, "data": data}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROTAS PROTEGIDAS â€” ConfiguraÃ§Ãµes globais (sistema)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_settings_router.get("/settings")
async def get_system_settings(current_user: dict = Depends(get_current_user)):
    """Retorna configuraÃ§Ãµes globais do sistema (score thresholds etc.)."""
    try:
        rows = await db.fetch("SELECT key, value, description FROM system_settings")
        settings = {}
        for r in rows:
            settings[r["key"]] = {
                "value": json.loads(r["value"]) if isinstance(r["value"], str) else r["value"],
                "description": r["description"],
            }

        # Garante chaves esperadas no frontend, mesmo que nÃ£o existam no banco ainda.
        for key, meta in DEFAULT_SYSTEM_SETTINGS.items():
            if key not in settings:
                settings[key] = {
                    "value": meta["value"],
                    "description": meta["description"],
                }
        return {"success": True, "settings": settings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_settings_router.put("/settings/{key}")
async def update_system_setting(
    key: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    try:
        if "value" not in payload:
            raise HTTPException(status_code=400, detail="Campo 'value' Ã© obrigatÃ³rio")
        json_val = json.dumps(payload["value"])
        default_desc = DEFAULT_SYSTEM_SETTINGS.get(key, {}).get("description")
        await db.execute(
            """
            INSERT INTO system_settings (key, value, description, updated_at)
            VALUES ($1, $2::jsonb, $3, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                description = COALESCE(system_settings.description, EXCLUDED.description),
                updated_at = NOW()
            """,
            key, json_val, default_desc,
        )
        # Comentário de controle: reflete alteração de score instantaneamente (sem esperar TTL).
        if key.startswith("score_"):
            _invalidate_score_settings_caches()
        return {"success": True, "message": f"Configuração '{key}' atualizada com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROTAS PROTEGIDAS â€” EstratÃ©gias salvas
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_strategies_router.get("/strategies")
async def list_strategies(current_user: dict = Depends(get_current_user)):
    try:
        rows = await db.fetch(
            """
            SELECT id, name, config, created_at
            FROM saved_strategies
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            current_user["id"],
        )
        data = []
        for r in rows:
            cfg = r["config"]
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            data.append({
                "id": r["id"],
                "name": r["name"],
                "config": cfg,
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            })
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_strategies_router.post("/strategies")
async def save_strategy(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    try:
        name = (payload.get("name") or "").strip()
        config = payload.get("config")
        if not name:
            raise HTTPException(status_code=400, detail="Nome da estratÃ©gia Ã© obrigatÃ³rio")
        if not config:
            raise HTTPException(status_code=400, detail="ConfiguraÃ§Ã£o da estratÃ©gia Ã© obrigatÃ³ria")

        json_config = json.dumps(config)
        row = await db.fetchrow(
            """
            INSERT INTO saved_strategies (name, config, user_id)
            VALUES ($1, $2::jsonb, $3)
            ON CONFLICT (name) DO UPDATE
                SET config = EXCLUDED.config, created_at = NOW()
            RETURNING id, name, created_at
            """,
            name, json_config, current_user["id"],
        )
        return {
            "success": True,
            "message": f"EstratÃ©gia '{name}' salva com sucesso",
            "id": row["id"],
            "name": row["name"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_strategies_router.delete("/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    current_user: dict = Depends(get_current_user),
):
    try:
        result = await db.execute(
            "DELETE FROM saved_strategies WHERE id = $1 AND user_id = $2",
            strategy_id, current_user["id"],
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="EstratÃ©gia nÃ£o encontrada")
        return {"success": True, "message": "EstratÃ©gia deletada com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Logs do Servidor
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_logs_router.get("/server-logs")
async def get_server_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    level: str = Query(default=""),
    date_from: str = Query(default=None),
    date_to: str = Query(default=None),
    search: str = Query(default=""),
    module: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
):
    try:
        conditions: list[str] = []
        params: list = []
        idx = 1

        if level:
            conditions.append(f"level = UPPER(${idx})")
            params.append(level)
            idx += 1

        if date_from:
            conditions.append(f"created_at >= ${idx}::timestamptz")
            params.append(date_from)
            idx += 1

        if date_to:
            conditions.append(f"created_at <= ${idx}::timestamptz")
            params.append(date_to)
            idx += 1

        if search:
            conditions.append(f"(message ILIKE ${idx} OR module ILIKE ${idx})")
            params.append(f"%{search}%")
            idx += 1

        if module:
            conditions.append(f"module ILIKE ${idx}")
            params.append(f"%{module}%")
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = await db.fetch(
            f"""
            SELECT id, level, module, message, created_at
            FROM server_logs
            {where}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, offset,
        )

        total = await db.fetchval(
            f"SELECT COUNT(*) FROM server_logs {where}",
            *params,
        )

        data = [
            {
                "id": r["id"],
                "level": r["level"],
                "module": r["module"] or "server",
                "message": r["message"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

        return {"success": True, "data": data, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ADMIN: ANÃLISE PnL DB vs Binance
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_BINANCE_FAPI = "https://fapi.binance.com"
_DIVERGENCE_THRESHOLD = 0.05  # USD


def _sign_binance_params(params: dict, secret: str) -> dict:
    query = urllib.parse.urlencode(params)
    signature = hmac.new(
        secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {**params, "signature": signature}


async def _fetch_binance_income(
    client: httpx.AsyncClient,
    api_key: str,
    api_secret: str,
    symbol: str,
    income_type: str,
    start_time: int,
    end_time: int,
) -> list[dict]:
    params = {
        "symbol": symbol,
        "incomeType": income_type,
        "startTime": start_time,
        "endTime": end_time,
        "limit": 200,
        "timestamp": int(time.time() * 1000),
        "recvWindow": 10000,
    }
    params = _sign_binance_params(params, api_secret)
    try:
        resp = await client.get(
            f"{_BINANCE_FAPI}/fapi/v1/income",
            params=params,
            headers={"X-MBX-APIKEY": api_key},
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def _brt_str_to_ms(value: str | None) -> int | None:
    from datetime import datetime, timezone, timedelta
    if not value:
        return None
    brt = timezone(timedelta(hours=-3))
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%y %H:%M:%S"):
        try:
            dt = datetime.strptime(str(value).strip(), fmt).replace(tzinfo=brt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return None


@_admin_router.get("/admin/analise-pnl")
async def admin_analise_pnl(
    limit: int = Query(default=500, ge=1, le=2000),
    only_divergent: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    """Analisa PnL de todos os real_trades da Binance comparando com a API real."""
    rows = await db.fetch(
        """
        SELECT
            rt.id,
            rt.config_id,
            rc.user_id,
            rt.symbol,
            rt.direction,
            COALESCE(rt.funding_pnl, 0)::float    AS funding_pnl,
            COALESCE(rt.price_pnl, 0)::float      AS price_pnl,
            COALESCE(rt.price_pnl_pct, 0)::float  AS price_pnl_pct,
            COALESCE(rt.fee_cost, 0)::float        AS fee_cost,
            COALESCE(rt.total_pnl, 0)::float       AS total_pnl,
            COALESCE(rt.total_pnl_pct, 0)::float   AS total_pnl_pct,
            rt.open_time,
            rt.close_time,
            rt.trade_timestamp,
            rt.close_reason,
            rt.reconciled_at
        FROM real_trades rt
        JOIN real_config rc ON rc.id = rt.config_id
        WHERE rt.exchange = 'binance'
        ORDER BY rt.trade_timestamp ASC
        LIMIT $1
        """,
        limit,
    )

    if not rows:
        return {"success": True, "trades": [], "summary": {
            "total_analyzed": 0, "with_divergence": 0,
            "sum_delta_total": 0.0, "divergence_threshold": _DIVERGENCE_THRESHOLD,
        }}

    unique_uids = list({r["user_id"] for r in rows})
    key_rows = await db.fetch(
        "SELECT user_id, value FROM user_settings WHERE key = 'api_keys_binance' AND user_id = ANY($1::int[])",
        unique_uids,
    )
    keys_by_user: dict[int, dict] = {}
    for kr in key_rows:
        val = kr["value"]
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                continue
        if isinstance(val, dict) and val.get("apiKey") and val.get("apiSecret"):
            keys_by_user[int(kr["user_id"])] = val

    results = []
    total_divergent = 0
    sum_delta_total = 0.0
    skipped_no_keys = 0
    skipped_api_error = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        for row in rows:
            uid = int(row["user_id"])
            keys = keys_by_user.get(uid)
            if not keys:
                skipped_no_keys += 1
                if not only_divergent:
                    results.append({
                        "trade_id": row["id"],
                        "symbol": row["symbol"],
                        "direction": row["direction"],
                        "open_time": row["open_time"],
                        "close_time": row["close_time"],
                        "error": f"Sem chaves API para user_id={uid}",
                    })
                continue

            api_key = keys["apiKey"]
            api_secret = keys["apiSecret"]
            close_ts = int(row["trade_timestamp"])
            price_start = close_ts - 60_000
            price_end = close_ts + 300_000

            try:
                pnl_recs = await _fetch_binance_income(
                    client, api_key, api_secret,
                    symbol=row["symbol"], income_type="REALIZED_PNL",
                    start_time=price_start, end_time=price_end,
                )
                comm_recs = await _fetch_binance_income(
                    client, api_key, api_secret,
                    symbol=row["symbol"], income_type="COMMISSION",
                    start_time=price_start, end_time=price_end,
                )
                open_ts_ms = _brt_str_to_ms(row["open_time"])
                close_ts_ms = _brt_str_to_ms(row["close_time"])
                funding_start = (open_ts_ms - 1_000) if open_ts_ms else (close_ts - 3_600_000)
                funding_end = (close_ts_ms + 300_000) if close_ts_ms else (close_ts + 300_000)
                fund_recs = await _fetch_binance_income(
                    client, api_key, api_secret,
                    symbol=row["symbol"], income_type="FUNDING_FEE",
                    start_time=funding_start, end_time=funding_end,
                )
            except Exception as exc:
                skipped_api_error += 1
                if not only_divergent:
                    results.append({
                        "trade_id": row["id"],
                        "symbol": row["symbol"],
                        "direction": row["direction"],
                        "open_time": row["open_time"],
                        "close_time": row["close_time"],
                        "error": str(exc),
                    })
                continue

            realized_pnl = sum(float(r.get("income", 0)) for r in pnl_recs)
            commission = sum(float(r.get("income", 0)) for r in comm_recs)
            funding_fee = sum(float(r.get("income", 0)) for r in fund_recs)
            binance_fee_abs = abs(commission)
            binance_total = realized_pnl - binance_fee_abs + funding_fee

            db_price_pnl = float(row["price_pnl"])
            db_fee = abs(float(row["fee_cost"]))
            db_funding = float(row["funding_pnl"])
            db_total = float(row["total_pnl"])

            delta_price = realized_pnl - db_price_pnl
            delta_fee = binance_fee_abs - db_fee
            delta_funding = funding_fee - db_funding
            delta_total = binance_total - db_total

            has_divergence = abs(delta_total) > _DIVERGENCE_THRESHOLD
            if has_divergence:
                total_divergent += 1
            sum_delta_total += delta_total

            if only_divergent and not has_divergence:
                continue

            results.append({
                "trade_id": row["id"],
                "symbol": row["symbol"],
                "direction": row["direction"],
                "open_time": row["open_time"],
                "close_time": row["close_time"],
                "reconciled": row["reconciled_at"] is not None,
                "close_reason": row["close_reason"],
                "db": {
                    "price_pnl": round(db_price_pnl, 6),
                    "fee_cost": round(db_fee, 6),
                    "funding_pnl": round(db_funding, 6),
                    "total_pnl": round(db_total, 6),
                },
                "binance": {
                    "realized_pnl": round(realized_pnl, 6),
                    "commission": round(binance_fee_abs, 6),
                    "funding_fee": round(funding_fee, 6),
                    "total": round(binance_total, 6),
                },
                "delta": {
                    "price_pnl": round(delta_price, 6),
                    "fee_cost": round(delta_fee, 6),
                    "funding_pnl": round(delta_funding, 6),
                    "total_pnl": round(delta_total, 6),
                },
                "has_divergence": has_divergence,
            })

    return {
        "success": True,
        "trades": results,
        "summary": {
            "total_analyzed": len(rows),
            "returned": len(results),
            "with_divergence": total_divergent,
            "skipped_no_keys": skipped_no_keys,
            "skipped_api_error": skipped_api_error,
            "sum_delta_total": round(sum_delta_total, 6),
            "divergence_threshold": _DIVERGENCE_THRESHOLD,
        },
    }


@_admin_router.post("/admin/fix-funding-pnl")
async def admin_fix_funding_pnl(
    dry_run: bool = Query(default=True),
    current_user: dict = Depends(get_current_user),
):
    """Corrige funding_pnl, total_pnl e balance_after dos real_trades da Binance com base nos dados reais da API."""
    rows = await db.fetch(
        """
        SELECT rt.id, rt.config_id, rc.user_id, rt.symbol,
               COALESCE(rt.funding_pnl, 0)::float    AS funding_pnl,
               COALESCE(rt.price_pnl, 0)::float      AS price_pnl,
               COALESCE(rt.price_pnl_pct, 0)::float  AS price_pnl_pct,
               COALESCE(rt.fee_cost, 0)::float        AS fee_cost,
               COALESCE(rt.total_pnl, 0)::float       AS total_pnl,
               COALESCE(rt.total_pnl_pct, 0)::float   AS total_pnl_pct,
               rt.open_time, rt.close_time, rt.trade_timestamp,
               rc.leverage, rc.capital::float
        FROM real_trades rt
        JOIN real_config rc ON rc.id = rt.config_id
        WHERE rt.exchange = 'binance'
        ORDER BY rt.config_id, rt.trade_timestamp ASC
        """
    )

    if not rows:
        return {"success": True, "dry_run": dry_run, "total_trades": 0,
                "fixes_count": 0, "applied": 0, "sum_delta": 0.0, "fixes": []}

    # Carrega chaves API por usuÃ¡rio
    unique_uids = list({int(r["user_id"]) for r in rows})
    key_rows = await db.fetch(
        "SELECT user_id, value FROM user_settings WHERE key = 'api_keys_binance' AND user_id = ANY($1::int[])",
        unique_uids,
    )
    keys_by_user: dict[int, dict] = {}
    for kr in key_rows:
        val = kr["value"]
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                continue
        if isinstance(val, dict) and val.get("apiKey") and val.get("apiSecret"):
            keys_by_user[int(kr["user_id"])] = val

    fixes = []
    sum_delta = 0.0

    async with httpx.AsyncClient(timeout=15.0) as client:
        for row in rows:
            uid = int(row["user_id"])
            keys = keys_by_user.get(uid)
            if not keys:
                continue

            api_key = keys["apiKey"]
            api_secret = keys["apiSecret"]
            close_ts = int(row["trade_timestamp"])
            open_ts_ms = _brt_str_to_ms(row["open_time"])
            close_ts_ms = _brt_str_to_ms(row["close_time"])
            funding_start = (open_ts_ms - 1_000) if open_ts_ms else (close_ts - 3_600_000)
            funding_end = (close_ts_ms + 300_000) if close_ts_ms else (close_ts + 300_000)

            try:
                fund_recs = await _fetch_binance_income(
                    client, api_key, api_secret,
                    symbol=row["symbol"], income_type="FUNDING_FEE",
                    start_time=funding_start, end_time=funding_end,
                )
            except Exception:
                continue

            real_funding = sum(float(r.get("income", 0)) for r in fund_recs)
            db_funding = float(row["funding_pnl"])
            delta = real_funding - db_funding

            if abs(delta) <= 0.0001:
                continue

            db_price_pnl = float(row["price_pnl"])
            old_price_pnl_pct = float(row["price_pnl_pct"])
            fee_cost = float(row["fee_cost"])
            old_total = float(row["total_pnl"])
            new_total = db_price_pnl + real_funding - fee_cost

            # Recalcula total_pnl_pct usando margem derivada do price_pnl_pct
            if abs(old_price_pnl_pct) > 0.000001 and abs(db_price_pnl) > 0.000001:
                margin = (db_price_pnl / old_price_pnl_pct) * 100
            else:
                margin = 0
            new_total_pct = (new_total / margin) * 100 if margin > 0 else float(row["total_pnl_pct"])

            sum_delta += delta
            fixes.append({
                "trade_id": row["id"],
                "config_id": row["config_id"],
                "symbol": row["symbol"],
                "open_time": row["open_time"],
                "db_funding": round(db_funding, 6),
                "real_funding": round(real_funding, 6),
                "delta": round(delta, 6),
                "old_total": round(old_total, 6),
                "new_total": round(new_total, 6),
                "new_total_pct": round(new_total_pct, 6),
                "new_funding_pnl": round(real_funding, 6),
                "trade_timestamp": row["trade_timestamp"],
                "capital": float(row["capital"]),
            })

    applied = 0
    if not dry_run and fixes:
        # Aplica correÃ§Ãµes nos trades
        for fix in fixes:
            await db.execute(
                """
                UPDATE real_trades
                SET funding_pnl = $1,
                    total_pnl   = $2,
                    total_pnl_pct = $3
                WHERE id = $4
                """,
                fix["new_funding_pnl"],
                fix["new_total"],
                fix["new_total_pct"],
                fix["trade_id"],
            )
            applied += 1

        # Recalcula balance_after em cascata por config_id
        config_ids = list({f["config_id"] for f in fixes})
        for cid in config_ids:
            # Busca capital inicial do config
            cfg_row = await db.fetchrow(
                "SELECT capital::float FROM real_config WHERE id = $1", cid
            )
            if not cfg_row:
                continue
            start_balance = float(cfg_row["capital"])

            # Busca todos os trades do config em ordem cronolÃ³gica
            trade_rows = await db.fetch(
                """
                SELECT id, COALESCE(total_pnl, 0)::float AS total_pnl
                FROM real_trades
                WHERE config_id = $1
                ORDER BY trade_timestamp ASC
                """,
                cid,
            )

            balance = start_balance
            for tr in trade_rows:
                balance += float(tr["total_pnl"])
                await db.execute(
                    "UPDATE real_trades SET balance_after = $1 WHERE id = $2",
                    round(balance, 8),
                    tr["id"],
                )

            # Atualiza balance final no config
            await db.execute(
                "UPDATE real_config SET balance = $1 WHERE id = $2",
                round(balance, 8),
                cid,
            )

    # Monta retorno sem campos internos de processamento
    fixes_out = [
        {
            "trade_id": f["trade_id"],
            "symbol": f["symbol"],
            "open_time": f["open_time"],
            "db_funding": f["db_funding"],
            "real_funding": f["real_funding"],
            "delta": f["delta"],
            "old_total": f["old_total"],
            "new_total": f["new_total"],
        }
        for f in fixes
    ]

    return {
        "success": True,
        "dry_run": dry_run,
        "total_trades": len(rows),
        "fixes_count": len(fixes),
        "applied": applied if not dry_run else 0,
        "sum_delta": round(sum_delta, 6),
        "fixes": fixes_out,
    }


# Inclui todos os sub-routers no router principal
router.include_router(_market_router)
router.include_router(_real_router)
router.include_router(_ai_router)
router.include_router(_settings_router)
router.include_router(_strategies_router)
router.include_router(_logs_router)
router.include_router(_admin_router)
