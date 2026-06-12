# Planejamento — Bot Encryptos (Phoenix)

## Visão Geral

Bot de trading automatizado baseado na **Metodologia Encryptos**:
- Aguarda Reset do BTC (RSI 30m/1h sobrevendido)
- Identifica altcoins com força relativa (Exponential BTC positivo durante o reset)
- Confirma combustão: TPM acelerado + LSR < 1 + OI crescente
- Executa ordens na **Bybit** com alavancagem configurável

**Stack híbrida: Core crítico em Rust + API/gestão em Python**

| Camada | Linguagem | Motivo |
|--------|-----------|--------|
| Engine de sinais, decisão, execução de ordens | **Rust** | Latência µs, sem GC, WebSocket de alta frequência |
| API REST, banco de dados, migração, config | **Python / FastAPI** | Velocidade de desenvolvimento, CCXT, asyncpg |
| Deploy | **Docker Compose** | VPS — todos os serviços em containers |

---

## Estrutura do Projeto (este diretório)

```
D:\3 - Projetos investimentos\Dash encryptos PHONIX Junho\
│
├── PLANEJAMENTO_BOT_ENCRYPTOS.md          ← este arquivo
│
├── bot_taxa_cripto-main/                  ← projeto base (referência, não alterado)
├── Manuais/                               ← metodologia Encryptos
│
└── bot_encryptos/                         ← NOVO PROJETO (criar aqui)
    │
    ├── docker-compose.yml                 # Orquestra todos os serviços
    ├── .env.example                       # Template de variáveis de ambiente
    │
    ├── rust_core/                         # Crate Rust — hot path crítico
    │   ├── Cargo.toml
    │   ├── Cargo.lock
    │   └── src/
    │       ├── main.rs                    # Entrypoint: inicia todos os loops async
    │       ├── config.rs                  # Lê env vars, struct Config
    │       │
    │       ├── market/
    │       │   ├── mod.rs
    │       │   ├── bybit_ws.rs            # WebSocket Bybit público (trades/sec em tempo real)
    │       │   ├── bybit_rest.rs          # REST público: tickers, OI, LSR, klines
    │       │   └── btc_monitor.rs         # RSI BTC 30m/1h — detecta estado Reset
    │       │
    │       ├── engine/
    │       │   ├── mod.rs
    │       │   ├── scorer.rs              # Score Encryptos por moeda (0–100)
    │       │   ├── signal_filter.rs       # Checklist dos 6 filtros obrigatórios
    │       │   └── decision.rs            # Loop de decisão: tick → filtro → dispara trade
    │       │
    │       ├── trading/
    │       │   ├── mod.rs
    │       │   ├── bybit_executor.rs      # Abre/fecha ordens via REST Bybit (signed)
    │       │   ├── position_manager.rs    # Estado em memória (HashMap) + notifica Python via HTTP
    │       │   ├── risk_manager.rs        # Stop loss, TP, trailing stop (loop por posição)
    │       │   ├── watchlist_manager.rs   # PCL — máquina de estados de re-entrada persistente
    │       │   └── structural_validator.rs # PCL — avalia 5 critérios de estrutura preservada
    │       │
    │       └── db/
    │           ├── mod.rs
    │           └── postgres.rs            # Pool sqlx PostgreSQL — persiste trades/positions/logs
    │
    ├── python_api/                        # Serviço Python — API REST + migração + config
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   ├── main.py                        # FastAPI app
    │   ├── database.py                    # asyncpg pool (reusar do projeto base)
    │   ├── config.py                      # Env vars
    │   │
    │   ├── api/
    │   │   ├── routes_bot.py              # start/stop/status do bot (chama Rust core via HTTP)
    │   │   ├── routes_trades.py           # Histórico, posições abertas, logs
    │   │   └── routes_config.py           # CRUD de configurações do bot
    │   │
    │   ├── db/
    │   │   ├── repositories.py            # Queries SQL para tabelas eassets_*
    │   │   └── migrations/
    │   │       ├── 001_create_eassets_tables.sql
    │   │       └── 002_migrate_sqlite_data.py   # SQLite → PostgreSQL (execução única)
    │   │
    │   └── services/
    │       ├── rust_bridge.py             # Cliente HTTP para comunicar com Rust core
    │       ├── eassets_scraper.py         # Portado do eassets-main — Playwright scraper
    │       └── eassets_loop.py            # Loop background: captura → salva → notifica Rust
    │
    └── nginx/                             # Proxy reverso (opcional na VPS)
        └── nginx.conf
```

---

## Coleta Automática de Dados — eAssets Scraper

### Como funciona (projeto `eassets-main`)
1. **Playwright** (Python) abre `https://eassets.ai/panel` headless
2. Faz login com `EASSETS_EMAIL` / `EASSETS_PASSWORD`
3. Clica no botão **"Export for AI"** → seleciona modo **"Full"**
4. Intercepta o `navigator.clipboard.writeText` via JS inject para capturar o JSON sem depender do clipboard real
5. Valida o payload (precisa ter `data`, `timestamp`, `symbols`)
6. Salva no banco e dispara atualização do engine

### Integração no Novo Bot

O scraper é **portado para dentro do `python_api`** como um serviço background, substituindo o import manual do projeto Phoenix original. A cada captura bem-sucedida, notifica o Rust core para atualizar o estado interno dos sinais.

```
[eassets.ai/panel]
       │  Playwright headless (a cada EASSETS_INTERVAL_SECONDS)
       ▼
[python_api / eassets_scraper.py]  ← portado do eassets-main
       │
       ├─ valida payload
       ├─ salva em eassets_market_snapshots (PostgreSQL)
       ├─ salva raw JSON em eassets_raw_snapshots (tabela nova)
       └─ POST http://rust_core:8001/internal/snapshot-updated
                    │
                    └─ Rust reprocessa scorer com dados frescos
```

