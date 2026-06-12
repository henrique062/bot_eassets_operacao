"""
AsyncPG connection pool — singleton with lifespan helpers.

Usage:
    await init_db()         # on startup
    pool = get_pool()       # anywhere after init
    await close_db()        # on shutdown
"""

from __future__ import annotations

import asyncpg
from loguru import logger

from config import DATABASE_URL

_pool: asyncpg.Pool | None = None

MIGRATIONS_DIR = "db/migrations"


def get_pool() -> asyncpg.Pool:
    """Return the active connection pool.

    Raises RuntimeError if called before init_db().
    """
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_db() first.")
    return _pool


async def init_db() -> None:
    """Create the asyncpg pool and run SQL migrations."""
    global _pool

    logger.info("Connecting to PostgreSQL...")
    _pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=60,
    )
    logger.info("PostgreSQL pool created.")

    await _run_migrations()


async def _run_migrations() -> None:
    """Execute all .sql migration files in order."""
    import glob
    import os

    pattern = os.path.join(MIGRATIONS_DIR, "*.sql")
    sql_files = sorted(glob.glob(pattern))

    if not sql_files:
        logger.warning("No SQL migration files found at {}", MIGRATIONS_DIR)
        return

    pool = get_pool()
    async with pool.acquire() as conn:
        for path in sql_files:
            logger.info("Running migration: {}", path)
            with open(path, encoding="utf-8") as f:
                sql = f.read()
            try:
                await conn.execute(sql)
                logger.info("Migration OK: {}", path)
            except Exception as exc:
                logger.error("Migration failed: {} — {}", path, exc)
                raise


async def close_db() -> None:
    """Close the connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed.")
