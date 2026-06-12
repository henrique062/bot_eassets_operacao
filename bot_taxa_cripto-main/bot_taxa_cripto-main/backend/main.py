"""
Backend FastAPI — Dashboard de Funding Rates (Binance + Bybit)
Serve API + frontend React (em produção, via arquivos estáticos)
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.openapi.utils import get_openapi
from loguru import logger

import binance_service
import bybit_service
import database as db
import symbol_syncer
from routes import router, close_routes_http_clients
from auth_routes import auth_router


# ──────────────────────────────────────────────────────────────
# Logging: loguru → stderr + banco de dados
# ──────────────────────────────────────────────────────────────

_main_loop: asyncio.AbstractEventLoop | None = None


async def _async_save_log(level: str, module: str, msg: str) -> None:
    """Insere log no banco de forma assíncrona (falhas são silenciadas)."""
    try:
        await db.execute(
            "INSERT INTO server_logs (level, module, message) VALUES ($1, $2, $3)",
            level, module[:100], msg,
        )
    except Exception:
        pass  # nunca deixa falha de logging derrubar o servidor


def _db_log_sink(message) -> None:
    """Sink do loguru (rodado na thread interna enqueue=True) — salva no banco."""
    global _main_loop
    if _main_loop is None or not _main_loop.is_running():
        return
    record = message.record
    level = record["level"].name
    module = record["extra"].get("module") or record.get("name") or "server"
    msg = record["message"]
    asyncio.run_coroutine_threadsafe(
        _async_save_log(level, str(module)[:100], msg),
        _main_loop,
    )


class _StdlibToLoguru(logging.Handler):
    """Intercepta loggers Python stdlib (uvicorn, asyncpg, etc.) → loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # Ignora logs de acesso HTTP (muito verboso — um por request)
        if record.name in ("uvicorn.access",):
            return
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = "INFO"
        logger.bind(module=record.name).opt(exception=record.exc_info).log(
            level, record.getMessage()
        )


class _StdoutToLoguru:
    """Intercepta print() de qualquer módulo → loguru (e continua exibindo no terminal)."""

    def __init__(self, original_stdout):
        self._orig = original_stdout
        self._buf = ""

    def write(self, msg: str) -> int:
        self._orig.write(msg)  # mantém saída normal no terminal
        self._buf += msg
        # processa linha a linha (print() pode chamar write() por fragmentos)
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if line:
                # extrai módulo a partir de prefixo estilo "[RealTrading]"
                module = "app"
                if line.startswith("[") and "]" in line:
                    module = line[1: line.index("]")]
                    line = line[line.index("]") + 1:].lstrip(" |")
                logger.bind(module=module).info(line)
        return len(msg)

    def flush(self) -> None:
        self._orig.flush()

    def isatty(self) -> bool:
        return self._orig.isatty()

    def fileno(self):
        return self._orig.fileno()


def _setup_logging() -> None:
    """Configura loguru: stderr colorido + sink de banco de dados."""
    logger.remove()  # remove handler padrão
    logger.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    # enqueue=True: processa sink em thread interna (não bloqueia event loop)
    logger.add(_db_log_sink, level="INFO", enqueue=True)

    # Redireciona stdlib logging → loguru
    logging.basicConfig(handlers=[_StdlibToLoguru()], level=logging.INFO, force=True)
    # Silencia logs muito verbosos
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Redireciona print() → loguru (captura mensagens de real_trader, etc.)
    sys.stdout = _StdoutToLoguru(sys.stdout)


# Configura logging antes de qualquer import de módulo de trading
_setup_logging()


# ──────────────────────────────────────────────────────────────
# Loop de snapshots de funding rates
# ──────────────────────────────────────────────────────────────

