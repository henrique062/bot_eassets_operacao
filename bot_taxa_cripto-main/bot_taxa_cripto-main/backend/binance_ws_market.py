"""
Stream público de mark prices da Binance USDS-M Futures.
Mantém um dict em memória atualizado a cada 1s com fundingRate + nextFundingTime.
Substitui o polling REST de get_all_funding_rates() nos _monitoring_loops,
reduzindo chamadas HTTP a zero durante operação normal.

Fallback automático: se o stream estiver indisponível ou stale (>5s sem update),
as funções retornam None e o chamador volta a usar REST.
"""

import asyncio
import json
import time

import aiohttp

_mark_price_data: dict[str, dict] = {}  # symbol → dados do mark price stream
_stream_ready: bool = False
_last_update: float = 0.0


async def start_stream() -> None:
    """
    Loop de conexão ao stream público !markPrice@arr@1s da Binance.
    Deve ser iniciado como asyncio.create_task() no lifespan do FastAPI.
    Reconecta automaticamente em caso de queda.
    """
    global _stream_ready, _last_update

    uri = "wss://fstream.binance.com/ws/!markPrice@arr@1s"

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(uri, heartbeat=20, timeout=aiohttp.ClientTimeout(total=30)) as ws:
                    _stream_ready = True
                    print("[WS Market] Conectado ao stream de mark prices Binance Futures")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            now = time.time()
                            try:
                                items = json.loads(msg.data)
                                for item in items:
                                    sym = item.get("s")
                                    if sym:
                                        _mark_price_data[sym] = {
                                            "symbol": sym,
                                            "fundingRate": float(item.get("r") or 0),
                                            "fundingRatePercent": float(item.get("r") or 0) * 100,
                                            "nextFundingTime": str(item.get("T") or 0),
                                            "markPrice": float(item.get("p") or 0),
                                            # markPrice como proxy de lastPrice — diferença < 0.1%
                                            "lastPrice": float(item.get("p") or 0),
                                            "_ws_updated_at": now,
                                        }
                            except Exception:
                                pass
                            _last_update = now
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
        except Exception as e:
            _stream_ready = False
            print(f"[WS Market] Desconectado: {e}. Reconectando em 5s...")

        _stream_ready = False
        await asyncio.sleep(5)


def get_all_rates() -> list[dict] | None:
    """
    Retorna todos os dados do stream se frescos (< 5s desde último update).
    Retorna None se o stream não estiver disponível — usar fallback REST.
    """
    if not _stream_ready or (time.time() - _last_update) > 5:
        return None
    return list(_mark_price_data.values())


def get_rate(symbol: str) -> dict | None:
    """
    Retorna dados de um símbolo específico se frescos (< 5s), senão None.
    """
    data = _mark_price_data.get(symbol)
    if data and (time.time() - data.get("_ws_updated_at", 0)) < 5:
        return data
    return None


def is_ready() -> bool:
    """Retorna True se o stream está ativo e com dados frescos."""
    return _stream_ready and (time.time() - _last_update) <= 5
