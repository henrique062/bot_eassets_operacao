import asyncio
import asyncpg
import os

async def main():
    db_url = os.getenv("DATABASE_URL", "postgres://vorxia:91318244@69.62.92.189:5432/vorxia?sslmode=disable")
    conn = await asyncpg.connect(db_url)
    rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='paper_config'")
    for r in rows:
        print(r[0])
    await conn.close()

asyncio.run(main())
