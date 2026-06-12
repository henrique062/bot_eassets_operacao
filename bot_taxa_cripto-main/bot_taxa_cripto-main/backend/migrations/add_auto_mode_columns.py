import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def run_migration():
    """Adiciona colunas para os modos automáticos nas tabelas de config."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL não configurado.")
        return

    conn = await asyncpg.connect(db_url)
    print("Conectado ao DB. Aplicando migração para auto_modes...")

    try:
        # Colunas para real_config
        await conn.execute("""
            ALTER TABLE real_config
            ADD COLUMN IF NOT EXISTS operation_mode VARCHAR DEFAULT 'manual',
            ADD COLUMN IF NOT EXISTS auto_direction VARCHAR DEFAULT 'both',
            ADD COLUMN IF NOT EXISTS auto_max_symbols INT DEFAULT 8,
            ADD COLUMN IF NOT EXISTS auto_min_score NUMERIC DEFAULT 50.0,
            ADD COLUMN IF NOT EXISTS auto_window_minutes INT DEFAULT 60
        """)
        print("Colunas adicionadas com sucesso em real_config.")

        # Colunas para paper_config
        await conn.execute("""
            ALTER TABLE paper_config
            ADD COLUMN IF NOT EXISTS operation_mode VARCHAR DEFAULT 'manual',
            ADD COLUMN IF NOT EXISTS auto_direction VARCHAR DEFAULT 'both',
            ADD COLUMN IF NOT EXISTS auto_max_symbols INT DEFAULT 8,
            ADD COLUMN IF NOT EXISTS auto_min_score NUMERIC DEFAULT 50.0,
            ADD COLUMN IF NOT EXISTS auto_window_minutes INT DEFAULT 60
        """)
        print("Colunas adicionadas com sucesso em paper_config.")

    except Exception as e:
        print(f"Erro na migração: {e}")
    finally:
        await conn.close()
        print("Migração finalizada.")

if __name__ == "__main__":
    asyncio.run(run_migration())
