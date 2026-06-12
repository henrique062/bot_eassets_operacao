import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    db_url = os.getenv("DATABASE_URL", "postgres://vorxia:91318244@69.62.92.189:5432/vorxia?sslmode=disable")
    print(f"Connecting to {db_url}...")
    try:
        conn = await asyncpg.connect(db_url)
        print("Connected!")
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        for t in tables:
            print(f"\nTable: {t['table_name']}")
            columns = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = $1", t['table_name'])
            for c in columns:
                print(f"  - {c['column_name']}: {c['data_type']}")
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
