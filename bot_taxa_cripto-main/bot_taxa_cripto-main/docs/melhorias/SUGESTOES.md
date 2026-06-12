# Sugestões de Melhoria — Plataforma Vorxia

> Baseadas na auditoria quantitativa do período 25–26/02/2026 (86 trades reais).
> Ordenadas por prioridade: maior impacto e menor esforço primeiro.

---

## Prioridade

| # | Sugestão | Esforço | Impacto | Status |
|---|---|---|---|---|
| 1 | [Notificações Telegram](#1-notificações-telegram) | Baixo | Alto | Pendente |
| 2 | [Heartbeat do Bot](#2-heartbeat-do-bot) | Baixo | Alto | Pendente |
| 3 | [Auto-Compound do Lucro](#3-auto-compound-do-lucro) | Médio | Alto | Pendente |
| 4 | [Painel de Performance Real](#4-painel-de-performance-real) | Médio | Médio | Pendente |
| 5 | [Filtro de Correlação entre Posições](#5-filtro-de-correlação-entre-posições) | Médio | Médio | Pendente |
| 6 | [Score Recalibrado por Dados Reais](#6-score-recalibrado-por-dados-reais) | Alto | Alto | Pendente |

---

## 1. Notificações Telegram

### Problema
O bot opera 24h mas você não monitora 24h. Hoje você só descobre o que aconteceu quando abre a tela manualmente.

### O que notificar
- **Posição aberta:** símbolo, direção, score, funding rate
- **Posição fechada:** PNL líquido, motivo de saída (trailing, stop, funding, etc.)
- **Erro crítico:** margin insufficient, API error, race condition, bot parado
- **Sinal forte sem bot ativo:** Score CT ≥ 90 apareceu mas nenhum bot está rodando para capturar

### Como implementar
1. Criar um bot no Telegram via `@BotFather` (gratuito, leva ~2 minutos)
2. Adicionar `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `backend/.env`
3. Criar `backend/notifier.py` com função `send_alert(message: str)`
4. Chamar `send_alert()` nos pontos críticos do `real_trader.py`:
   - Ao abrir posição
   - Ao fechar posição (com PNL)
   - Em erros recorrentes (> 3 tentativas falhas)
   - Quando score CT ≥ 90 e nenhum bot counter_trend ativo

### Exemplo de mensagem
```
⚡ POSIÇÃO ABERTA
Bot: CT Precisa | STEEMUSDT SHORT
Score: 97 | Funding: -0.39%/ciclo
Capital: $10 | Leverage: 5x
Entrada: 0.06290 | 25/02 22:00

✅ FECHADA — trailing_stop
STEEMUSDT SHORT | +$0.86 (+13.5%)
Duração: 1min | Fee: $0.03
PNL Líquido: +$0.83
```

---

## 2. Heartbeat do Bot

### Problema
Se o bot travar ou parar por erro silencioso, você não sabe até abrir a tela. No período auditado, houve 4 race conditions e 29 erros de margem silenciosos.

### Como implementar
1. O `real_trader.py` escreve um timestamp no banco a cada 60s:
   ```sql
   UPDATE real_config SET last_heartbeat = NOW() WHERE id = $bot_id;
   ```
2. Uma task de monitoramento (cron a cada 2min ou task asyncio) verifica:
   ```sql
   SELECT id, name FROM real_config
   WHERE status = 'running'
   AND last_heartbeat < NOW() - INTERVAL '3 minutes';
   ```
3. Se encontrar bots com heartbeat velho → envia alerta Telegram + marca `status = 'error'`

### Schema necessário
```sql
ALTER TABLE real_config ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;
ALTER TABLE real_config ADD COLUMN IF NOT EXISTS error_count INT DEFAULT 0;
```

---

## 3. Auto-Compound do Lucro

### Problema
O sistema gerou +12.9% em 33h com capital fixo de $103. O capital permanece $103 no próximo ciclo — os juros compostos não são aproveitados.

### Como funciona
Ao encerrar uma sessão de bot, o sistema calcula o novo capital base:
```
capital_novo = capital_atual + (pnl_sessao * reinvestimento_pct)
```

Exemplo com 50% de reinvestimento:
- Sessão 1: capital $100, lucro $13 → novo capital $106.50
- Sessão 2: capital $106.50, lucro $13.80 → novo capital $113.40
- vs. capital fixo: sempre $100 → $113 acumulado no mesmo período

### Como implementar
1. Adicionar campo `auto_compound_pct` em `real_config` (0 = desativado, 0.5 = 50%)
2. Ao criar nova sessão com "Copiar Estratégia", calcular:
   ```python
   if config.auto_compound_pct:
       pnl_anterior = await get_session_pnl(previous_session_id)
       capital_novo = config.capital + (pnl_anterior * config.auto_compound_pct)
   ```
3. Exibir no formulário: campo "Auto-compound (%)" com toggle

### UI sugerida
```
Capital Total ($): [100]
Auto-compound:  [toggle ON]  Reinvestir [50]% do lucro na próxima sessão
Capital estimado próx. sessão: $106.50
```

---

## 4. Painel de Performance Real

### Problema
Hoje existem logs de operações, mas não há visão consolidada longitudinal. Impossível saber se uma estratégia está "morrendo" (edge desaparecendo) antes de perder capital.

### O que construir
- **Gráfico de PnL acumulado** por dia/semana/mês (equity curve)
- **Win rate e Profit Factor rolante** — últimos 7 dias vs últimos 30 dias
- **Drawdown atual** em relação ao pico histórico
- **Ranking de bots/estratégias** por retorno acumulado
- **Heatmap de horários** — quais horas do dia geram mais lucro (CT performa melhor em quais ciclos?)

### Dados já disponíveis no banco
Tudo está em `real_trades` — basta agregar:
```sql
SELECT
  DATE(close_time) as dia,
  SUM(net_pnl) as pnl_dia,
  COUNT(*) as trades,
  AVG(CASE WHEN net_pnl > 0 THEN 1.0 ELSE 0 END) as win_rate
FROM real_trades
GROUP BY DATE(close_time)
ORDER BY dia;
```

### Endpoint sugerido
`GET /api/performance?period=30d&bot_id=&mode=`

---

## 5. Filtro de Correlação entre Posições

### Problema identificado nos dados
No período auditado, o bot abriu **STEEMUSDT + SKRUSDT + ESPUSDT + POWERUSDT** todos em SHORT simultâneo. Se esses ativos são correlacionados (reagem ao mesmo movimento do mercado), você não tem 4 posições independentes — tem **1 aposta concentrada dividida em 4**.

Resultado: quando STEEMUSDT reverteu, todos os outros também reverteram juntos.

### Como implementar
Antes de abrir uma nova posição CT, calcular a correlação de preço dos últimos 3 dias entre o novo símbolo e as posições já abertas:

```python
async def is_too_correlated(new_symbol: str, open_positions: list, threshold=0.75) -> bool:
    prices_new = await get_price_series(new_symbol, days=3)
    for pos in open_positions:
        prices_existing = await get_price_series(pos.symbol, days=3)
        corr = pearson_correlation(prices_new, prices_existing)
        if corr > threshold:
            logger.info(f"Pulando {new_symbol}: correlação {corr:.2f} com {pos.symbol}")
            return True
    return False
```

### Parâmetro configurável
Adicionar `max_correlation` em `real_config` (padrão: 0.75). Se correlação > threshold → pular símbolo e tentar o próximo na lista.

---

## 6. Score Recalibrado por Dados Reais

### Problema
Os pesos do score foram definidos manualmente e nunca foram validados com dados reais:
```
Coleta de Taxa:  APY=40, Volume=20, Intervalo=10, Consistência=15
Counter-Trend:   Extremidade=40, Persistência=30, Volume=20, Volatilidade=10
```

A auditoria mostrou que a Coleta de Taxa tem **Profit Factor 0.88** (abaixo de 1). Isso pode indicar que os pesos estão mal calibrados — um pilar recebe muito peso mas tem baixa correlação real com lucro.

### Como calibrar
Com os dados já existentes no banco (`real_trades.entry_score_breakdown` + `real_trades.net_pnl`):

1. Extrair para cada trade: valor de cada pilar + PNL líquido
2. Calcular correlação de Spearman entre cada pilar e PNL
3. Redistribuir pesos proporcionalmente às correlações positivas

```python
# Exemplo de análise
import pandas as pd
from scipy.stats import spearmanr

df = pd.DataFrame(trades)  # entry_score_breakdown + net_pnl
correlations = {}
for pilar in ['apy', 'volume', 'interval', 'consistency']:
    corr, p_value = spearmanr(df[pilar], df['net_pnl'])
    correlations[pilar] = {'corr': corr, 'p_value': p_value}
```

### Resultado esperado
Pesos ajustados automaticamente com base em evidência — ex.: se `Consistência` tiver correlação 0.12 com PNL mas `APY` tiver 0.61, o novo peso seria APY≈50, Consistência≈5.

### Quando executar
Recalibrar após acumular ≥ 200 trades reais por modo. Hoje já há dados suficientes para uma primeira calibração.

---

## Correções Já Aplicadas (não são sugestões, já feitas)

| Correção | Data | Impacto |
|---|---|---|
| Bug `tp_limit_price` ausente em `real_positions` | 26/02/2026 | Elimina exchange_sync negativos |
| Migration `score_limits_counter` com funding_min=0.10% | 26/02/2026 | Filtra sinais CT fracos |
| Thresholds score Coleta: forte=82, moderado=70, fraco=50 | 26/02/2026 | Exige qualidade real |
| Estratégias reduzidas de 7 para 4 com configs otimizadas | 26/02/2026 | Remove estratégias sem edge |