### Tabelas de Snapshots — espelho exato do `phoenix.db`

O `phoenix.db` (SQLite) tem duas tabelas centrais: `snapshots` + `metrics`.
As tabelas PostgreSQL abaixo espelham o **mesmo schema** para não quebrar nenhuma lógica de processamento existente (`gerar_painel.py`, `analise_dados.py`, `db.py`).

**`eassets_snapshots`** — metadados de cada scan (espelho de `snapshots`)
```sql
CREATE TABLE eassets_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TEXT UNIQUE NOT NULL,   -- timestamp do scan vindo do JSON (chave de dedup)
    exchange    TEXT,
    setup       TEXT,
    mode        TEXT,
    symbols     INTEGER,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source      TEXT,                   -- 'auto_scraper' | 'manual' | 'api'
    btc_reset   BOOLEAN,                -- TRUE = BTC em reset/janela aberta no snapshot
    trigger     VARCHAR(20) NOT NULL DEFAULT 'auto'
);
CREATE INDEX idx_eassets_snapshots_ts ON eassets_snapshots(timestamp DESC);
```

**`eassets_metrics`** — dados por moeda por snapshot (espelho de `metrics`)
```sql
CREATE TABLE eassets_metrics (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES eassets_snapshots(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    rank            INTEGER,
    score           INTEGER,
    setup           TEXT,
    price           NUMERIC(24,8),
    price_change_1d NUMERIC(14,4),
    exp_1d          NUMERIC(10,4),
    exp_4h          NUMERIC(10,4),
    exp_1h          NUMERIC(10,4),
    oi_trend        NUMERIC(10,4),
    lsr             NUMERIC(10,4),
    lsr_trend       NUMERIC(10,4),
    rsi_4h          NUMERIC(6,2),
    oi_usd          NUMERIC(24,6),
    trades_min      NUMERIC(14,2),
    range_4h        NUMERIC(10,4),
    range_1d        NUMERIC(10,4),
    trades_1d       NUMERIC(18,2),
    toi             NUMERIC(18,2),      -- trades:1D por $1M de OI (intensidade SM)
    setup_score     INTEGER,            -- 0-7 critérios do Setup de Ouro atendidos
    setup_grade     TEXT,               -- 'SETUP DE OURO' | 'PARCIAL' | ''
    raw_json        TEXT NOT NULL       -- dict bruto completo da moeda (mesmo do SQLite)
);
CREATE INDEX idx_eassets_metrics_snap   ON eassets_metrics(snapshot_id);
CREATE INDEX idx_eassets_metrics_sym    ON eassets_metrics(symbol);
CREATE INDEX idx_eassets_metrics_rank   ON eassets_metrics(snapshot_id, rank);
CREATE INDEX idx_eassets_metrics_toi    ON eassets_metrics(snapshot_id, toi DESC NULLS LAST);
CREATE INDEX idx_eassets_metrics_grade  ON eassets_metrics(setup_grade) WHERE setup_grade = 'SETUP DE OURO';
```

**`eassets_symbol_tags`** — tags manuais por moeda (ex.: Binance Alpha)
```sql
CREATE TABLE eassets_symbol_tags (
    symbol TEXT NOT NULL,
    tag    TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    PRIMARY KEY (symbol, tag)
);
```

**Fluxo de ingestão (espelho do `db.ingest()` do phoenix):**
```
scrape_eassets_json()
    │
    ▼
validate_eassets_payload(data)
    │
    ▼
gerar_painel.build_rows(data)          ← mesma função do projeto original
    │  calcula: score, setup, checklist, toi, entry_grade
    ▼
INSERT eassets_snapshots (timestamp, exchange, btc_reset, ...)
    │
    ▼
INSERT eassets_metrics (por moeda: rank, score, setup_grade, raw_json, ...)
    │
    ▼
POST rust_core:8001/internal/snapshot-updated?snap_id=<id>
```

> O `raw_json` por moeda preserva **todos os campos brutos** do JSON — nada é descartado,
> igual ao phoenix.db. Qualquer lógica que ler `raw_json` funcionará idêntica.

### Novo serviço no Docker Compose

O scraper precisa de Chromium — Dockerfile separado ou mesmo container Python com Playwright.

```yaml
# adicionado ao docker-compose.yml
  eassets_scraper:
    build:
      context: ./python_api
      dockerfile: Dockerfile.scraper      # usa python-playwright como base
    restart: unless-stopped
    env_file: .env
    depends_on:
      - python_api
    environment:
      - EASSETS_INTERVAL_SECONDS=1800     # captura a cada 30 min
      - EASSETS_AUTO_ENABLED=1
      - EASSETS_HEADLESS=1
```

```dockerfile
# python_api/Dockerfile.scraper
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps
COPY . .
CMD ["python", "-m", "services.eassets_loop"]
```

### Variáveis de ambiente adicionais

```ini
# eAssets scraper (credenciais da conta eassets.ai)
EASSETS_EMAIL=seu-email@exemplo.com
EASSETS_PASSWORD=sua-senha
EASSETS_INTERVAL_SECONDS=1800    # 30 minutos
EASSETS_AUTO_ENABLED=1
EASSETS_HEADLESS=1
EASSETS_TIMEOUT_MS=240000
```

### Arquivos no `python_api`

```
python_api/
└── services/
    ├── eassets_scraper.py    # portado do eassets-main (sem alteração de lógica)
    ├── eassets_loop.py       # loop background: captura → salva → notifica Rust
    └── rust_bridge.py        # cliente HTTP para controlar Rust core
```

