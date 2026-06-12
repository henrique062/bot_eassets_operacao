# 🧠 Análise IA — Documentação

## O que é?

A feature de **Análise IA** usa o Google Gemini para avaliar o desempenho dos bots de real trading e sugerir ajustes de configuração.

A análise é **100% manual** — só é executada quando o usuário clica no ícone IA. Não consome tokens automaticamente.

---

## Onde Fica?

Tudo está na tela de **Logs** (`LogsPage.jsx`):

- **Aba "Bots"** → Coluna **Ações** → Ícone IA (roxo) dispara análise
- **Aba "🧠 Análises IA"** → Histórico de todas as análises feitas

---

## Fluxo

```
Logs → Aba "Bots" → Ícone IA na linha do bot → Modal de Análise → Aplicar Sugestões (opcional)
```

1. Usuário vai na tela de **Logs**
2. Na aba **Bots**, cada bot tem um ícone IA na coluna Ações
3. Ao clicar, abre o **Modal de Análise IA** que:
   - Chama `POST /api/real-trading/{session_id}/ai-analyze`
   - Mostra spinner enquanto a IA processa (~15s)
   - Exibe **análise em texto** + **tabela comparativa** (config atual vs sugestão)
   - Botão **"✅ Aplicar Sugestões"** para aceitar alterações
4. A análise é salva no banco e aparece na aba **"🧠 Análises IA"**

---

## Arquivos

### Backend

| Arquivo                                   | O que faz                                            |
| ----------------------------------------- | ---------------------------------------------------- |
| `ai_service.py` → `analyze_bot_cycle()`   | Monta prompt com contexto completo e chama Gemini    |
| `ai_service.py` → `_parse_bot_analysis()` | Parseia JSON da resposta                             |
| `routes.py` → `POST /ai-analyze`          | Busca trades + config → chama IA → salva no banco    |
| `routes.py` → `POST /ai-apply`            | Aplica sugestões via `edit_session()`                |
| `routes.py` → `GET /ai-analyses`          | Retorna histórico de análises                        |
| `main.py` → `lifespan()`                  | Auto-migração da tabela `bot_ai_analyses` no startup |

### Frontend

| Arquivo                            | O que faz                                                                   |
| ---------------------------------- | --------------------------------------------------------------------------- |
| `api.js`                           | `requestBotAIAnalysis()`, `applyBotAISuggestions()`, `fetchBotAIAnalyses()` |
| `LogsPage.jsx` → `BotsTable`       | Ícone IA na coluna Ações                                                    |
| `LogsPage.jsx` → `AIAnalysisModal` | Modal com análise, tabela comparativa e botão aplicar                       |
| `LogsPage.jsx` → `AIAnalysesTab`   | Aba com histórico de análises                                               |

---

## Banco de Dados

### Tabela: `bot_ai_analyses`

```sql
CREATE TABLE IF NOT EXISTS bot_ai_analyses (
    id SERIAL PRIMARY KEY,
    config_id INT REFERENCES real_config(id) ON DELETE CASCADE,
    analysis_text TEXT,
    suggested_config JSONB,
    applied BOOLEAN DEFAULT FALSE,
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    trigger_type VARCHAR(20) DEFAULT 'manual'
);
```

> Criada automaticamente no startup do servidor.

---

## O Prompt da IA

O prompt inclui **contexto completo**:

- Como funciona o funding rate sniping (fluxo completo)
- Todos os 5 modos de operação
- Sistema de scoring (0-100 pts)
- Significado de cada parâmetro configurável
- Motivos de fechamento e cálculo de PnL
- Configuração atual do bot
- Performance do ciclo (PnL, win rate, etc.)
- Últimos 20 trades detalhados

### Campos que a IA pode sugerir alterar:

`entrySeconds`, `exitSeconds`, `stopLossPct`, `minProfitPct`, `autoMaxSymbols`, `leverage`, `makerTimeoutSeconds`

---

## API Endpoints

| Método | Endpoint                                      | Descrição            |
| ------ | --------------------------------------------- | -------------------- |
| `POST` | `/api/real-trading/{id}/ai-analyze`           | Gera nova análise IA |
| `POST` | `/api/real-trading/{id}/ai-apply`             | Aplica sugestões     |
| `GET`  | `/api/real-trading/{id}/ai-analyses?limit=10` | Lista histórico      |

---

## Hot-Reload

Quando sugestões são aplicadas:

1. `POST /ai-apply` chama `edit_session()` do `real_trader.py`
2. Atualiza banco + memória em tempo real
3. Na próxima iteração do loop, novas configurações são usadas

**Não precisa reiniciar o servidor.**
