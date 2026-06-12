import asyncio
from database import db

async def migrate():
    await db.connect()
    with open('migrations/20260221_add_target_take_profit_pct.sql', 'r') as f:
        sql = f.read()
    await db.execute(sql)
    print("Migration executed successfully")
    await db.close()

if __name__ == '__main__':
    asyncio.run(migrate())
