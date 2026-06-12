import asyncio
import aiohttp
from datetime import datetime, timezone
import database as db

async def test_webhook():
    await db.init_db()
    
    query = """
    SELECT rt.*, rc.user_id, rc.exchange, rc.leverage, rc.operation_mode, rc.id as target_config_id
    FROM real_trades rt
    JOIN real_config rc ON rt.config_id = rc.id
    WHERE rc.user_id IS NOT NULL
    ORDER BY rt.trade_timestamp DESC
    LIMIT 1
    """
    row = await db.fetchrow(query)
    
    if not row:
        print("Nenhuma trade real encontrada com user_id. Buscando qualquer trade real...")
        query_fallback = """
        SELECT rt.*, rc.user_id, rc.exchange, rc.leverage, rc.operation_mode, rc.id as target_config_id
        FROM real_trades rt
        JOIN real_config rc ON rt.config_id = rc.id
        ORDER BY rt.trade_timestamp DESC
        LIMIT 1
        """
        row = await db.fetchrow(query_fallback)
        if not row:
            print("Nenhuma trade real encontrada no banco de dados para testar.")
            await db.close_db()
            return
            
    user_id = row['user_id']
    user_info = {}
    if user_id:
        user_row = await db.fetchrow("SELECT id, email FROM users WHERE id = $1", user_id)
        if user_row:
            user_info = dict(user_row)
    else:
        # Pega qualquer usuario pra fins de teste se n tiver
        user_row = await db.fetchrow("SELECT id, email FROM users LIMIT 1")
        if user_row:
            user_info = dict(user_row)
    
    payload = {
        "event": "CLOSED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user_info,
        "bot_config": {
            "config_id": row["target_config_id"],
            "exchange": row["exchange"] or "binance",
            "leverage": row["leverage"] or 10,
            "operationMode": row["operation_mode"] or "manual",
        },
        "trade": {
            "trade_id": row["id"],
            "symbol": row["symbol"],
            "direction": row["direction"],
            "entryPrice": float(row["entry_price"]),
            "exitPrice": float(row["exit_price"]),
            "fundingRatePct": float(row["funding_rate"]),
            "fundingPnl": float(row["funding_pnl"]),
            "pricePnl": float(row["price_pnl"]),
            "pricePnlPct": float(row["price_pnl_pct"]) if row["price_pnl_pct"] else 0.0,
            "feeCost": float(row["fee_cost"]),
            "totalPnl": float(row["total_pnl"]),
            "totalPnlPct": float(row["total_pnl_pct"]) if row["total_pnl_pct"] else 0.0,
            "closeReason": row["close_reason"],
            "openTime": row["open_time"],
            "closeTime": row["close_time"]
        }
    }

    url = "https://bot.vorxia.pro/webhook/fundtrader"
    try:
        print("Enviando payload:")
        print(payload)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                print(f"Webhook test result: HTTP {resp.status}")
                print(await resp.text())
    except Exception as e:
        print("Erro:", e)
        
    await db.close_db()

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_webhook())
