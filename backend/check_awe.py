import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def check():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    
    cfgs = await conn.fetch("SELECT id, session_name, active FROM real_config WHERE active=true ORDER BY id")
    print("BOTS ATIVOS:")
    for c in cfgs:
        print(f"  #{c['id']} {c['session_name']}")
    
    positions = await conn.fetch("SELECT config_id, symbol, direction FROM real_positions ORDER BY id")
    print(f"\nPOSICOES ({len(positions)}):")
    for p in positions:
        cfg = await conn.fetchrow("SELECT active, session_name FROM real_config WHERE id=$1", p['config_id'])
        st = "ATIVO" if cfg and cfg['active'] else "INATIVO"
        print(f"  Bot #{p['config_id']} ({cfg['session_name']}) [{st}] -> {p['symbol']} {p['direction']}")
    
    # Ultimo log de trailing
    tlog = await conn.fetchrow("SELECT event, symbol, message, created_at FROM real_order_logs WHERE symbol='AWEUSDT' AND event='trailing_armed' ORDER BY created_at DESC LIMIT 1")
    if tlog:
        print(f"\nTRAILING AWE: {tlog['created_at']} | {tlog['message']}")
    
    await conn.close()

asyncio.run(check())
