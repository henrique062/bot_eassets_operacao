import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

def fetch_table(query):
    try:
        cur.execute(query)
        rows = cur.fetchall()
        return "\n".join([f"{dict(row)}" for row in rows])
    except Exception as e:
        conn.rollback()
        return f"Error: {e}"

output = fetch_table("SELECT id, session_name, symbols, operation_mode FROM real_config WHERE active=TRUE")

with open("output_cfg_active.txt", "w", encoding="utf-8") as f:
    f.write(output)

cur.close()
conn.close()
