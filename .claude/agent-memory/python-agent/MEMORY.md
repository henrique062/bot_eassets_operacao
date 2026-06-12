# Bot Taxa Cripto — Memória do Agente Python

## Stack Principal
- Backend: FastAPI + asyncpg + CCXT (trading real) + Python 3.10+
- Frontend: React 19 + Vite
- DB: PostgreSQL em 69.62.92.189:5432

## Arquivos Críticos do Backend
- `backend/real_trader.py` — engine de trading real com CCXT
- `backend/paper_trader.py` — engine de paper trading (simulação)
- `backend/routes.py` — todos os endpoints da API (prefixo `/api`)
- `backend/scoring.py` — sistema de score 0-100 para funding rates
- `backend/auth.py` — JWT + bcrypt direto (sem passlib)

## Padrões de Bug Conhecidos

### real_trader.py — Bugs corrigidos em 2026-02-22
1. `_execute_snipe`: `fee_rate` não existe nesse escopo — usar `cfg.get("feeRate", 0.0002)`
2. `_execute_snipe`: variável `ex` pode ser `None` no bloco `except` — inicializar como `None` antes do `try`
3. `_execute_snipe`: após `await ex.close()`, setar `ex = None` para evitar double-close
4. `_monitoring_loop` do real_trader: não tratava `asyncio.CancelledError` — paper_trader trata corretamente
5. `close_all_positions` em real_trader: stub sem implementação real — marcado com TODO

### paper_trader.py — Bugs corrigidos em 2026-02-22
- `price_pnl_pct` calculada dentro do loop mas usada no INSERT fora — recalcular após o loop

## Convenções de Escopo do Projeto
- Conexões CCXT: sempre inicializar como `ex = None` antes do `try`, setar `ex = None` após `close()`
- Configurações de fee: acessar via `cfg.get("feeRate", 0.0002)` — nunca variável local `fee_rate`
- Todos os endpoints de trading real protegidos com `Depends(get_current_user)`
- `close_all_positions` em real_trader é stub — não executa ordens reais na exchange

## Módulos de Trading
- `_execute_snipe`: abre posição + agenda fechamento via `_monitor_and_close_position`
- `_monitoring_loop`: detecta oportunidades e dispara snipes via `asyncio.create_task`
- `_reconcile_with_exchange`: background task que reconcilia PnL estimado com dados reais

## Melhores Configurações de Paper Trading (análise do código)
- Modo: `auto_expiring` + `feeType: maker` + `leverage: 5`
- `entrySeconds: 30`, `exitSeconds: 30`, `stopLossPct: 1.0`
- Direção `both`, `autoMinScore: 50`
