---
name: project-bot-encryptos
description: Architecture and key decisions for the bot_encryptos Python API project
metadata:
  type: project
---

Python API infra for the PHOENIX/Encryptos trading bot.

**Location:** `D:\3 - Projetos investimentos\Dash encryptos PHONIX Junho\bot_encryptos\`

**Stack:**
- FastAPI + asyncpg (no ORM) + loguru + httpx + Pydantic v2
- Playwright (sync) wrapped in run_in_executor for async compat
- PostgreSQL 16 via asyncpg pool singleton in `database.py`
- `config.py` uses plain os.environ (not pydantic-settings) — project decision

**Key paths:**
- `python_api/main.py` — FastAPI app + lifespan (pool init + scraper loop task)
- `python_api/config.py` — all env vars
- `python_api/database.py` — asyncpg pool singleton (get_pool / init_db / close_db)
- `python_api/db/repositories.py` — all SQL queries
- `python_api/services/eassets_scraper.py` — Playwright scraper + ingest_snapshot()
- `python_api/services/eassets_loop.py` — background asyncio loop + trigger_now()
- `python_api/services/rust_bridge.py` — httpx client for Rust core (port 8001)
- `python_api/db/migrations/001_create_eassets_tables.sql` — full schema (8 tables)
- `python_api/db/migrations/002_migrate_sqlite_data.py` — one-shot SQLite→PG migration

**gerar_painel.py** is at project root (one level above python_api).
Imported via sys.path.insert in eassets_scraper.py pointing to grandparent dir.

**Why:** All response JSON follows `{"ok": true, "data": ...}` envelope.
