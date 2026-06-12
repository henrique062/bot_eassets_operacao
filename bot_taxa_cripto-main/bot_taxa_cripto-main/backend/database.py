"""
Pool de conexão asyncpg para o banco PostgreSQL.
Fornece funções utilitárias de consulta utilizadas pelo paper_trader e snapshot_loop.
"""

import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool: asyncpg.Pool | None = None
_DATABASE_URL = os.getenv("DATABASE_URL", "")


async def init_db() -> None:
    """Inicializa o pool de conexões. Chamado no startup do FastAPI."""
    global _pool
    if not _DATABASE_URL:
        raise RuntimeError("DATABASE_URL não configurado no .env")
    _pool = await asyncpg.create_pool(
        dsn=_DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def close_db() -> None:
    """Fecha o pool de conexões. Chamado no shutdown do FastAPI."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool não inicializado. Chame init_db() primeiro.")
    return _pool


async def fetch(sql: str, *args) -> list[asyncpg.Record]:
    """Executa SELECT e retorna lista de registros."""
    async with _get_pool().acquire() as conn:
        return await conn.fetch(sql, *args)


async def fetchrow(sql: str, *args) -> asyncpg.Record | None:
    """Executa SELECT e retorna um único registro (ou None)."""
    async with _get_pool().acquire() as conn:
        return await conn.fetchrow(sql, *args)


async def fetchval(sql: str, *args):
    """Executa SELECT e retorna um único valor escalar."""
    async with _get_pool().acquire() as conn:
        return await conn.fetchval(sql, *args)


async def execute(sql: str, *args) -> str:
    """Executa INSERT/UPDATE/DELETE e retorna o status."""
    async with _get_pool().acquire() as conn:
        return await conn.execute(sql, *args)


async def executemany(sql: str, args_list: list) -> None:
    """Executa INSERT/UPDATE em lote."""
    async with _get_pool().acquire() as conn:
        await conn.executemany(sql, args_list)
