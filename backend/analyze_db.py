import sqlite3
import json

db_path = 'backend/trading_bot.db'

def get_schema():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    schema = {}
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        schema[table_name] = [col[1] for col in columns]
        
    print(json.dumps(schema, indent=2))
    conn.close()

if __name__ == '__main__':
    get_schema()
