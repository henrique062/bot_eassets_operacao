import asyncio
import asyncpg
import json

async def main():
    conn = await asyncpg.connect("postgres://vorxia:91318244@69.62.92.189:5432/vorxia?sslmode=disable")
    
    row = await conn.fetchrow("SELECT target_take_profit_pct, min_profit_pct, stop_loss_pct FROM real_config WHERE id=45")
    print(dict(row))
            
    await conn.close()
    print("DONE CONFIG LOGS")

if __name__ == "__main__":
    asyncio.run(main())
