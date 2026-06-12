import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def run_migration():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL não configurado.")
        return

    print("Conectando ao banco de dados...")
    conn = await asyncpg.connect(db_url)
    
    file_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "20260223_add_bot_ai_analyses.sql")
    with open(file_path, "r", encoding="utf-8") as f:
        sql = f.read()

    print("Executando migration...")
    await conn.execute(sql)
    
    print("Migration executada com sucesso!")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run_migration())
