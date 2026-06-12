import asyncio
import database as db

async def show_bots():
    await db.init_db()
    rows = await db.fetch("SELECT id, session_name, symbols, exchange, operation_mode, auto_direction, active FROM real_config WHERE active=true")
    for r in rows:
        print(dict(r))
    await db.close_db()

asyncio.run(show_bots())