### Endpoint da API para controle manual

```
POST /api/eassets/scraper/capture      # dispara captura manual imediata
GET  /api/eassets/scraper/status       # estado: running, last_ok, last_error, next_run_at
GET  /api/eassets/raw-snapshots        # lista de capturas brutas com status
GET  /api/eassets/panel/tags/alpha     # lista moedas Binance Alpha
POST /api/eassets/panel/tags/alpha     # adiciona moedas Binance Alpha
DELETE /api/eassets/panel/tags/alpha/{symbol} # remove moeda Binance Alpha
```

---

## Comunicação Rust ↔ Python

O Rust core expõe uma **API HTTP interna** (porta 8001) para controle:

```
POST  http://rust_core:8001/internal/start              # Python → Rust: inicia engine
POST  http://rust_core:8001/internal/stop               # Python → Rust: para engine
POST  http://rust_core:8001/internal/config             # Python → Rust: atualiza config em runtime
GET   http://rust_core:8001/internal/status             # Python → Rust: estado atual do engine
POST  http://rust_core:8001/internal/snapshot-updated   # Python → Rust: novo snapshot eAssets disponível
```

O Rust **escreve direto no PostgreSQL** (tabelas `eassets_*`). Python lê as mesmas tabelas para servir a API REST externa.

```
[eassets.ai] ──→ [Playwright Scraper] ──→ [PostgreSQL eassets_raw_snapshots]
                                                          │
                                    POST /snapshot-updated│
                                                          ▼
[Bybit WS/REST] ──────────────────→ [Rust Core :8001] ←──┘
                                          │
                                          ├─ escreve → [PostgreSQL eassets_*]
                                          │
[Python API :8000] ──────────────────→   └─ controle via HTTP interno
        │
        └─ lê ─→ [PostgreSQL eassets_*] → responde frontend/usuário
```

---

## Docker Compose — Estrutura de Serviços

```yaml
# docker-compose.yml (resumo estrutural)
services:
  rust_core:
    build: ./rust_core
    restart: unless-stopped
    env_file: .env
    ports:
      - "8001:8001"          # API interna (não exposta externamente)
    depends_on:
      - db

  python_api:
    build: ./python_api
    restart: unless-stopped
    env_file: .env
    ports:
      - "8000:8000"          # API pública
    depends_on:
      - rust_core
      - db

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    env_file: .env
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./python_api/db/migrations/001_create_eassets_tables.sql:/docker-entrypoint-initdb.d/001.sql

  nginx:                     # Opcional — proxy reverso na VPS
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - python_api

volumes:
  postgres_data:
```

> Na VPS: `docker compose up -d --build` sobe tudo. Zero configuração manual.

---

## Banco de Dados — Tabelas `eassets_*`

> Todas novas tabelas usam prefixo `eassets_`. Schema inspirado nas `real_*` do projeto base.
> Coexistem no mesmo banco sem conflito com tabelas existentes (`real_*`, etc).

