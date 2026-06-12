import asyncio
import os
import asyncpg
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz

load_dotenv()
_DATABASE_URL = os.getenv("DATABASE_URL", "")

async def main():
    if not _DATABASE_URL:
        print("Error: DATABASE_URL not found in environment.")
        return
        
    conn = await asyncpg.connect(_DATABASE_URL)
    
    # Time window: Yesterday and Today GMT-3
    tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    
    # Query configurations
    configs = await conn.fetch("SELECT * FROM real_config")
    df_configs = pd.DataFrame([dict(r) for r in configs])
    
    # Query trades
    trades = await conn.fetch(f"""
        SELECT * FROM real_trades 
        WHERE created_at >= '{yesterday_start.isoformat()}' 
        ORDER BY created_at ASC
    """)
    df_trades = pd.DataFrame([dict(r) for r in trades])
    
    # Query logs
    logs = await conn.fetch(f"""
        SELECT * FROM server_logs 
        WHERE created_at >= '{yesterday_start.isoformat()}'
        ORDER BY created_at ASC
    """)
    df_logs = pd.DataFrame([dict(r) for r in logs])
    
    order_logs = await conn.fetch(f"""
        SELECT * FROM real_order_logs 
        WHERE created_at >= '{yesterday_start.isoformat()}'
        ORDER BY created_at ASC
    """)
    df_order_logs = pd.DataFrame([dict(r) for r in order_logs])
    
    print(f"Time Window: {yesterday_start} to {now}")
    print(f"Total configs: {len(df_configs)}")
    print(f"Total trades in window: {len(df_trades)}")
    print(f"Total logs in window: {len(df_logs)}")
    print(f"Total order logs in window: {len(df_order_logs)}")
    
    # Save to CSV for easier parsing by another script if needed
    if len(df_trades) > 0:
        df_trades.to_csv('trades_dump.csv', index=False)
    if len(df_configs) > 0:
        df_configs.to_csv('configs_dump.csv', index=False)
    if len(df_logs) > 0:
        df_logs.to_csv('logs_dump.csv', index=False)
    if len(df_order_logs) > 0:
        df_order_logs.to_csv('order_logs_dump.csv', index=False)
        
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())