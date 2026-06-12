import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def m():
    c = await asyncpg.connect(os.getenv('DATABASE_URL'))
    cols = await c.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='real_config'")
    print("=== real_config ===")
    for col in cols: print(f"  {col['column_name']}: {col['data_type']}")
    print("\n=== system_settings ===")
    cols2 = await c.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='system_settings'")
    for col in cols2: print(f"  {col['column_name']}: {col['data_type']}")
    await c.close()

asyncio.run(m())
