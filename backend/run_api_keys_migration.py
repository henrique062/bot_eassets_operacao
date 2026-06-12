import asyncio
import database as db

async def run_migration():
    await db.init_db()
    with open('../migrations/20260221_add_api_keys.sql', 'r', encoding='utf-8') as f:
        sql = f.read()

    pool = db._get_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql)
    
    print("Migration para API Keys aplicada com sucesso!")
    await db.close_db()

asyncio.run(run_migration())
