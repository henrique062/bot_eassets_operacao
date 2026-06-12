# Arquitetura: IA para Blacklist Inteligente + Criação de Bot via IA

> Implementado em: 2026-02-28
> Arquivos principais: `backend/symbol_blacklist.py`, `backend/ai_service.py`, `backend/routes.py`, `backend/real_trader.py`, `frontend/src/components/SmartReport.jsx`

---

## Visão Geral

Duas features de IA foram adicionadas ao sistema de Funding Rate Sniping:

1. **Blacklist Inteligente**: rastreia losses consecutivos por símbolo e pede à IA para decidir um cooldown automático
2. **Criação de Bot via IA**: a partir de um relatório de análise existente, a IA gera uma configuração de bot otimizada que é pré-preenchida no formulário de criação

---

## Feature 1: Blacklist Inteligente de Símbolos

### Fluxo Completo

```
Trade fechado no real_trader.py
        │
        ▼
on_trade_closed(user_id, symbol, config_id, total_pnl)   [symbol_blacklist.py]
        │
        ├── total_pnl >= 0 → zera consecutive_losses no banco
        │
        └── total_pnl < 0 → conta losses consecutivos (query real_trades)
                    │
                    └── consecutive_losses >= 3 (THRESHOLD)?
                                │
                                ├── NÃO → apenas salva o streak atual
                                │
                                └── SIM → asyncio.create_task(
                                              _analyze_and_maybe_blacklist(...)
                                          )
                                                   │
                                                   ▼
                                        analyze_symbol_for_blacklist()   [ai_service.py]
                                        (Gemini recebe últimos 10 trades)
                                                   │
                                                   ▼
                                        Resposta JSON da IA:
                                        {
                                          "should_blacklist": true/false,
                                          "cooldown_hours": 0|4|8|12|24,
                                          "reason": "...",
                                          "analysis": "..."
                                        }
                                                   │
                                        should_blacklist = true?
                                                   │
                                        ├── SIM → INSERT/UPDATE symbol_blacklist
                                        │          blacklisted_until = NOW + cooldown_hours
                                        │          invalida cache do usuário
                                        │
                                        └── NÃO → apenas loga a decisão, sem bloqueio
```

### Como a Blacklist filtra símbolos automáticos

```
_monitoring_loop / start_trading
        │
        ▼
_resolve_auto_symbols(service, exchange, strategy)   [real_trader.py]
        │
        ├── busca funding rates
        ├── aplica scoring
        ├── filtra por score/mode/direction
        ├── ordena candidatos
        ├── pega top N símbolos (maxSymbols)
        │
        └── get_blacklisted_symbols(user_id)   ← cache TTL 30s
                    │
                    └── filtra símbolos bloqueados do resultado
                                │
                                ▼
                    _auto_symbols_cache[key] = selected (filtrado)
```

### Detecção de Anomalia em _execute_snipe

Antes de abrir qualquer posição, se `|fundingRatePercent| > 5.0%`:
- Log WARNING no banco (`real_order_logs`)
- Snipe cancelado com motivo `"anomaly_detected"`

Isso protege contra dados corrompidos ou manipulação de mercado.

### Banco de Dados

```sql
symbol_blacklist:
  - user_id        (FK → users.id)
  - symbol         (VARCHAR 30)
  - consecutive_losses (INT)
  - blacklisted_until  (TIMESTAMPTZ) -- NULL se IA decidiu não bloquear
  - ai_reason      (VARCHAR 300)
  - ai_analysis    (TEXT)
  - cleared_manually (BOOLEAN)
  - UNIQUE(user_id, symbol)
```

