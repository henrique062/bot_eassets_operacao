---
name: rust-core-architecture
description: Decisões arquiteturais do rust_core bot_encryptos — motor de trading Bybit em Rust
metadata:
  type: project
---

# Rust Core — Arquitetura

**Localização:** `D:\3 - Projetos investimentos\Dash encryptos PHONIX Junho\bot_encryptos\rust_core\`

## Camadas
- `market/` — WebSocket (trades/s) + REST Bybit + BTC Monitor
- `engine/` — scorer, signal_filter, decision loop (2s)
- `trading/` — executor, position_manager, risk_manager, watchlist_manager, structural_validator
- `db/` — postgres pool via sqlx (sem `query!` para evitar DATABASE_URL em compile-time)

## Decisões-chave
- Usa `sqlx::query()` (dinâmico) em vez de `sqlx::query!()` (macro verificada) para não exigir conexão DB em CI/build
- `BtcMonitor::new()` retorna `(Arc<RwLock<BtcState>>, Arc<BtcMonitor>)` — state é compartilhado com decision loop
- `TradeCounter` usa `DashMap<String, (AtomicU64, Instant)>` para contagem lock-free de trades/s
- Score: 30% exp_btc + 25% tpm + 20% oi_trend + 15% (1-lsr) + 10% range_level (todos normalizados 0-1)
- PCL loop: tokio task a cada 60s; deadlock evitado soltando DashMap RefMut antes de chamar async fn
- `AppState` compartilhado via `Arc` em todos os handlers Axum e tasks

## Tabelas PostgreSQL (nomes exatos)
- `eassets_positions` — posições abertas/fechadas
- `eassets_trades` — histórico de trades completos
- `eassets_order_logs` — logs PCL (PCL_ADDED, PCL_REENTRY, PCL_INVALIDATED)
- `eassets_watchlist` — máquina de estados PCL por símbolo

## Portas
- rust_core: 8001 (RUST_CORE_PORT)
- python_api: 8000 (PYTHON_API_URL)

## Variáveis de ambiente obrigatórias
DATABASE_URL, BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_SYMBOLS

**Why:** Projeto novo criado do zero em 2026-06-11.
**How to apply:** Ao fazer qualquer alteração no rust_core, consultar este arquivo para manter consistência de nomes de tabelas, portas e padrões de código.
