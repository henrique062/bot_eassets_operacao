import asyncio
import os
import asyncpg
from dotenv import load_dotenv
import json

load_dotenv()
_DATABASE_URL = os.getenv("DATABASE_URL", "")

async def main():
    if not _DATABASE_URL:
        print("Error: DATABASE_URL not found in environment.")
        return
        
    conn = await asyncpg.connect(_DATABASE_URL)
    
    # Get all tables in public schema
    tables = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    
    schema = {}
    for record in tables:
        table_name = record['table_name']
        columns = await conn.fetch(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
        """)
        schema[table_name] = {col['column_name']: col['data_type'] for col in columns}
        
    print(json.dumps(schema, indent=2))
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())