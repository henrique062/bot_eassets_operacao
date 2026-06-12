import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    db_url = os.getenv("DATABASE_URL")
    print(f"Connecting to {db_url}...")
    conn = await asyncpg.connect(db_url)
    try:
        with open('migrations/20260222_add_maker_timeout.sql', 'r') as f:
            sql = f.read()
        await conn.execute(sql)
        print("Migration executed successfully")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