### Endpoints REST

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/symbols/blacklist` | Lista blacklists do usuário atual |
| DELETE | `/api/symbols/blacklist/{symbol}` | Remove manualmente um bloqueio |

### Cache e Performance

- `get_blacklisted_symbols(user_id)` usa cache em memória com TTL de 30 segundos
- A análise da IA é sempre `asyncio.create_task` (fire-and-forget) — não bloqueia o fechamento da posição
- O filtro na `_resolve_auto_symbols` só consulta o cache, não o banco direto
- A blacklist filtra **apenas modos automáticos** — modo manual não é bloqueado (apenas loga aviso)

### Limites e Segurança

- Todas as funções em `symbol_blacklist.py` têm `try/except` global — **nunca quebram o fluxo de trading**
- Threshold configurável via constante `LOSS_THRESHOLD = 3`
- IA só pode retornar cooldown de 0/4/8/12/24 horas — valores inválidos são convertidos para 0
- `cleared_manually = TRUE` remove o bloqueio permanentemente (a IA não pode reverter)

---

## Feature 2: Criação de Bot via IA

### Fluxo Completo

```
Usuário está em SmartReport (página "Análise IA")
        │
        ├── Gera ou seleciona um relatório existente
        │
        └── Clica "Criar Bot com IA" (botão abaixo das moedas recomendadas)
                    │
                    ▼
            Modal de configuração
            ┌─────────────────────────┐
            │ Capital (USDT)          │ → ex: $200
            │ Alavancagem             │ → ex: 5x
            │ Exchange                │ → Binance / Bybit
            └─────────────────────────┘
                    │
                    ▼ (clique em "Gerar e Pré-preencher")
            generateBotConfigFromAI(reportId, {capital, leverage, exchange})
                    │ [api.js]
                    ▼
            POST /api/ai/generate-bot-config
                    │ [routes.py]
                    ▼
    ┌───────────────────────────────────────────┐
    │ 1. Busca recommended_coins do ai_reports  │
    │ 2. Busca historical_stats de trades       │
    │    bem-sucedidos do usuário (avg stopLoss │
    │    fee_type mais usado)                   │
    │ 3. Chama generate_bot_config() no Gemini  │
    └───────────────────────────────────────────┘
                    │
                    ▼
            generate_bot_config(recommended_coins, capital, leverage, ...)
            [ai_service.py]
                    │
                    ├── Sizing dinâmico por confiança:
                    │    FORTE    → 100% do capital
                    │    MODERADO → 80% do capital
                    │    FRACO    → 60% do capital
                    │
                    ├── Detecção de Regime de Mercado no prompt:
                    │    Calmo    → entrySeconds menor, stopLoss maior
                    │    Volátil  → stopLoss mais justo, makerTimeout menor
                    │    Tendência → autoMaxSymbols maior na direção dominante
                    │
                    └── Gemini retorna JSON compatível com start_trading():
                        {
                          "sessionName": "IA-Bot-BINANCE-1430",
                          "symbols": ["BTCUSDT", "ETHUSDT"],
                          "operationMode": "auto_strongest",
                          "entrySeconds": 25,
                          "exitSeconds": 45,
                          "stopLossPct": 2.5,
                          "autoMinScore": 55,
                          "autoMaxSymbols": 5,
                          "feeType": "maker",
                          "capital": 160.00,
                          "leverage": 5,
                          "ai_justification": "..."
                        }
                    │
                    ▼ (retorno para o frontend)
            Modal fecha
                    │
                    ▼
    onCreateBotFromAI(config) → App.jsx
                    │
                    ▼
    handleCreateBotFromAI:
        setPrefilledStrategy(config)
        setPage('real-trading')
                    │
                    ▼
    RealTradingPage recebe prefilledConfig
    (formulário pré-preenchido pela IA)
    Usuário revisa → confirma criação do bot
