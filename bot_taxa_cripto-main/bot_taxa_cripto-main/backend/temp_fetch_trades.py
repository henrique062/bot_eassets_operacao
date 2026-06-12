import asyncio
import json
from database import init_db, fetch, close_db
from decimal import Decimal
from datetime import datetime, date

async def main():
    await init_db()
    try:
        # Busca os ultimos 10 trades usando ID
        rows = await fetch("SELECT * FROM paper_trades ORDER BY id DESC LIMIT 10")
        trades = []
        for r in rows:
            trades.append(dict(r))
        
        # Converter datetime e decimal para json.dumps funcionar
        for t in trades:
            for k, v in t.items():
                if isinstance(v, (datetime, date)):
                    t[k] = v.isoformat()
                elif isinstance(v, Decimal):
                    t[k] = float(v)
        
        print(json.dumps(trades, indent=2))
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
