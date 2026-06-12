# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projeto

Dashboard de Funding Rates para contratos perpétuos de criptomoedas (Binance + Bybit), com análise via IA (Google Gemini), backtesting e paper trading.

## Comandos

### Backend (Python/FastAPI)

```bash
# Instalar dependências
cd backend && pip install -r requirements.txt

# Iniciar servidor de desenvolvimento
cd backend && python main.py
# ou
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API disponível em `http://localhost:8000`. Documentação automática em `/docs`.

### Frontend (React/Vite)

```bash
cd frontend && npm install
npm run dev       # Servidor de desenvolvimento
npm run build     # Build de produção (gera frontend/dist/)
npm run lint      # Linting ESLint
npm run preview   # Preview do build
```

### Deploy (produção)

Após `npm run build`, copiar o conteúdo de `frontend/dist/` para `backend/static/`. O FastAPI serve os arquivos estáticos automaticamente se o diretório existir.

## Variáveis de Ambiente

Arquivo `backend/.env`:

- `GEMINI_API_KEY` — chave da API Google Gemini (obrigatória para `/api/ai-analysis`)
- `GEMINI_MODEL` — modelo Gemini a usar (padrão: `gemini-3-flash-preview`)
- `DATABASE_URL` — connection string PostgreSQL (ex: `postgres://user:pass@host:5432/db?sslmode=disable`)

## Banco de Dados (PostgreSQL)

Banco `vorxia` em `69.62.92.189:5432`. Tabelas:

| Tabela                   | Propósito                                                                        |
| ------------------------ | -------------------------------------------------------------------------------- |
| `paper_config`           | Configuração + saldo + flag `active` da sessão do paper trader (singleton ativo) |
| `paper_positions`        | Posições abertas (FK → paper_config). Persiste entre restarts do servidor        |
| `paper_trades`           | Histórico completo de trades. Campos em `NUMERIC` para precisão financeira       |
| `funding_rate_snapshots` | Snapshots periódicos (a cada 15 min) de todos os pares das 2 exchanges           |

O módulo `backend/database.py` gerencia o pool asyncpg. As funções `fetch`, `fetchrow`, `execute` e `executemany` são os helpers usados em todo o backend.

## Arquitetura

### Backend (`backend/`)

- **`main.py`** — FastAPI com `lifespan`: inicializa pool do banco, chama `maybe_resume_on_startup()` para reativar paper trader, e lança `_snapshot_loop()` em background. Middleware CORS e serving do frontend estático em produção.
- **`database.py`** — Pool asyncpg (2–10 conexões). Funções: `init_db()`, `close_db()`, `fetch()`, `fetchrow()`, `fetchval()`, `execute()`, `executemany()`.
- **`routes.py`** — Todos os endpoints sob o prefixo `/api`. Seleciona o serviço de exchange via parâmetro `?exchange=binance|bybit`.
- **`binance_service.py`** / **`bybit_service.py`** — Implementam a mesma interface de funções assíncronas: `get_all_funding_rates()`, `get_funding_history()`, `get_long_short_ratio()`, `get_klines()`, `get_stats()`. Cada função usa `TTLCache` da lib `cachetools` para evitar excesso de chamadas à API externa.
- **`scoring.py`** — Algoritmo de score risco/retorno (0–100). Fatores: magnitude do funding (0–30), risco/retorno vs. volatilidade (0–30), volume/liquidez (0–20), bônus de intervalo menor (0–10) e urgência do próximo settlement (−10 a +10). Vetos automáticos para volatilidade >35% ou volume <$2M.
- **`ai_service.py`** — Envia dados de mercado ao Google Gemini para gerar análise em markdown em PT-BR.
- **`backtester.py`** — Simula backtest histórico com dois modos: `normal` (usa variação de preço real via klines) e `sniping` (janela de ~30s, variação de preço ≈ 0). Calcula P&L considerando funding recebido, variação de preço e fees (maker 0.02% / taker 0.05%).
- **`paper_trader.py`** — Paper trading em tempo real. Loop assíncrono que monitora settlements e executa snipes virtuais. Estado persistido no PostgreSQL (tabelas `paper_config`, `paper_positions`, `paper_trades`). A função `maybe_resume_on_startup()` relança o loop automaticamente se `active=TRUE` no banco.

### Frontend (`frontend/`)

React 19 + Vite. O ponto de entrada é `frontend/src/main.jsx` → `App.jsx`.

### Endpoints da API

| Endpoint                                  | Descrição                                                |
| ----------------------------------------- | -------------------------------------------------------- |
| `GET /api/funding-rates`                  | Lista todas as taxas com score, suporta filtro/ordenação |
| `GET /api/funding-rates/{symbol}/history` | Histórico de funding de um símbolo                       |
| `GET /api/funding-rates/{symbol}/lsr`     | Long/Short Ratio de um símbolo                           |
| `GET /api/funding-rates/{symbol}/klines`  | Dados de candlestick                                     |
| `GET /api/batch-lsr`                      | LSR de múltiplos símbolos em paralelo                    |
| `GET /api/stats`                          | Estatísticas gerais do mercado                           |
| `GET /api/ai-analysis`                    | Análise de oportunidades via Gemini                      |
| `GET /api/backtest`                       | Executa backtest histórico                               |
| `GET/POST /api/paper-trading`             | Gerenciamento do paper trading                           |

### Padrão de adição de nova exchange

Para adicionar uma nova exchange, criar um novo módulo seguindo a interface de `binance_service.py`/`bybit_service.py` e registrá-la no dicionário `EXCHANGES` em `routes.py`.

## Github

Sempre suba as atualizações no git no final da tarefa. As mensagens de commit devem ser **sempre em português brasileiro** ("feat: adicionado...", "fix: corrigido erro...", "refactor: melhorado...", etc). Faça o push para o repositório remoto (`git push`).

**Nunca pule essa opção** Sempre execute e suba no git ao final de cada tarefa.

## Alterações no codigo

**Nunca pule essa opção** Sempre que for realizar qualquer ação ou alteração no codigo, faça o comentario da parte que está sendo editada, alterada ou incluinda, para melhor controle do motivo daquela alteração