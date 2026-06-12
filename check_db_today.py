import asyncio
import os
import sys

sys.path.append(r'd:\3 - Projetos investimentos\bot_taxa_cripto\backend')
from database import init_db, fetch

async def main():
    await init_db()
    
    for tbl in ["paper_trades", "real_trades"]:
        print(f"\n--- ÚLTIMAS 5 TRADES EM {tbl} ---")
        try:
            trades = await fetch(f"SELECT * FROM {tbl} ORDER BY id DESC LIMIT 5")
            for t in trades:
                d = dict(t)
                print(f"Data: {d.get('opened_at', d.get('created_at', 'N/A'))} | {d.get('symbol')} | {d.get('direction')} | Status: {d.get('status')} | Mode: {d.get('mode', 'N/A')}")
                
                # Exibir razões para validação das palavras
                for k, v in d.items():
                    if 'reason' in k.lower():
                        print(f"  {k}: {v}")
                print("-" * 40)
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
