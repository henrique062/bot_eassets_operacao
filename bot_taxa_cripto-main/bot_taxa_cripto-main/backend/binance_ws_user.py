"""
Gerencia User Data Streams da Binance USDS-M Futures por user_id.

Cada usuário com bot real ativo mantém uma conexão WS independente.
O evento ORDER_TRADE_UPDATE dispara imediatamente quando uma ordem TP limit
é preenchida na exchange, eliminando o polling fetch_order() de 1s.

Arquitetura:
  - Uma conexão WS por user_id (compartilhada entre todos os bots do mesmo usuário)
  - listenKey renovado a cada 30min (expira em 60min)
  - Reconexão automática em caso de queda
  - Callbacks registrados por order_id (asyncio.Event)
"""

import asyncio
import json
import time

import aiohttp

_connections: dict[int, "UserDataManager"] = {}  # user_id → manager
_creation_lock = asyncio.Lock()  # previne race condition em get_or_create concorrente

_FAPI_BASE = "https://fapi.binance.com"


class UserDataManager:
    def __init__(self, user_id: int, api_key: str):
        self.user_id = user_id
        self.api_key = api_key
        self.listen_key: str | None = None
        # order_id → asyncio.Event disparado quando FILLED
        self.callbacks: dict[str, asyncio.Event] = {}
        # order_id → preço de preenchimento (average fill price)
        self.fill_prices: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.listen_key = await self._get_listen_key()
        self._task = asyncio.create_task(self._ws_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        print(f"[UserDataWS] user_id={self.user_id} iniciado (listenKey={self.listen_key[:8]}...)")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        await self._delete_listen_key()
        print(f"[UserDataWS] user_id={self.user_id} encerrado")

    def register_tp(self, order_id: str) -> asyncio.Event:
        """Registra um callback para quando a ordem order_id for FILLED."""
        event = asyncio.Event()
        self.callbacks[order_id] = event
        return event

    def unregister_tp(self, order_id: str) -> None:
        """Remove o callback após a posição ser fechada."""
        self.callbacks.pop(order_id, None)
        self.fill_prices.pop(order_id, None)

    def get_fill_price(self, order_id: str) -> float | None:
        """Retorna o preço de preenchimento recebido via WS, ou None."""
        return self.fill_prices.get(order_id)

    async def _get_listen_key(self) -> str:
        async with aiohttp.ClientSession() as s:
            resp = await s.post(
                f"{_FAPI_BASE}/fapi/v1/listenKey",
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=aiohttp.ClientTimeout(total=10),
            )
            resp.raise_for_status()
            data = await resp.json()
            return data["listenKey"]

    async def _keepalive_loop(self) -> None:
        """Renova o listenKey a cada 30 minutos (expira em 60min)."""
        while True:
            await asyncio.sleep(1800)  # 30 minutos
            try:
                async with aiohttp.ClientSession() as s:
                    resp = await s.put(
                        f"{_FAPI_BASE}/fapi/v1/listenKey",
                        headers={"X-MBX-APIKEY": self.api_key},
                        timeout=aiohttp.ClientTimeout(total=10),
                    )
                    if resp.status >= 400:
                        # listenKey expirou ou inválido — forçar reconexão com nova chave
                        print(f"[UserDataWS] user_id={self.user_id} keepalive retornou HTTP {resp.status} — forçando reconexão")
                        if self._task and not self._task.done():
                            self._task.cancel()
            except Exception as e:
                print(f"[UserDataWS] user_id={self.user_id} keepalive falhou: {e}")

    async def _delete_listen_key(self) -> None:
        if not self.listen_key:
            return
        try:
            async with aiohttp.ClientSession() as s:
                await s.delete(
                    f"{_FAPI_BASE}/fapi/v1/listenKey",
                    headers={"X-MBX-APIKEY": self.api_key},
                    params={"listenKey": self.listen_key},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            pass

    async def _ws_loop(self) -> None:
        """Loop de conexão WS com reconexão automática e renovação de listenKey."""
        while True:
            try:
                uri = f"wss://fstream.binance.com/ws/{self.listen_key}"
                async with aiohttp.ClientSession() as s:
                    async with s.ws_connect(uri, heartbeat=20, timeout=aiohttp.ClientTimeout(total=30)) as ws:
                        print(f"[UserDataWS] user_id={self.user_id} conectado")
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    self._handle_event(data)
                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[UserDataWS] user_id={self.user_id} desconectado: {e}. Reconectando em 5s...")

            await asyncio.sleep(5)
            # Limpar fill_prices acumulados de ordens anteriores (dados stale de antes da queda).
            # Os callbacks (asyncio.Event) são mantidos — monitors ativos ainda os referenciam
            # e o check periódico REST (60s) detectará cancelamentos/preenchimentos perdidos.
            stale_count = len(self.fill_prices)
            self.fill_prices.clear()
            if stale_count:
                print(f"[UserDataWS] user_id={self.user_id} reconectando — {stale_count} fill_price(s) stale limpos, {len(self.callbacks)} callback(s) ativo(s) mantidos")
            # Obter novo listenKey após reconexão (o antigo pode ter expirado)
            try:
                self.listen_key = await self._get_listen_key()
            except Exception as e:
                print(f"[UserDataWS] user_id={self.user_id} erro ao renovar listenKey: {e}")

    def _handle_event(self, data: dict) -> None:
        """Processa eventos do User Data Stream."""
        event_type = data.get("e")

        if event_type == "ORDER_TRADE_UPDATE":
            order = data.get("o", {})
            order_id = str(order.get("i", ""))  # orderId (int na API, convertemos para str)
            status = order.get("X", "")          # NEW, PARTIALLY_FILLED, FILLED, CANCELED...

            if status == "FILLED" and order_id in self.callbacks:
                # L = último preço de execução, ap = preço médio de execução
                fill_price = float(order.get("L") or order.get("ap") or 0)
                self.fill_prices[order_id] = fill_price
                self.callbacks[order_id].set()
                print(f"[UserDataWS] user_id={self.user_id} TP order={order_id} preenchida @ {fill_price}")


# ──────────────────────────────────────────────────────────────────────────────
# API pública do módulo
# ──────────────────────────────────────────────────────────────────────────────

async def get_or_create(user_id: int, api_key: str) -> UserDataManager:
    """Retorna (ou cria) o manager de User Data Stream para o user_id."""
    if user_id in _connections:
        return _connections[user_id]
    async with _creation_lock:
        # Re-checar dentro do lock para evitar double-create por coroutines concorrentes
        if user_id not in _connections:
            mgr = UserDataManager(user_id, api_key)
            await mgr.start()
            _connections[user_id] = mgr
    return _connections[user_id]


async def release_if_no_sessions(user_id: int, remaining_config_ids: list[int]) -> None:
    """
    Fecha a conexão WS do user_id se não há mais bots ativos.
    Deve ser chamado após stop_trading().
    """
    if not remaining_config_ids and user_id in _connections:
        await _connections[user_id].stop()
        del _connections[user_id]