### `eassets_bot_config`
```sql
CREATE TABLE eassets_bot_config (
    id              BIGSERIAL PRIMARY KEY,
    session_name    VARCHAR(100) NOT NULL,
    exchange        VARCHAR(20)  NOT NULL DEFAULT 'bybit',
    active          BOOLEAN      NOT NULL DEFAULT FALSE,
    paused          BOOLEAN      NOT NULL DEFAULT FALSE,

    capital         NUMERIC(18,6) NOT NULL,
    balance         NUMERIC(18,6) NOT NULL,
    leverage        SMALLINT      NOT NULL DEFAULT 5,
    fee_type        VARCHAR(10)   NOT NULL DEFAULT 'maker',
    fee_rate        NUMERIC(10,6) NOT NULL DEFAULT 0.0002,

    -- Parâmetros Encryptos
    min_tpm         INTEGER       NOT NULL DEFAULT 800,
    min_oi_trend    NUMERIC(10,4) DEFAULT 0,
    max_lsr         NUMERIC(10,4) DEFAULT 1.0,
    min_rsi_btc     NUMERIC(6,2)  DEFAULT NULL,
    max_rsi_btc     NUMERIC(6,2)  DEFAULT 40.0,
    min_exp_btc     NUMERIC(10,4) DEFAULT 0,
    max_positions   SMALLINT      NOT NULL DEFAULT 5,
    min_score       NUMERIC(6,2)  NOT NULL DEFAULT 65.0,

    -- Gestão de risco
    stop_loss_pct        NUMERIC(10,4) DEFAULT NULL,
    stop_loss_usd        NUMERIC(18,6) DEFAULT NULL,
    take_profit_pct      NUMERIC(10,4) DEFAULT NULL,
    trailing_stop_pct    NUMERIC(10,4) DEFAULT NULL,
    trailing_start_pct   NUMERIC(10,4) DEFAULT NULL,
    break_even_at_pct    NUMERIC(10,4) DEFAULT NULL,

    entry_seconds   SMALLINT NOT NULL DEFAULT 30,
    exit_seconds    SMALLINT NOT NULL DEFAULT 30,

    -- PCL — Persistent Candidate Loop
    pcl_enabled           BOOLEAN       NOT NULL DEFAULT TRUE,
    pcl_cooldown_minutes  INTEGER       NOT NULL DEFAULT 30,
    pcl_max_attempts      SMALLINT      NOT NULL DEFAULT 3,
    pcl_min_struct_score  SMALLINT      NOT NULL DEFAULT 3,
    pcl_profit_target_usd NUMERIC(18,6) DEFAULT NULL,

    user_id         INTEGER DEFAULT NULL,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    ended_at        TIMESTAMPTZ DEFAULT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `eassets_positions`
```sql
CREATE TABLE eassets_positions (
    id               BIGSERIAL PRIMARY KEY,
    config_id        BIGINT NOT NULL REFERENCES eassets_bot_config(id) ON DELETE CASCADE,
    symbol           VARCHAR(30) NOT NULL,
    direction        VARCHAR(5)  NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price      NUMERIC(24,8) NOT NULL,
    size             NUMERIC(24,8) NOT NULL,
    value            NUMERIC(18,6) NOT NULL,
    funding_rate     NUMERIC(14,6) NOT NULL DEFAULT 0,
    funding_rate_pct NUMERIC(14,6) NOT NULL DEFAULT 0,
    open_order_id    VARCHAR(100),
    tp_order_id      VARCHAR(100),
    tp_price         NUMERIC(24,8),
    open_time        VARCHAR(30),
    open_timestamp   BIGINT NOT NULL,
    -- Snapshot dos sinais no momento da entrada (auditoria)
    entry_rsi_btc    NUMERIC(6,2),
    entry_exp_btc    NUMERIC(10,4),
    entry_tpm        INTEGER,
    entry_lsr        NUMERIC(10,4),
    entry_oi_trend   NUMERIC(10,4),
    entry_score      NUMERIC(6,2),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_eassets_positions_config ON eassets_positions(config_id);
CREATE INDEX idx_eassets_positions_symbol ON eassets_positions(symbol);
```

### `eassets_trades`
```sql
CREATE TABLE eassets_trades (
    id              BIGSERIAL PRIMARY KEY,
    config_id       BIGINT NOT NULL REFERENCES eassets_bot_config(id) ON DELETE CASCADE,
    symbol          VARCHAR(30) NOT NULL,
    direction       VARCHAR(5)  NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price     NUMERIC(24,8) NOT NULL,
    exit_price      NUMERIC(24,8) NOT NULL,
    size            NUMERIC(24,8) NOT NULL,
    funding_rate    NUMERIC(14,6) NOT NULL DEFAULT 0,
    funding_pnl     NUMERIC(18,6) NOT NULL DEFAULT 0,
    price_pnl       NUMERIC(18,6) NOT NULL DEFAULT 0,
    price_pnl_pct   NUMERIC(18,6) NOT NULL DEFAULT 0,
    fee_cost        NUMERIC(18,6) NOT NULL DEFAULT 0 CHECK (fee_cost >= 0),
    total_pnl       NUMERIC(18,6) NOT NULL DEFAULT 0,
    total_pnl_pct   NUMERIC(14,6) NOT NULL DEFAULT 0,
    balance_after   NUMERIC(18,6) NOT NULL,
    close_reason    VARCHAR(50),
    open_time       VARCHAR(30),
    close_time      VARCHAR(30),
    trade_timestamp BIGINT NOT NULL,
    exchange        VARCHAR(20) NOT NULL DEFAULT 'bybit',
    entry_rsi_btc   NUMERIC(6,2),
    entry_exp_btc   NUMERIC(10,4),
    entry_tpm       INTEGER,
    entry_lsr       NUMERIC(10,4),
    entry_score     NUMERIC(6,2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_eassets_trades_config_id      ON eassets_trades(config_id);
CREATE INDEX idx_eassets_trades_config_created ON eassets_trades(config_id, created_at DESC);
CREATE INDEX idx_eassets_trades_timestamp      ON eassets_trades(trade_timestamp DESC);
CREATE INDEX idx_eassets_trades_symbol         ON eassets_trades(symbol);
```

### `eassets_order_logs`
```sql
CREATE TABLE eassets_order_logs (
    id          BIGSERIAL PRIMARY KEY,
    config_id   BIGINT NOT NULL,
    log_level   VARCHAR(10) NOT NULL DEFAULT 'INFO',
    event       VARCHAR(50) NOT NULL,
    symbol      VARCHAR(30),
    direction   VARCHAR(5),
    exchange    VARCHAR(20),
    message     TEXT,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_eassets_order_logs_config ON eassets_order_logs(config_id, created_at DESC);
```

### `eassets_market_snapshots`
```sql
CREATE TABLE eassets_market_snapshots (
    id           BIGSERIAL PRIMARY KEY,
    symbol       VARCHAR(30) NOT NULL,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    price        NUMERIC(24,8),
    rsi_1m       NUMERIC(6,2),
    rsi_5m       NUMERIC(6,2),
    rsi_15m      NUMERIC(6,2),
    rsi_1h       NUMERIC(6,2),
    exp_btc      NUMERIC(10,4),
    trades_min   INTEGER,
    trades_sec   NUMERIC(10,2),
    oi           NUMERIC(24,6),
    oi_trend     NUMERIC(10,4),
    lsr          NUMERIC(10,4),
    lsr_trend    NUMERIC(10,4),
    funding_rate NUMERIC(14,6),
    range_level  NUMERIC(10,4),
    score        NUMERIC(6,2)
);
CREATE INDEX idx_eassets_snapshots_symbol_time ON eassets_market_snapshots(symbol, captured_at DESC);
```

### `eassets_watchlist`
Moedas em monitoramento persistente após stop — candidatas a re-entrada.

```sql
CREATE TABLE eassets_watchlist (
    id                  BIGSERIAL PRIMARY KEY,
    config_id           BIGINT NOT NULL REFERENCES eassets_bot_config(id) ON DELETE CASCADE,
    symbol              VARCHAR(30) NOT NULL,

    -- Estado da máquina de estados
    state               VARCHAR(20) NOT NULL DEFAULT 'WATCHLIST',
    -- WATCHLIST   = monitorando, aguardando setup se formar novamente
    -- COOLDOWN    = pausa obrigatória após stop antes de re-entrar
    -- CANDIDATE   = passou no checklist, aguarda ordem de entrada
    -- INVALIDATED = indicadores estruturais fracos, removido do loop
    -- COMPLETED   = atingiu lucro alvo, encerrado com sucesso

    -- Histórico de tentativas
    attempt_count       SMALLINT NOT NULL DEFAULT 0,  -- quantas entradas já foram feitas
    max_attempts        SMALLINT NOT NULL DEFAULT 3,  -- circuit breaker
    total_pnl_so_far    NUMERIC(18,6) NOT NULL DEFAULT 0,  -- PnL acumulado de todas as tentativas

    -- Referência do último trade que resultou em stop
    last_trade_id       BIGINT REFERENCES eassets_trades(id),
    last_stop_reason    VARCHAR(50),                  -- 'stop_loss', 'trailing_stop'
    last_stop_price     NUMERIC(24,8),
    last_entry_price    NUMERIC(24,8),

    -- Cooldown
    cooldown_until      TIMESTAMPTZ,                  -- não re-entra antes deste horário

    -- Snapshot dos indicadores estruturais no momento do stop
    -- (usado para validar se a mola ainda está comprimida)
    stop_range_4h       NUMERIC(10,4),                -- range_level:4h no stop
    stop_range_1d       NUMERIC(10,4),                -- range_level:1D no stop
    stop_exp_btc_1d     NUMERIC(10,4),                -- exp_btc:1D no stop
    stop_toi            NUMERIC(18,2),                -- T/OI no stop
    stop_oi_trend       NUMERIC(10,4),
    stop_lsr            NUMERIC(10,4),

    -- Última verificação estrutural
    last_check_at       TIMESTAMPTZ,
    last_check_score    NUMERIC(6,2),
    last_check_passed   BOOLEAN,

    -- Meta
    added_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (config_id, symbol)   -- uma entrada por moeda por sessão
);
CREATE INDEX idx_eassets_watchlist_config   ON eassets_watchlist(config_id, state);
CREATE INDEX idx_eassets_watchlist_cooldown ON eassets_watchlist(cooldown_until) WHERE state = 'COOLDOWN';
```

---

## Sistema de Monitoramento Persistente (PCL — Persistent Candidate Loop)

### O Problema
O mercado de acumulação tem um padrão recorrente:
1. Moeda aparece no ranking (todos os indicadores bons)
2. Bot entra — preço se move um pouco, depois reverte → **stop ativado**
3. Moeda ainda está em acumulação: `range_level` alto, `T/OI` desproporcional, `exp_btc:1D` positivo
4. Dias depois: moeda explode +30%, +50% — o setup **ainda estava válido**

O stop foi legítimo (gestão de risco), mas a estrutura não mudou. A oportunidade não acabou.

### Solução: Máquina de Estados por Moeda

```
SCANNING (pool geral)
    │
    │ passa no checklist (7 filtros) + BTC em reset
    ▼
CANDIDATE
    │
    │ ordem executada
    ▼
ACTIVE (posição aberta)
    │
    ├─── take_profit / trailing_stop → COMPLETED (remove do loop)
    │
    └─── stop_loss ativo
              │
              ▼
         [Verificação Estrutural]
              │
              ├─ indicadores fracos → INVALIDATED (remove do loop)
              │
              └─ estrutura preservada → COOLDOWN
                        │
                        │ (cooldown_until expirou)
                        │ (attempt_count < max_attempts)
                        ▼
                   WATCHLIST (re-monitora)
                        │
                        │ checklist passa novamente
                        ▼
                   CANDIDATE (nova tentativa)
                        │
                        └─ loop até COMPLETED ou INVALIDATED
```

### Regras de Invalidação (saída do loop)

Moeda é **removida** do watchlist (→ INVALIDATED) se qualquer condição abaixo:

| Critério | Regra de Invalidação |
|----------|----------------------|
| Estrutura vs BTC | `exp_btc:1D` < -50 por 2+ verificações consecutivas |
| Acumulação perdida | `range_level:4h` < 2 E `range_level:1D` < 2 |
| SM saiu | `oi_trend` < 0 por 3+ verificações consecutivas (OI caindo = capital saindo) |
| Armadilha confirmada | `is_trap()` = true (preço caindo + LSR subindo + OI caindo) |
| Max tentativas | `attempt_count` >= `max_attempts` |
| Curto-prazo fraco | `exp_btc:5m` < 0 E `exp_btc:15m` < 0 E `exp_btc:1h` < 0 por 3+ checks → acum quebrada |

### Verificação de Estrutura Preservada (após stop)

Para entrar no WATCHLIST (não ser invalidado direto), precisa de **pelo menos 3 de 5**:

| Sinal | Threshold "Estrutura Preservada" |
|-------|----------------------------------|
| Acumulação ativa | `range_level:4h` >= 3 OU `range_level:1D` >= 3 |
| SM ainda presente | `T/OI` >= 40.000 (acima do p90 = interesse desproporcional) |
| Capital não saiu | `oi_trend` >= 0 (OI neutro ou crescendo) |
| Força estrutural | `exp_btc:1D` > 0 (ainda positivo vs BTC no longo prazo) |
| Varejo ainda short | `lsr` < 1.0 OU `lsr_trend` < 0 |

Se < 3 critérios: vai direto para INVALIDATED.

### Configurações do PCL (por sessão)

```sql
-- adicionado em eassets_bot_config:
pcl_enabled          BOOLEAN  NOT NULL DEFAULT TRUE,   -- ativa/desativa o loop
pcl_cooldown_minutes INTEGER  NOT NULL DEFAULT 30,     -- pausa após stop antes de re-verificar
pcl_max_attempts     SMALLINT NOT NULL DEFAULT 3,      -- max re-entradas por moeda
pcl_min_struct_score SMALLINT NOT NULL DEFAULT 3,      -- mínimo de critérios estruturais (de 5)
pcl_profit_target_usd NUMERIC(18,6) DEFAULT NULL,      -- PnL acumulado alvo para sair do loop
```

### Lógica do Loop PCL (Rust — tokio task)

```
PCL tick (a cada 60s)
    │
    ▼
Para cada moeda em WATCHLIST com cooldown_until < NOW():
    │
    ├─ Busca sinais atuais (bybit_rest / cache WS)
    │
    ├─ Verifica Estrutura Preservada (5 critérios)
    │   ├─ < pcl_min_struct_score → INVALIDATED, log, remove
    │   └─ >= pcl_min_struct_score → continua
    │
    ├─ Aplica checklist completo (7 filtros) + BTC em reset
    │   ├─ falhou → permanece WATCHLIST, atualiza last_check_at
    │   └─ passou → move para CANDIDATE
    │
    └─ CANDIDATE → decision_engine.try_open() (mesma lógica de entrada normal)
            │
            └─ increment attempt_count, reset cooldown_until, salva no banco
```

### Integração no Fluxo Principal

Quando `risk_manager` fecha uma posição por stop:

```rust
// risk_manager.rs
async fn on_stop_triggered(position: &Position, config: &BotConfig, db: &Pool) {
    if !config.pcl_enabled { return; }
    if position.attempt_count >= config.pcl_max_attempts { return; }

    let signals = fetch_current_signals(&position.symbol).await;
    let struct_score = evaluate_structural_persistence(&signals);

    if struct_score >= config.pcl_min_struct_score {
        // Entra no watchlist com cooldown
        upsert_watchlist(db, WatchlistEntry {
            symbol: position.symbol,
            state: WatchlistState::Cooldown,
            cooldown_until: Utc::now() + Duration::minutes(config.pcl_cooldown_minutes),
            attempt_count: position.attempt_count + 1,
            // snapshot dos indicadores estruturais agora
            stop_range_4h: signals.range_4h,
            stop_range_1d: signals.range_1d,
            stop_exp_btc_1d: signals.exp_btc_1d,
            stop_toi: signals.toi,
            ...
        }).await;
    } else {
        log_invalidated(&position.symbol, struct_score, &signals).await;
    }
}
```

### Nova Tabela no `eassets_order_logs` para PCL

Eventos específicos do loop persistente (facilitam debug e análise):

| `event` | Descrição |
|---------|-----------|
| `PCL_ADDED` | Moeda entrou no watchlist após stop |
| `PCL_COOLDOWN_START` | Início do cooldown |
| `PCL_CHECK_PASSED` | Verificação estrutural passou |
| `PCL_CHECK_FAILED` | Verificação estrutural falhou (com razão) |
| `PCL_REENTRY` | Nova entrada disparada pelo loop |
| `PCL_INVALIDATED` | Removida do loop (com razão) |
| `PCL_COMPLETED` | Lucro alvo atingido, encerrado |
| `PCL_MAX_ATTEMPTS` | Circuit breaker ativado |

### Novo Módulo no Rust Core

```
rust_core/src/
└── trading/
    ├── ...
    └── watchlist_manager.rs   # NOVO — PCL state machine + loop de re-verificação
```

### Novo Endpoint na API Python

```
GET  /api/eassets/watchlist              # Lista moedas em monitoramento persistente
GET  /api/eassets/watchlist/{symbol}     # Histórico de tentativas por moeda
POST /api/eassets/watchlist/{symbol}/remove  # Remove manualmente do loop
```

---

## Engine de Sinais Encryptos (Rust)

### Checklist de Pré-Operação (todos obrigatórios)

| # | Sinal | Condição de Aprovação |
|---|-------|----------------------|
| 1 | **Reset BTC** | RSI BTC 30m ou 1h ≤ `max_rsi_btc` (default 40) |
| 2 | **Exponential BTC** | `exp_btc` positivo em 5m, 15m e 1h simultaneamente |
| 3 | **Aceleração TPM** | `trades_minute` > `min_tpm` (default 800) OU salto ≥ 4x em 2 min |
| 4 | **LSR favorável** | `lsr` < `max_lsr` (default 1.0) OU em queda clara |
| 5 | **Combustível OI** | `oi_trend` positivo (dinheiro novo entrando) |
| 6 | **Posições disponíveis** | `posições_abertas` < `max_positions` |

### Score Final (0–100)

```
score = (
    30% × normalized(exp_btc)      +
    25% × normalized(trades_min)   +
    20% × normalized(oi_trend)     +
    15% × normalized(1.0 - lsr)    +
    10% × normalized(range_level)
)
```

### Fluxo de Decisão (loop Rust — tokio async)

```
Tick do mercado (a cada ~2s via WS)
    │
    ▼
btc_monitor::check_reset()
    ├─ RSI BTC > max_rsi_btc → BLOQUEADO
    └─ RSI BTC ≤ max_rsi_btc → CONTINUA
            │
            ▼
    scorer::score_all_symbols()
            │
            ▼
    signal_filter::apply_checklist(symbol)
        (todos os 6 filtros devem passar)
            │
            ▼
    decision::try_open(symbol, score)
        ├─ posições abertas ≥ max_positions → SKIP
        └─ score ≥ min_score → ABRE POSIÇÃO
                │
                ▼
        bybit_executor::open_position(symbol, direction, size)
                │
                ▼
        position_manager::save(position) → PostgreSQL
                │
                ▼
        risk_manager::spawn_monitor(position)
            ├─ stop_loss atingido → fecha
            ├─ take_profit atingido → fecha
            ├─ trailing_stop atingido → fecha
            └─ sinal de saída → fecha
```

---

## Migração SQLite → PostgreSQL

```
python_api/db/migrations/002_migrate_sqlite_data.py

Fluxo:
1. Ler trading_bot.db (bot_taxa_cripto-main/backend/)
2. Mapear campos → schema eassets_*
3. Inserir em lote no PostgreSQL (executemany asyncpg)
4. Verificar contagem pré/pós migração
5. Log de erros por linha
```

> Execução única via: `docker compose run python_api python -m db.migrations.002_migrate_sqlite_data`

---

## API Endpoints (Python)

```
POST   /api/eassets/bot/start              # Inicia sessão (chama Rust core)
POST   /api/eassets/bot/stop/{config_id}   # Para sessão
GET    /api/eassets/bot/status             # Status de todas as sessões ativas
GET    /api/eassets/bot/status/{config_id} # Status detalhado

GET    /api/eassets/positions              # Posições abertas
GET    /api/eassets/trades                 # Histórico de trades
GET    /api/eassets/trades/{symbol}        # Trades por moeda
GET    /api/eassets/logs/{config_id}       # Logs de ordens

GET    /api/eassets/market/signals         # Score Encryptos de todas as moedas agora
GET    /api/eassets/market/btc-status      # RSI BTC atual (reset ou não)

POST   /api/eassets/config                 # Salva configuração
GET    /api/eassets/config/{config_id}     # Lê configuração

GET    /api/eassets/watchlist              # Lista moedas no PCL (com estado, tentativas, cooldown)
GET    /api/eassets/watchlist/{symbol}     # Histórico de tentativas da moeda no loop
DELETE /api/eassets/watchlist/{symbol}     # Remove manualmente do loop
```

---

## Fases de Desenvolvimento

### Fase 1 — Infraestrutura
- [x] Criar pasta `bot_encryptos/` neste diretório
- [x] `docker-compose.yml` com serviços: rust_core, python_api, eassets_scraper, db, nginx
- [x] `.env.example` com todas as variáveis
- [x] Migration `001_create_eassets_tables.sql`
- [x] `database.py` Python + `postgres.rs` Rust (ambos conectam ao mesmo PostgreSQL)

### Fase 2 — Dados de Mercado (Rust)
- [x] `bybit_rest.rs` — tickers, OI, LSR, funding, klines com cache TTL
- [x] `bybit_ws.rs` — WebSocket publicTrade (tokio-tungstenite), DashMap+AtomicU64
- [x] `btc_monitor.rs` — RSI Wilder 14p em 30m/1h, atualiza a cada 30s

### Fase 3 — Engine Encryptos (Rust)
- [x] `scorer.rs` — score 0–100 (30/25/20/15/10)
- [x] `signal_filter.rs` — checklist 6 filtros obrigatórios
- [x] `decision.rs` — loop 2s, coleta sinais → filtros → score → abre posição

### Fase 4 — Execução de Ordens (Rust)
- [x] `bybit_executor.rs` — HMAC-SHA256 signed, Bybit v5 REST
- [x] `position_manager.rs` — DashMap em memória + persistência PostgreSQL via sqlx
- [x] `risk_manager.rs` — tokio task por posição (stop/TP/trailing a cada 1s)
- [x] **hook de stop → chama `watchlist_manager::on_stop_triggered()`**

### Fase 4b — PCL: Persistent Candidate Loop (Rust)
- [x] `watchlist_manager.rs` — máquina de estados WATCHLIST/COOLDOWN/CANDIDATE/INVALIDATED/COMPLETED
- [x] `structural_validator.rs` — 5 critérios de persistência estrutural + tracker de streak
- [x] Tabela `eassets_watchlist` na migration `001_create_eassets_tables.sql`
- [x] Loop PCL: tokio task a cada 60s, verifica moedas com cooldown expirado
- [x] Re-entrada via `decision_engine::try_open()` com `attempt_count` incrementado
- [x] Logs PCL em `eassets_order_logs` (PCL_ADDED, PCL_REENTRY, PCL_INVALIDATED, etc.)

### Fase 5 — API Python + Scraper + Migração
- [x] `routes_bot.py`, `routes_trades.py`, `routes_config.py`, `routes_scraper.py`
- [x] `rust_bridge.py` — cliente httpx para controlar Rust core
- [x] `eassets_scraper.py` — portado do eassets-main + `ingest_snapshot()`
- [x] `eassets_loop.py` — loop asyncio com state global e `trigger_now()`
- [x] `Dockerfile.scraper` — imagem Playwright + Chromium
- [x] `main.py` FastAPI com lifespan
- [x] `002_migrate_sqlite_data.py` — migração SQLite → PostgreSQL
- [x] Tabela `eassets_raw_snapshots` na migration `001`

### Fase 5b — Frontend (Next.js)
**Stack:** Next.js 15 (App Router) · Tailwind CSS · shadcn/ui · Lucide icons · Recharts

```
bot_encryptos/frontend/
├── app/
│   ├── layout.tsx              # Layout raiz + ThemeProvider
│   ├── page.tsx                # Dashboard principal (redirect → /dashboard)
│   ├── dashboard/
│   │   └── page.tsx            # Visão geral: engine status, posições, PnL do dia
│   ├── positions/
│   │   └── page.tsx            # Posições abertas em tempo real
│   ├── trades/
│   │   └── page.tsx            # Histórico de trades com filtros
│   ├── signals/
│   │   └── page.tsx            # Score Encryptos por moeda + status BTC reset
│   ├── watchlist/
│   │   └── page.tsx            # PCL — moedas em monitoramento persistente
│   ├── scraper/
│   │   └── page.tsx            # eAssets scraper: status, captura manual, histórico
│   └── config/
│       └── page.tsx            # Configurações do bot (capital, leverage, thresholds)
├── components/
│   ├── ui/                     # shadcn/ui components
│   ├── layout/
│   │   ├── sidebar.tsx
│   │   └── header.tsx
│   ├── dashboard/
│   │   ├── engine-status-card.tsx
│   │   ├── btc-reset-badge.tsx
│   │   ├── pnl-summary.tsx
│   │   └── positions-table.tsx
│   ├── signals/
│   │   ├── signals-table.tsx
│   │   └── score-bar.tsx
│   └── charts/
│       ├── pnl-chart.tsx       # Recharts — PnL acumulado
│       └── trades-chart.tsx
├── lib/
│   ├── api.ts                  # Fetch wrapper → python_api :8000
│   └── types.ts                # Tipos TypeScript espelhando as tabelas eassets_*
├── hooks/
│   └── use-polling.ts          # Polling genérico com SWR/interval
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

**Páginas principais:**
| Rota | Conteúdo |
|------|----------|
| `/dashboard` | Cards: engine ON/OFF, BTC reset status, posições abertas, PnL dia/total |
| `/positions` | Tabela live de posições: símbolo, direção, preço entrada, PnL atual, SL/TP |
| `/trades` | Histórico paginado, filtro por símbolo/data, PnL por trade |
| `/signals` | Ranking de moedas por score Encryptos, badges de filtros passados/falhos |
| `/watchlist` | PCL — estado de cada moeda, tentativas, cooldown restante |
| `/scraper` | Status do loop eAssets, botão "Capturar agora", histórico de capturas |
| `/config` | Formulário completo de `eassets_bot_config` (capital, leverage, thresholds) |
| `/analise/alpha` | Cadastro/remoção de moedas Binance Alpha e badge Alpha no painel |

- [ ] Criar `bot_encryptos/frontend/` com estrutura Next.js 15
- [ ] Integrar com `python_api` via `NEXT_PUBLIC_API_URL`
- [ ] Adicionar serviço `frontend` no `docker-compose.yml`

### Fase 6 — Deploy VPS
- [ ] Testar `docker compose up --build` localmente
- [ ] Configurar `.env` na VPS
- [ ] Deploy: `git pull && docker compose up -d --build`
- [ ] Verificar logs de todos os containers

### Fase 7 — Parâmetros de Entrada/Saída
> **A definir em sessão futura** com base em backtest/análise:
> - Quais moedas monitorar
> - Thresholds exatos (RSI BTC, score mínimo, TPM mínimo)
> - Lógica de saída (tempo fixo vs sinal de reversão Encryptos)
> - Alavancagem padrão por perfil de risco

---

## Variáveis de Ambiente

Arquivo `.env.local` criado na raiz deste diretório com **todos os valores reais** consolidados de todos os projetos. Copiar para `bot_encryptos/.env` antes de rodar.

> **NUNCA versionar `.env.local` ou `.env`.** Adicionar ambos ao `.gitignore`.

| Grupo | Variáveis-chave |
|-------|----------------|
| **PostgreSQL** | `DATABASE_URL`, `POSTGRES_USER/PASSWORD/DB/HOST/PORT` |
| **Bybit API** | `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `BYBIT_BASE_URL` |
| **eAssets Scraper** | `EASSETS_EMAIL`, `EASSETS_PASSWORD`, `EASSETS_INTERVAL_SECONDS`, `EASSETS_HEADLESS` |
| **Gemini AI** | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| **Telegram** | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_PARSE_MODE` |
| **Coinalyze** | `COINALYZE_API_KEY`, `COINALYZE_BASE_URL`, `COINALYZE_SERVICE_URL` |
| **Portas internas** | `RUST_CORE_PORT=8001`, `PYTHON_API_PORT=8000`, `SCRAPER_PORT=8002` |
| **Bot defaults** | `DEFAULT_LEVERAGE`, `DEFAULT_MAX_POSITIONS`, `DEFAULT_MIN_SCORE` |

---

## Dependências

### Rust (`Cargo.toml`)
```toml
[dependencies]
tokio          = { version = "1", features = ["full"] }
tokio-tungstenite = "0.21"
reqwest        = { version = "0.11", features = ["json"] }
sqlx           = { version = "0.7", features = ["postgres", "runtime-tokio-native-tls", "bigdecimal"] }
serde          = { version = "1", features = ["derive"] }
serde_json     = "1"
axum           = "0.7"          # API interna HTTP
hmac           = "0.12"         # Assinar requests Bybit
sha2           = "0.10"
hex            = "0.4"
tracing        = "0.1"
tracing-subscriber = "0.3"
dotenv         = "0.15"
```

### Python (`requirements.txt`)
```txt
fastapi
uvicorn[standard]
asyncpg
python-dotenv
httpx
loguru
playwright          # scraper eAssets (Dockerfile.scraper tem Chromium pré-instalado)
```

> Python não usa CCXT — execução de ordens é 100% Rust. CCXT removido do caminho crítico.
> O scraper roda em container separado (`eassets_scraper`) com imagem Playwright oficial.

---

## Notas Importantes

1. **Rust escreve direto no PostgreSQL** via `sqlx` — sem passar pelo Python para dados críticos
2. **Python só lê** o banco para servir a API REST e gerenciar configurações
3. **Tabelas `real_*` existentes** coexistem sem conflito — banco compartilhado
4. **Deploy final na VPS**: `docker compose up -d --build` — zero configuração manual
5. **Migração SQLite**: executada uma única vez antes do primeiro deploy
6. **Parâmetros de entrada/saída**: Fase 7, definidos após análise de backtest
