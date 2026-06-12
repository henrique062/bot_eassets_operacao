import os
import asyncpg
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def run():
    pool = await asyncpg.create_pool(os.getenv('DATABASE_URL'))
    async with pool.acquire() as c:
        rows = await c.fetch("SELECT id, session_name, symbols, exchange, operation_mode, auto_direction, active FROM real_config WHERE active=true OR session_name LIKE '%contrario%' OR session_name LIKE '%Bot Binance%'")
        for r in rows:
            print(dict(r))
    await pool.close()

asyncio.run(run())
