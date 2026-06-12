import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def migrate():
    db_url = os.getenv("DATABASE_URL", "postgres://vorxia:91318244@69.62.92.189:5432/vorxia?sslmode=disable")
    print(f"Connecting to {db_url}...")
    try:
        conn = await asyncpg.connect(db_url)
        with open('backend/migrations/20260221_add_target_take_profit_pct.sql', 'r') as f:
            sql = f.read()
        await conn.execute(sql)
        print("Migration executed successfully")
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