async def _snapshot_loop() -> None:
    """
    Salva snapshots de todas as funding rates no banco a cada 15 minutos.
    A primeira coleta ocorre imediatamente ao iniciar o servidor.
    """
    async def _resolve_rate_column() -> str:
        """Detecta a coluna correta da taxa agregada no schema atual."""
        try:
            rows = await db.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'funding_rate_snapshots'
                  AND column_name IN ('monthly_rate', 'annualized_rate')
                """
            )
            cols = {r["column_name"] for r in rows}
            if "monthly_rate" in cols:
                return "monthly_rate"
            if "annualized_rate" in cols:
                return "annualized_rate"
        except Exception as e:
            logger.bind(module="Snapshot").warning(f"Falha ao detectar coluna de taxa: {e}")
        return "annualized_rate"

    while True:
        captured_at = datetime.now(timezone.utc)
        rate_col = await _resolve_rate_column()
        try:
            for exchange_name, svc in [("binance", binance_service), ("bybit", bybit_service)]:
                try:
                    rates = await svc.get_all_funding_rates()
                except Exception as e:
                    logger.bind(module="Snapshot").error(f"Falha ao coletar rates de {exchange_name}: {e}")
                    continue

                rows = [
                    (
                        exchange_name,
                        r["symbol"],
                        r["fundingRate"],
                        r["fundingRatePercent"],
                        r["monthlyRate"],
                        r["lastPrice"],
                        r.get("volume24h", 0) or r.get("turnover24h", 0) or 0,
                        r.get("price24hPcnt", 0),
                        r.get("fundingInterval", 8),
                        captured_at,
                    )
                    for r in rates
                ]
                if not rows:
                    continue

                insert_sql = f"""
                    INSERT INTO funding_rate_snapshots
                        (exchange, symbol, funding_rate, funding_rate_pct,
                         {rate_col}, last_price, volume_24h,
                         price_24h_pcnt, funding_interval, captured_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    ON CONFLICT (exchange, symbol, captured_at) DO NOTHING
                """

                try:
                    await db.executemany(insert_sql, rows)
                    logger.bind(module="Snapshot").info(
                        f"{exchange_name}: {len(rows)} snapshots salvos em "
                        f"{captured_at.isoformat()} (coluna={rate_col})"
                    )
                except Exception as e:
                    # Retry automático trocando monthly_rate <-> annualized_rate
                    alt_col = "monthly_rate" if rate_col == "annualized_rate" else "annualized_rate"
                    alt_sql = f"""
                        INSERT INTO funding_rate_snapshots
                            (exchange, symbol, funding_rate, funding_rate_pct,
                             {alt_col}, last_price, volume_24h,
                             price_24h_pcnt, funding_interval, captured_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                        ON CONFLICT (exchange, symbol, captured_at) DO NOTHING
                    """
                    try:
                        await db.executemany(alt_sql, rows)
                        logger.bind(module="Snapshot").info(
                            f"{exchange_name}: retry OK com coluna={alt_col} "
                            f"em {captured_at.isoformat()} ({len(rows)} linhas)"
                        )
                    except Exception as retry_err:
                        logger.bind(module="Snapshot").error(
                            f"ERRO ao inserir snapshots de {exchange_name} "
                            f"(coluna={rate_col}, retry={alt_col}): {retry_err} | erro inicial: {e}"
                        )
        except Exception as e:
            logger.bind(module="Snapshot").error(f"Erro inesperado no loop: {e}")

        await asyncio.sleep(900)  # 15 minutos até a próxima coleta


# ──────────────────────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia startup e shutdown do servidor."""
    global _main_loop
    _main_loop = asyncio.get_running_loop()

    # Inicializa pool de banco de dados
    await db.init_db()

    # Auto-migracao leve de colunas opcionais em producao
    try:
        await db.execute(
            "ALTER TABLE real_config ADD COLUMN IF NOT EXISTS trailing_start_profit_pct NUMERIC"
        )
    except Exception:
        pass

    # Motivo: habilitar filtro minimo de funding (%) por sessao no real trading.
    try:
        await db.execute(
            "ALTER TABLE real_config ADD COLUMN IF NOT EXISTS min_funding_rate_pct NUMERIC DEFAULT 0.001"
        )
    except Exception:
        pass

    # Auto-migração: pendências de entrada limit manual (retomada após restart).
    try:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS real_pending_entries (
                id BIGSERIAL PRIMARY KEY,
                config_id INT NOT NULL REFERENCES real_config(id) ON DELETE CASCADE,
                user_id INT NULL REFERENCES users(id) ON DELETE SET NULL,
                exchange VARCHAR(20) NOT NULL DEFAULT 'binance',
                symbol VARCHAR(30) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                side VARCHAR(10) NOT NULL,
                size NUMERIC(24,8) NOT NULL,
                limit_price NUMERIC(24,8) NOT NULL,
                order_id TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                last_error TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_real_pending_entries_config_status
                ON real_pending_entries(config_id, status, created_at DESC)
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_real_pending_entries_user_exchange
                ON real_pending_entries(user_id, exchange, created_at DESC)
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_real_pending_entries_order_id
                ON real_pending_entries(order_id)
            """
        )
    except Exception:
        pass

    # Auto-migração: cria tabela server_logs se não existir
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_logs (
                id         SERIAL PRIMARY KEY,
                level      VARCHAR(10)  NOT NULL,
                module     VARCHAR(100),
                message    TEXT         NOT NULL,
                created_at TIMESTAMPTZ  DEFAULT NOW()
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_server_logs_created_at ON server_logs(created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_server_logs_level ON server_logs(level)"
        )
    except Exception:
        pass

    # Limpa logs antigos (>7 dias) a cada startup
    try:
        deleted = await db.fetchval(
            "WITH d AS (DELETE FROM server_logs WHERE created_at < NOW() - INTERVAL '7 days' RETURNING id) SELECT COUNT(*) FROM d"
        )
        if deleted:
            logger.bind(module="ServerLogs").info(f"Cleanup: {deleted} logs antigos removidos (>7 dias)")
    except Exception:
        pass

    # Relança real trader se estava ativo antes do restart
    from real_trader import maybe_resume_on_startup as resume_real
    await resume_real()

    # Auto-migração: cria tabela bot_ai_analyses se não existir
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_ai_analyses (
                id SERIAL PRIMARY KEY,
                config_id INT REFERENCES real_config(id) ON DELETE CASCADE,
                analysis_text TEXT,
                suggested_config JSONB,
                applied BOOLEAN DEFAULT FALSE,
                applied_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                trigger_type VARCHAR(20) DEFAULT 'manual'
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bot_ai_analyses_config ON bot_ai_analyses(config_id)")
    except Exception:
        pass  # Tabela já existe ou erro não-crítico

    logger.bind(module="Server").info("Servidor iniciado com sucesso")

    # Inicia coleta periódica de snapshots em background
    asyncio.create_task(_snapshot_loop())

    # Inicia rotina de sincronização de símbolos (a cada 10 min)
    asyncio.create_task(symbol_syncer.sync_symbols_loop())

    # Inicia WebSocket de mark prices da Binance Futures (tempo real, substitui REST polling)
    from binance_ws_market import start_stream as start_binance_market_stream
    asyncio.create_task(start_binance_market_stream())

    yield

    logger.bind(module="Server").info("Servidor encerrando")
    # Comentário de controle: encerra clientes HTTP compartilhados das rotas para shutdown limpo.
    await close_routes_http_clients()
    # Shutdown: fecha pool do banco
    await db.close_db()


_openapi_tags = [
    {"name": "Auth", "description": "Autenticação JWT. Use POST /api/auth/login para obter o token Bearer."},
    {"name": "Market Data", "description": "Funding rates, histórico, LSR e klines da Binance/Bybit. Rotas públicas, sem autenticação."},
    {"name": "Paper Trading", "description": "Gerencia sessões de paper trading (simulação sem capital real)."},
    {"name": "Real Trading", "description": "Gerencia sessões de trading real na exchange. Requer autenticação."},
    {"name": "AI Analysis", "description": "Análises automáticas por IA e smart reports históricos."},
    {"name": "Settings", "description": "Configurações globais do sistema e por usuário (inclui chaves de API)."},
    {"name": "Strategies", "description": "Salva, lista e remove estratégias de trading."},
    {"name": "Logs", "description": "Histórico de operações, trades e logs do servidor."},
    {"name": "Admin", "description": "Ferramentas administrativas: análise de PnL vs Binance e correção de dados históricos."},
]

app = FastAPI(
    title="Crypto Funding Rates API",
    description="API para consultar taxas de financiamento do mercado futuro",
    version="2.0.0",
    lifespan=lifespan,
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=_openapi_tags,
    )
    # Adiciona esquema de segurança BearerAuth
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Token JWT obtido via POST /api/auth/login. Formato: Bearer <token>",
    }
    # Aplica security em todas as rotas exceto Auth e Market Data
    _public_tags = {"Auth", "Market Data"}
    for path_data in schema.get("paths", {}).values():
        for operation in path_data.values():
            if not isinstance(operation, dict):
                continue
            op_tags = set(operation.get("tags", []))
            if not op_tags.intersection(_public_tags):
                operation.setdefault("security", [{"BearerAuth": []}])
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

# CORS — permite o frontend React se conectar (dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas da API
app.include_router(auth_router)
app.include_router(router)

# Servir frontend estático em produção
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        from fastapi.responses import Response
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # Paths com extensão de arquivo que não existem → 404
        if "." in full_path.split("/")[-1]:
            return Response(status_code=404)
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    async def root():
        return {
            "message": "Crypto Funding Rates API",
            "docs": "/docs",
            "frontend": "Use npm run dev no diretório frontend/",
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
