import asyncio
import asyncpg
import os

async def main():
    conn = await asyncpg.connect("postgres://vorxia:91318244@69.62.92.189:5432/vorxia?sslmode=disable")
    print("Executing ALTER TABLE paper_trades...")
    await conn.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS price_pnl_pct NUMERIC(18, 6) NOT NULL DEFAULT 0")
    print("Executing ALTER TABLE real_trades...")
    await conn.execute("ALTER TABLE real_trades ADD COLUMN IF NOT EXISTS price_pnl_pct NUMERIC(18, 6) NOT NULL DEFAULT 0")
    print("Done")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
