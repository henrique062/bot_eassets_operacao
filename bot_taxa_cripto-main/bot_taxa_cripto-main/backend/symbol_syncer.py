"""
Serviço de background para manter uma lista atualizada de símbolos de
futuros perpétuos da Binance e Bybit, filtrando lixos e paridades cruzadas.
"""

import asyncio
import httpx
import database as db

# In-memory fast cache
_valid_symbols = {
    "binance": set(),
    "bybit": set()
}

def is_valid_symbol(exchange: str, symbol: str) -> bool:
    """Verifica se um símbolo existe e é válido na corretora informada."""
    # Se o cache estiver vazio (ex: boot inicial), libera todos para não quebrar a UI
    if not _valid_symbols[exchange]:
        return True
    return symbol in _valid_symbols[exchange]

async def fetch_binance_symbols() -> set[str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://fapi.binance.com/fapi/v1/exchangeInfo")
        resp.raise_for_status()
        data = resp.json()
        symbols = set()
        for s in data.get("symbols", []):
            if s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL":
                symbols.add(s["symbol"])
        return symbols

async def fetch_bybit_symbols() -> set[str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://api.bybit.com/v5/market/instruments-info?category=linear")
        resp.raise_for_status()
        data = resp.json()
        symbols = set()
        for s in data.get("result", {}).get("list", []):
            if s.get("status") == "Trading":
                symbols.add(s["symbol"])
        return symbols

async def _sync_exchange(exchange: str, fetch_fn) -> bool:
    """
    Sincroniza os símbolos de uma exchange específica.
    Retorna True se bem-sucedido, False em caso de erro.
    Falha de uma exchange não interrompe a sincronização da outra.
    """
    try:
        syms = await fetch_fn()
        if syms:
            _valid_symbols[exchange] = syms
            print(f"[Symbol Syncer] {exchange}: {len(syms)} símbolos carregados.")
            return True
        print(f"[Symbol Syncer] {exchange}: resposta vazia, cache mantido.")
        return False
    except Exception as e:
        print(f"[Symbol Syncer] Erro ao sincronizar {exchange}: {e}")
        return False


async def sync_symbols_loop():
    """Roda a cada 10 minutos para atualizar a lista de moedas válidas de cada exchange.
    Cada exchange é sincronizada de forma independente: falha de uma não bloqueia a outra."""
    while True:
        await _sync_exchange("binance", fetch_binance_symbols)
        await _sync_exchange("bybit", fetch_bybit_symbols)

        # Salvar no banco as listas atualizadas
        rows = []
        for s in _valid_symbols["binance"]:
            rows.append(("binance", s, "TRADING"))
        for s in _valid_symbols["bybit"]:
            rows.append(("bybit", s, "TRADING"))

        if rows:
            try:
                await db.executemany(
                    """
                    INSERT INTO exchange_symbols (exchange, symbol, status, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (exchange, symbol) DO UPDATE SET updated_at = NOW(), status = EXCLUDED.status
                    """,
                    rows,
                )
                await db.execute(
                    """
                    UPDATE exchange_symbols
                    SET status = 'CLOSED', updated_at = NOW()
                    WHERE updated_at < NOW() - INTERVAL '30 minutes'
                    """
                )
            except Exception as e:
                print(f"[Symbol Syncer] Erro ao persistir no banco: {e}")

        await asyncio.sleep(600)  # Aguardar 10 minutos
