import asyncio
import database as db

async def migrate():
    await db.init_db()
    # Adding entry_seconds and exit_seconds to paper_config table
    await db.execute('ALTER TABLE paper_config ADD COLUMN IF NOT EXISTS entry_seconds INT DEFAULT 30;')
    await db.execute('ALTER TABLE paper_config ADD COLUMN IF NOT EXISTS exit_seconds INT DEFAULT 30;')
    print("Columns added successfully")

asyncio.run(migrate())
