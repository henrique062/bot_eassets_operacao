import asyncio
from datetime import datetime
import json
import database as db

async def main():
    await db.init_db()
    
    trades = await db.fetch("SELECT id, config_id, total_pnl, balance_after, reconciled_at FROM real_trades ORDER BY id DESC LIMIT 5")
    for t in trades:
        print(f"ID: {t['id']} | Config: {t['config_id']} | PnL: {t['total_pnl']} | Balance: {t['balance_after']} | Reconciled: {t['reconciled_at']}")
        
    await db.close_db()

if __name__ == "__main__":
    asyncio.run(main())
