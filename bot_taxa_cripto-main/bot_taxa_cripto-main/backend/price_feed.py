"""
Price Feed via WebSocket — Binance Futures e Bybit Linear.

Mantém conexões WebSocket persistentes para receber mark prices em tempo real.
Reconecta automaticamente em caso de erro.

API pública:
    get_price(exchange, symbol) -> float | None
    ensure_running(exchange, symbols) -> None
"""

import asyncio
import json

import websockets

# Armazena preços com chave "exchange:SYMBOL"
_prices: dict[str, float] = {}

# Tasks asyncio rodando por exchange
_ws_tasks: dict[str, asyncio.Task] = {}

# Símbolos já subscritos no Bybit
_bybit_subscribed: set[str] = set()

# Referência ao websocket ativo do Bybit (para adicionar subscriptions)
_bybit_ws = None


def get_price(exchange: str, symbol: str) -> float | None:
    """
    Retorna o preço mais recente do símbolo ou None se ainda não disponível.

    Args:
        exchange: "binance" ou "bybit"
        symbol: símbolo no formato "BTCUSDT"

    Returns:
        Preço como float ou None se ainda não recebido.
    """
    return _prices.get(f"{exchange.lower()}:{symbol.upper()}")


async def ensure_running(exchange: str, symbols: list[str] | None = None) -> None:
    """
    Garante que o feed WebSocket está rodando para a exchange.
    Para Bybit, também subscreve nos symbols fornecidos se ainda não estiverem.

    Args:
        exchange: "binance" ou "bybit"
        symbols: lista de símbolos para subscrever (apenas relevante para Bybit)
    """
    exch = exchange.lower()

    # Inicia a task se ainda não está rodando ou foi cancelada/finalizada
    if exch not in _ws_tasks or _ws_tasks[exch].done():
        if exch == "binance":
            _ws_tasks[exch] = asyncio.create_task(_binance_feed())
        elif exch == "bybit":
            _ws_tasks[exch] = asyncio.create_task(_bybit_feed())

    # Para Bybit, subscreve símbolos novos dinamicamente
    if exch == "bybit" and symbols:
        await _bybit_subscribe(symbols)


async def _bybit_subscribe(symbols: list[str]) -> None:
    """Subscreve símbolos no Bybit via websocket ativo, se disponível."""
    global _bybit_ws, _bybit_subscribed

    new_symbols = [s.upper() for s in symbols if s.upper() not in _bybit_subscribed]
    if not new_symbols:
        return

    if _bybit_ws is not None:
        try:
            args = [f"tickers.{s}" for s in new_symbols]
            msg = json.dumps({"op": "subscribe", "args": args})
            await _bybit_ws.send(msg)
            _bybit_subscribed.update(new_symbols)
        except Exception as e:
            print(f"[PriceFeed] Bybit subscribe erro: {e}")
    else:
        # WS ainda não conectou — registra para subscrever quando conectar
        _bybit_subscribed.update(new_symbols)


async def _binance_feed() -> None:
    """
    Coroutine persistente que mantém conexão WebSocket com Binance Futures.
    Recebe mark prices de TODOS os símbolos a cada 1 segundo.
    Reconecta automaticamente em caso de erro.
    """
    url = "wss://fstream.binance.com/ws/!markPrice@arr@1s"
    while True:
        try:
            async with websockets.connect(url) as ws:
                print("[PriceFeed] Binance WS conectado")
                async for msg in ws:
                    data = json.loads(msg)
                    if isinstance(data, list):
                        for item in data:
                            s = item.get("s", "")
                            p_raw = item.get("p", 0)
                            try:
                                p = float(p_raw or 0)
                            except (ValueError, TypeError):
                                p = 0.0
                            if s and p:
                                _prices[f"binance:{s}"] = p
        except Exception as e:
            print(f"[PriceFeed] Binance WS erro: {e}, reconectando em 3s...")
            await asyncio.sleep(3)


async def _bybit_feed() -> None:
    """
    Coroutine persistente que mantém conexão WebSocket com Bybit Linear.
    Subscreve nos símbolos registrados em _bybit_subscribed.
    Reconecta automaticamente em caso de erro, resubscrevendo todos os símbolos.
    """
    global _bybit_ws, _bybit_subscribed

    url = "wss://stream.bybit.com/v5/public/linear"
    while True:
        try:
            async with websockets.connect(url) as ws:
                _bybit_ws = ws
                print("[PriceFeed] Bybit WS conectado")

                # Subscreve nos símbolos já registrados (incluindo os adicionados antes da conexão)
                if _bybit_subscribed:
                    args = [f"tickers.{s}" for s in _bybit_subscribed]
                    await ws.send(json.dumps({"op": "subscribe", "args": args}))

                async for msg in ws:
                    data = json.loads(msg)
                    topic = data.get("topic", "")
                    if topic.startswith("tickers."):
                        ticker_data = data.get("data", {})
                        symbol = ticker_data.get("symbol", "")
                        price_raw = ticker_data.get("lastPrice")
                        if symbol and price_raw is not None:
                            try:
                                price = float(price_raw)
                                if price:
                                    _prices[f"bybit:{symbol}"] = price
                            except (ValueError, TypeError):
                                pass

        except Exception as e:
            print(f"[PriceFeed] Bybit WS erro: {e}, reconectando em 3s...")
        finally:
            _bybit_ws = None
            await asyncio.sleep(3)
