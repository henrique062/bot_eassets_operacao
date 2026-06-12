import asyncio
import database as db

async def check():
    await db.init_db()
    
    # Paper trades
    res1 = await db.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'paper_trades';")
    print("PAPER TRADES:")
    for r in res1:
        print(f"  {r['column_name']}: {r['data_type']}")
        
    # Real trades
    res2 = await db.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'real_trades';")
    print("\nREAL TRADES:")
    for r in res2:
        print(f"  {r['column_name']}: {r['data_type']}")
        
    await db.close_db()

if __name__ == '__main__':
    asyncio.run(check())