```

### Sizing Dinâmico (Bônus IA #4)

A confiança da moeda com maior score no relatório determina quanto do capital será sugerido:

| Confiança da Top Moeda | Capital Sugerido |
|------------------------|-----------------|
| FORTE | 100% do capital informado |
| MODERADO | 80% do capital informado |
| FRACO | 60% do capital informado |

O usuário pode revisar e alterar antes de confirmar.

### Endpoint REST

| Método | Rota | Body | Resposta |
|--------|------|------|---------|
| POST | `/api/ai/generate-bot-config` | `{ reportId, capital, leverage, exchange, operationMode? }` | `{ config: {...}, ai_justification: "..." }` |

**Não inicia o bot automaticamente** — apenas retorna a configuração para revisão.

### Historical Stats (Parâmetros de Sucesso do Usuário)

A rota busca os últimos 50 trades lucrativos do usuário para alimentar o prompt da IA:

```sql
SELECT rc.stop_loss_pct, rc.fee_type
FROM real_trades rt
JOIN real_config rc ON rc.id = rt.config_id
WHERE rc.user_id = $1 AND rt.total_pnl > 0
ORDER BY rt.trade_timestamp DESC
LIMIT 50
```

Calcula: `avgStopLossPct`, `mostUsedFeeType`, `totalWinningTrades`.

---

## Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND                                    │
│                                                                      │
│  SmartReport.jsx                                                     │
│  ├── Botão "Criar Bot com IA"  → openBotModal()                      │
│  ├── Modal de configuração     → handleCreateBotWithAI()             │
│  └── generateBotConfigFromAI() → api.js → POST /api/ai/generate-bot │
│                                                                      │
│  App.jsx                                                             │
│  ├── handleCreateBotFromAI(config) → prefilledStrategy               │
│  └── setPage('real-trading') → RealTradingPage com form pré-preench. │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          │ HTTP
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           BACKEND                                    │
│                                                                      │
│  routes.py (_ai_router)                                              │
│  ├── GET  /symbols/blacklist        → symbol_blacklist.get_user_blacklist()  │
│  ├── DELETE /symbols/blacklist/{s}  → symbol_blacklist.clear_symbol_blacklist() │
│  └── POST /ai/generate-bot-config   → ai_service.generate_bot_config()      │
│                                                                      │
│  real_trader.py                                                      │
│  ├── _build_auto_strategy()    → propaga user_id                    │
│  ├── _resolve_auto_symbols()   → filtra blacklisted symbols          │
│  ├── _execute_snipe()          → detecção de anomalia (>5%)         │
│  └── _monitor_and_close_position() → on_trade_closed() fire-forget  │
│  └── sync_loop()               → on_trade_closed() fire-forget      │
│                                                                      │
│  symbol_blacklist.py                                                 │
│  ├── on_trade_closed()         → atualiza streak de losses           │
│  ├── _analyze_and_maybe_blacklist() → chama ai_service               │
│  ├── get_blacklisted_symbols() → cache TTL 30s                       │
│  ├── get_user_blacklist()      → listagem para a API                 │
│  └── clear_symbol_blacklist()  → remoção manual                      │
│                                                                      │
│  ai_service.py                                                       │
│  ├── analyze_symbol_for_blacklist()  → Gemini (decisão de cooldown)  │
│  └── generate_bot_config()           → Gemini (config de bot)        │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          │ asyncpg
                          ▼
┌──────────────────────────┐          ┌──────────────────┐
│  symbol_blacklist table  │          │  ai_reports table │
│  (PostgreSQL)            │          │  recommended_coins│
└──────────────────────────┘          └──────────────────┘
                          │
                          │ HTTPS
                          ▼
              ┌──────────────────────┐
              │   Google Gemini API  │
              │   (GEMINI_MODEL env) │
              └──────────────────────┘
```

---

## Prompts da IA

### Prompt: analyze_symbol_for_blacklist

**Input**: últimos 10 trades do símbolo + estatísticas (wins/losses, PnL total)
**Output JSON**:
```json
{
  "should_blacklist": true,
  "cooldown_hours": 8,
  "reason": "Texto curto (<200 chars)",
  "analysis": "Análise detalhada em markdown"
}
```

**Temperatura**: 0.3 (conservadora — evita decisões impulsivas)
**Política**: só bloqueia se losses são estruturais, não aleatórios

### Prompt: generate_bot_config

**Input**: moedas recomendadas + parâmetros do usuário + historical_stats + análise de regime
**Output JSON**: configuração completa compatível com `start_trading()`
**Temperatura**: 0.4 (levemente criativa para variar parâmetros)

---

## Como Testar

### Blacklist
```bash
# 1. Forçar 3 losses no mesmo símbolo → ver log "[Blacklist] X bloqueado por Yh"
# 2. Verificar registro:
SELECT * FROM symbol_blacklist WHERE user_id = 1;

# 3. Remover manualmente:
DELETE /api/symbols/blacklist/BTCUSDT  (autenticado)

# 4. Verificar filtro automático:
# Nos logs de _resolve_auto_symbols: "[Blacklist] Filtrados N símbolo(s) bloqueados"
```

### Criar Bot via IA
```bash
# 1. Ir em "Análise IA" → gerar novo relatório
# 2. Ver seção "Estratégias Refinadas pela IA"
# 3. Clicar "Criar Bot com IA"
# 4. Preencher capital (≥$10), alavancagem, exchange
# 5. Clicar "Gerar e Pré-preencher" → aguardar Gemini (~10-30s)
# 6. Formulário em "Conta Real" estará pré-preenchido para revisão
```

### Anomaly Detection
```bash
# Símbolo com funding > 5% → verificar em real_order_logs:
SELECT * FROM real_order_logs WHERE event_type = 'anomaly_detected';
```

---

## Limitações e Observações

- **Gemini é assíncrono e lento**: chamadas levam 10-30s — aguardar o spinner no botão
- **Blacklist não bloqueia modo manual**: apenas modos `auto_*` e `counter_trend` são filtrados
- **IA não é infalível**: a configuração gerada deve ser revisada antes de iniciar
- **Backend deve ser reiniciado** após deploy para novas rotas serem registradas
- **Cache de blacklist é in-memory**: reiniciar o servidor limpa o cache (seguro, ele é reconstruído no próximo acesso)
