# Plano de Ação — Novas Estratégias e Melhorias de Score
> Gerado em: 2026-02-28 | Baseado em análise histórica de 413 trades + pesquisa quantitativa

---

## Visão Geral

Este documento consolida o plano de evolução do bot em três frentes:

1. **Infraestrutura de dados** — liquidações e OI em tempo real (base para tudo)
2. **Melhorias de score** — RSI, OI crescente, predicted funding rate
3. **Novas estratégias** — Flip Momentum, CVD Divergence, Cross-Exchange Arb

### Legenda de prioridade
- 🔴 **P0** — base necessária para as demais frentes
- 🟡 **P1** — alto impacto, baixo/médio esforço
- 🔵 **P2** — médio impacto ou maior esforço
- ⚪ **P3** — futuro / pesquisa adicional necessária

---

## Resumo Executivo — O que os dados mostraram hoje

| Descoberta | Implicação |
|---|---|
| 95% do lucro vem de `price_pnl`, não de `funding_pnl` | Score deve refletir qualidade de entrada de preço, não só taxa |
| Taxa > 1%/ciclo → win rate 41% (pior faixa) | Filtro de taxa máxima ✅ (já implementado hoje) |
| Faixa 0.5–1%/ciclo → win rate 64% (melhor) | Novo teto do score APY |
| Consistência histórica alta → resultado pior | Peso reduzido de 25 → 13 ✅ (já implementado hoje) |
| Momentum acelerando → PnL negativo | Peso reduzido e invertido ✅ (já implementado hoje) |
| Bug de margin insufficient em abertura paralela | Corrigido via in-memory session ✅ |
| Race condition pós-cancelamento maker | Corrigido com sleep(1) ✅ |
| DB balance desatualizado durante abertura | Corrigido via `available_balance` ✅ |

---

## FRENTE 1 — Infraestrutura de Dados (Liquidações + OI)

> Base necessária para as estratégias avançadas. Sem esses dados, as frentes 2 e 3 ficam incompletas.

### 1.1 — Stream de Liquidações em Tempo Real 🔴

**O que é:** WebSocket público e gratuito da Binance + Bybit que transmite cada liquidação forçada em tempo real — sem API key, sem custo.

**Por que precisamos:** Liquidações em cascata são o principal driver de movimentos de preço bruscos. Saber quando estão acontecendo permite:
- Detectar cascade em andamento e entrar no bounce
- Acumular histórico de liquidações por nível de preço (heatmap próprio)
- Usar como sinal de saída antecipada (liquidações do lado da posição = risco)

**Endpoints gratuitos:**
```
# Binance — todas as moedas, sem autenticação
wss://fstream.binance.com/ws/!forceOrder@arr

# Bybit — por símbolo, atualização a 500ms
wss://stream.bybit.com/v5/public/linear
subscribe: {"op": "subscribe", "args": ["allLiquidation.BTCUSDT"]}
```

**Formato do evento Binance:**
```json
{
  "s": "BTCUSDT",     // símbolo
  "S": "SELL",        // SELL = long liquidado | BUY = short liquidado
  "q": "0.014",       // quantidade
  "p": "9910",        // preço
  "T": 1568014460893  // timestamp
}
```

**O que implementar:**
- Novo arquivo `backend/liquidation_ws.py` similar ao `binance_ws_market.py`
- Acumular liquidações em memória por símbolo nas últimas 4h (janela rolante)
- Persistir no banco a cada 15 min na tabela `liquidation_snapshots` (nova)
- Expor via endpoint `GET /api/market/liquidations/{symbol}`

**Schema da nova tabela:**
```sql
CREATE TABLE liquidation_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(30) NOT NULL,
    exchange    VARCHAR(20) NOT NULL DEFAULT 'binance',
    side        VARCHAR(5)  NOT NULL,  -- 'LONG' ou 'SHORT' (lado liquidado)
    price       NUMERIC(24,8) NOT NULL,
    qty         NUMERIC(24,8) NOT NULL,
    usd_value   NUMERIC(18,2),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_liq_symbol_time ON liquidation_snapshots(symbol, captured_at DESC);
```

**Esforço estimado:** 1–2 dias
**Dependências:** nenhuma (dados gratuitos)

---

### 1.2 — Acumulador de Open Interest (OI) por Símbolo 🔴

**O que é:** Polling periódico do endpoint REST da Binance para capturar evolução do OI.

**Por que precisamos:** OI crescente com preço sideways = posicionamento se acumulando → squeeze iminente. Já temos `funding_rate_snapshots`; OI é o dado que falta para a triple confluência.

**Endpoint gratuito:**
```
GET https://fapi.binance.com/futures/data/openInterestHist
    ?symbol=BTCUSDT&period=15m&limit=48
```

**O que implementar:**
- Adicionar coluna `open_interest` na tabela `funding_rate_snapshots` (migration)
- Ou criar tabela separada `oi_snapshots` com mesma estrutura de captura
- Coletar junto com o `symbol_syncer.py` a cada 15 min
- Calcular variação de OI nos últimos 3 ciclos (OI_delta) e expor no scoring

**OI Delta Signal:**
```python
oi_now   = snapshots[-1].open_interest
oi_3ago  = snapshots[-4].open_interest
oi_delta = (oi_now - oi_3ago) / oi_3ago  # variação % em 3 ciclos (45 min)

# Sinal: OI subindo com preço sideways e funding extremo = squeeze iminente
```

**Esforço estimado:** 0.5 dia
**Dependências:** nenhuma

---

### 1.3 — Heatmap de Liquidações Próprio (sem Coinglass) 🔵

**O que é:** Construir estimativa de zonas de liquidação a partir dos dados acumulados pelo item 1.1 + fórmula matemática.

**Fórmula de liquidação:**
```
# Posição LONG (margem isolada)
liq_price_long  = entry_price × (1 - 1/leverage + maintenance_margin_rate)

# Posição SHORT (margem isolada)
liq_price_short = entry_price × (1 + 1/leverage - maintenance_margin_rate)

# Maintenance Margin Rate Binance: ~0.4% para leverage ≤ 20x
```

**Método de construção do heatmap:**
1. Pegar histórico de preço (OHLCV) dos últimos 7 dias em candles de 1h
2. Para cada candle, assumir distribuição de leverage do mercado (30% em 10x, 25% em 20x, 20% em 50x, 25% em outros)
3. Calcular onde cada grupo seria liquidado a partir daquele preço
4. Agregar por nível de preço → clusters = zonas quentes

**Alternativa mais simples:** usar os dados do stream de liquidações (item 1.1) acumulados e plotar histograma por nível de preço → mesmo resultado, mais preciso pois usa dados reais.

**Esforço estimado:** 2–3 dias
**Dependências:** item 1.1 em operação por pelo menos 7 dias para ter histórico suficiente

---

### 1.4 — Integração Coinalyze API (fallback rico) 🔵

**O que é:** API REST gratuita (40 req/min com cadastro) com dados históricos de OI, liquidações, Long/Short Ratio e Predicted Funding Rate para Binance + Bybit.

**URL:** https://api.coinalyze.net/v1/doc/

**Endpoints úteis:**
```
GET /open-interest-history?symbols=BTCUSDT_PERP.A&interval=15min
GET /liquidation-history?symbols=BTCUSDT_PERP.A&interval=1hour
GET /long-short-ratio-history?symbols=BTCUSDT_PERP.A&interval=1hour
GET /predicted-funding-rate-history?symbols=BTCUSDT_PERP.A
```

**Uso sugerido:** backfill inicial do banco quando o stream próprio (1.1/1.2) ainda não tem histórico suficiente.

**Esforço estimado:** 0.5 dia
**Dependências:** cadastro gratuito para API key

---

## FRENTE 2 — Melhorias de Score com Dados Técnicos

> Melhorar a qualidade do sinal de entrada sem mudar a infraestrutura de execução.

### 2.1 — Predicted Funding Rate no Score 🟡

**O que é:** A Binance expõe a taxa de funding que vai ser paga **no próximo ciclo** (diferente da taxa histórica do último ciclo). Usar esse dado evita entrar em ativos onde a taxa já está caindo.

**Endpoint:**
```
GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT
→ campo: "lastFundingRate" (atual) + "nextFundingTime"
→ campo: o predicted está em "markPrice" e "indexPrice" (precisa calcular)

Ou via:
GET https://fapi.binance.com/fapi/v1/fundingRate
```

**Já temos o dado?** Sim — `binance_ws_market.py` já captura `fundingRate`. Verificar se é o predicted ou o histórico.

**Mudança no scoring:**
```python
# Antes: usa fundingRate (histórico do ciclo anterior)
funding_pct = abs(float(item.get("fundingRatePercent", 0)))

# Depois: preferir predictedFundingRatePercent se disponível
predicted = item.get("predictedFundingRatePercent")
funding_pct = abs(float(predicted if predicted is not None else item.get("fundingRatePercent", 0)))
```

**Impacto esperado:** evitar entradas onde a taxa histórica é alta mas o próximo pagamento será muito menor.

**Esforço estimado:** 2–4 horas
**Dependências:** verificar se o dado já é coletado no WS ou precisa de polling adicional

---

### 2.2 — RSI no Score de Funding Harvest 🟡

**O que é:** Adicionar RSI dos candles de 15 minutos como multiplicador de score. Entrada é melhor quando há confluência: funding extremo + RSI confirmando sobrecompra/sobrevenda.

**Lógica:**
```
Sinal SHORT com confluência:
  FR positivo alto (> 0.05%/ciclo) AND RSI 15min > 70
  → multiplicador +20% no score final

Sinal LONG com confluência (counter-trend):
  FR negativo (< -0.05%/ciclo) AND RSI 15min < 30
  → multiplicador +20% no score final

Divergência negativa (penalidade):
  FR positivo AND RSI < 50 (preço já caindo apesar de funding alto)
  → multiplicador -15% (provável que a reversão já começou)
```

**O que implementar:**
- Novo módulo `backend/indicators.py` com `calculate_rsi(candles, period=14)`
- Cache TTL de 60s por símbolo (candles mudam só a cada minuto)
- Integrar no `scoring.py` como multiplicador **após** calcular o score base
- Endpoint `GET /api/market/candles/{symbol}?interval=15m&limit=20` se necessário

**Fonte dos candles:** `GET https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=20`

**Esforço estimado:** 1 dia
**Dependências:** nenhuma

---

### 2.3 — OI Delta como Componente do Score 🟡

**O que é:** Adicionar variação de Open Interest como sinal de squeeze iminente. OI subindo + funding extremo + preço sideways = posicionamento se acumulando = squeeze iminente.

**Triple Confluência (o sinal mais robusto da literatura):**

| FR | OI Delta | Preço 4h | Interpretação | Ação |
|---|---|---|---|---|
| Alto positivo | +5% (subindo) | Sideways | Longs acumulando, squeeze SHORT iminente | Reforçar SHORT |
| Negativo | +5% (subindo) | Sideways | Shorts acumulando, squeeze LONG iminente | Reforçar LONG |
| Alto positivo | -5% (caindo) | Subindo | Distribuição — longs saindo no topo | SHORT forte |
| Qualquer | Queda brusca -10% | Caindo | Cascade de liquidações ativo | Aguardar estabilização |

**Integração no score:**
```python
# Componente OI (novo, 0 a +10 pontos bônus)
oi_delta = await _get_oi_delta(symbol, exchange, ciclos=3)

if oi_delta > 0.05 and funding_rate > 0:       # OI subindo + funding alto = squeeze SHORT
    oi_bonus = 10
elif oi_delta > 0.05 and funding_rate < 0:     # OI subindo + funding negativo = squeeze LONG
    oi_bonus = 10
elif oi_delta < -0.05:                          # OI caindo = posições fechando, sinal enfraquece
    oi_bonus = -5
else:
    oi_bonus = 0
```

**Esforço estimado:** 1 dia (depende do item 1.2)
**Dependências:** item 1.2 (coleta de OI)

---

### 2.4 — CVD (Cumulative Volume Delta) como Filtro de Entrada 🔵

**O que é:** CVD = soma acumulada de (volume compras mercado − volume vendas mercado). Mede pressão real de ordens. Divergência entre CVD e preço é um dos sinais mais poderosos de order flow.

**Lógica:**
```
Divergência Bearish (vender):
  Preço subindo + CVD caindo → distribuição real → reforça SHORT

Divergência Bullish (comprar):
  Preço caindo + CVD subindo → acumulação real → reforça LONG

Confluência com Funding:
  FR positivo alto + CVD divergindo negativamente = SHORT de alta confiança
```

**Como calcular:**
- Usar WebSocket de trades em tempo real: `wss://fstream.binance.com/ws/btcusdt@aggTrade`
- Para cada trade: se `m=false` (buyer is maker = sell market order) → subtrair; se `m=true` (buy market order) → somar
- Manter janela rolante de 30 minutos

**O que implementar:**
- Adicionar ao `binance_ws_market.py` acumulação de CVD por símbolo (apenas símbolos monitorados)
- Expor `cvd_30m` no dicionário de dados do símbolo
- Integrar como filtro de qualidade no `scoring.py`

**Esforço estimado:** 2 dias
**Dependências:** nenhuma além do WS já existente

---

## FRENTE 3 — Novas Estratégias de Operação

### 3.1 — Funding Flip Momentum 🟡

**O que é:** Quando o funding rate muda de sinal (negativo → positivo ou positivo → negativo), o mercado está mudando de regime. Entrar na direção da virada com trailing stop.

**Lógica de entrada:**
```
Virada LONG (negativo → positivo):
  - FR estava negativo por ≥ 2 ciclos consecutivos
  - FR atual > +0.005% (virou positivo)
  - OI crescendo (confirmação de participação)
  - Entrar LONG com leverage moderado (2–3x)
  - TP: quando FR supera +0.05% (mercado sobreaquecido) ou trailing 2%

Virada SHORT (positivo → negativo):
  - FR estava positivo por ≥ 2 ciclos consecutivos
  - FR atual < -0.005% (virou negativo)
  - Entrar SHORT
  - TP: quando FR cai abaixo de -0.05% ou trailing 2%
```

**Implementação:**
- Novo `operation_mode = "flip_momentum"` no `real_trader.py`
- Detector de virada em `scoring.py` ou novo `scoring_flip_momentum.py`
- Requer: histórico de 3+ snapshots de funding por símbolo (já temos em `funding_rate_snapshots`)
- Parâmetros configuráveis: `min_negative_cycles`, `min_positive_cycles`, `flip_threshold_pct`

**Risco:** sinais falsos frequentes quando funding oscila em torno de zero. Mitigar com filtro de OI crescente obrigatório.

**Esforço estimado:** 3–4 dias
**Dependências:** item 1.2 (OI) para filtro de confirmação

---

### 3.2 — Cascade Entry (Entrada Pós-Liquidação) 🟡

**O que é:** Detectar quando um cascade de liquidações está acontecendo em tempo real (via stream do item 1.1) e entrar na direção oposta após o pico de liquidações — capturando o bounce/mean reversion.

**Lógica:**
```
Trigger SHORT cascade (longs sendo liquidados):
  - Stream recebe ≥ X liquidações SELL (longs) em 60 segundos
  - USD liquidado no período > threshold (ex: $500k em 60s)
  - Preço caiu ≥ 2% nos últimos 5 minutos
  - Aguardar 30s de estabilização após último spike
  - Entrar LONG (bounce esperado após limpeza de alavancagem)
  - Stop apertado: -1% do preço de entrada
  - TP: +1.5% a +3% (recuperação típica de 60–80% do movimento)

Trigger LONG cascade (shorts sendo liquidados):
  - Liquidações BUY em cascata (shorts)
  - Entrar SHORT após estabilização
```

**Parâmetros configuráveis:**
- `cascade_usd_threshold`: valor mínimo de liquidações em USD no trigger (padrão: $200k)
- `cascade_window_seconds`: janela de detecção (padrão: 60s)
- `stabilization_seconds`: aguardar após pico (padrão: 30s)
- `stop_loss_pct`: stop apertado pós-cascade (padrão: 1%)

**Implementação:**
- Novo `operation_mode = "cascade_entry"`
- Módulo `backend/liquidation_detector.py` consumindo dados do item 1.1
- Lógica de trigger baseada em acumulação de USD liquidado por janela de tempo

**Esforço estimado:** 3–5 dias
**Dependências:** item 1.1 (stream de liquidações) — pré-requisito obrigatório

---

### 3.3 — Cross-Exchange Arbitrage (Binance × Bybit) 🔵

**O que é:** Quando o mesmo ativo tem funding rate muito diferente entre Binance e Bybit, abrir SHORT na exchange com funding maior (recebe mais) e LONG na outra (paga menos). Posição delta-neutra — lucro puro do diferencial de funding.

**Exemplo:**
```
POWERUSDT Binance: +0.08%/ciclo (recebe)
POWERUSDT Bybit:   +0.02%/ciclo (paga)
Diferencial:        0.06%/ciclo = +65.7% APY
Exposição direcional: ZERO (short Binance cancela long Bybit)
```

**Lógica de entrada:**
```python
spread = funding_binance - funding_bybit

if abs(spread) >= 0.03:  # diferencial mínimo de 0.03%/ciclo (~32% APY)
    if spread > 0:       # Binance mais cara
        open SHORT on Binance (recebe funding alto)
        open LONG  on Bybit   (paga funding baixo)
    else:                # Bybit mais cara
        open SHORT on Bybit
        open LONG  on Binance
```

**Lógica de saída:**
- Diferencial cai abaixo de 0.01%/ciclo (spread insuficiente)
- Funding inverte de direção em uma das pernas
- Saída simultânea nos dois lados

**Desempenho documentado:** 6–23% APY com Sharpe 3–6, risco direcional quase zero.

**Implementação:**
- Novo `operation_mode = "cross_exchange_arb"`
- Monitor de spread em `symbol_syncer.py` (já captura dados das duas exchanges)
- Abertura paralela coordenada: uma posição em cada exchange
- Monitoramento conjunto: ambas as pernas devem fechar juntas

**Riscos principais:**
- Abertura assíncrona: se uma perna falha, a outra fica exposta → precisa de rollback
- Spread pode fechar antes de executar as duas pernas
- Capital imobilizado nas duas exchanges simultaneamente

**Esforço estimado:** 1–2 semanas
**Dependências:** item 1.2 (OI para filtro), lógica de rollback, testes extensivos

---

### 3.4 — FR + RSI + Suporte/Resistência (Modo Técnico) 🔵

**O que é:** Modo de operação que combina funding extremo como filtro de direção com análise técnica (RSI + níveis de S/R) para timing de entrada mais preciso.

**Lógica:**
```
Setup SHORT de alta confiança:
  1. FR > +0.05%/ciclo por ≥ 2 ciclos (superlotado de longs)
  2. RSI 15min > 70 (sobrecomprado tecnicamente)
  3. Preço próximo (≤ 0.5%) de resistência histórica identificada
  4. CVD divergindo negativamente (confirmação order flow)
  → Entrada SHORT com alta confiança, stop acima da resistência

Setup LONG de alta confiança:
  1. FR < -0.05%/ciclo (superlotado de shorts)
  2. RSI 15min < 30 (sobrevendido tecnicamente)
  3. Preço próximo de suporte histórico
  4. CVD divergindo positivamente
  → Entrada LONG com stop abaixo do suporte
```

**Identificação automática de S/R:**
- Usar pivôs de candles diários/4h (máximas e mínimas dos últimos 20 candles)
- Volume Profile: preços de alto volume = suporte forte (calculável dos candles OHLCV)
- VWAP diário como referência dinâmica de valor justo

**Esforço estimado:** 2–3 semanas
**Dependências:** itens 2.2 (RSI), 2.4 (CVD), candles históricos em banco ou cache

---

## FRENTE 4 — Melhorias Pontuais no Sistema Atual

### 4.1 — Notificações Telegram 🟡

**Contexto:** já listado em `SUGESTOES.md`. Inclui aqui para priorização conjunta.

**O que notificar:**
- Posição aberta: símbolo, direção, score, funding, tamanho
- Posição fechada: PnL líquido, motivo de saída
- Erro crítico: margin insufficient, API error, bot parado inesperadamente
- Cascade detectado: símbolo, valor liquidado, direção do cascade
- Score forte sem bot ativo para capturar (oportunidade perdida)

**Esforço estimado:** 0.5–1 dia

---

### 4.2 — Auto-Compound do Lucro 🟡

**O que é:** Após cada ciclo de trades fechados com lucro, atualizar automaticamente o `capital` e `balance` do bot para reinvestir o lucro, aumentando o tamanho das posições.

**Lógica:**
```python
# Após fechar posição com lucro:
if total_pnl > 0:
    new_balance = current_balance + total_pnl
    await db.execute(
        "UPDATE real_config SET balance = $1 WHERE id = $2",
        new_balance, config_id
    )
    # position_value no próximo trade será automaticamente maior
```

**Esforço estimado:** 0.5 dia (já existe lógica de balance update)

---

### 4.3 — Heartbeat + Watchdog do Bot 🟡

**O que é:** Serviço que verifica periodicamente se os bots ativos ainda estão respondendo e alerta via Telegram se detectar travamento.

**Implementação:**
- Cada bot atualiza campo `last_heartbeat` a cada 60s no `real_config`
- Worker separado verifica bots com `last_heartbeat > 5 min` e envia alerta
- Reinicia automaticamente bots travados (opcional, com flag de segurança)

**Esforço estimado:** 1 dia

---

## Roadmap Sugerido

```
SEMANA 1 (Infraestrutura + Melhorias Rápidas)
├── [0.5d] 1.2 — Coleta de OI no symbol_syncer
├── [1.0d] 1.1 — Stream de liquidações Binance/Bybit
├── [0.5d] 2.1 — Predicted funding rate no scoring
├── [0.5d] 4.1 — Notificações Telegram
└── [0.5d] 4.2 — Auto-compound do lucro

SEMANA 2 (Score Avançado)
├── [1.0d] 2.2 — RSI 15min no scoring
├── [1.0d] 2.3 — OI Delta como componente do score
├── [2.0d] 2.4 — CVD acumulação no WS
└── [0.5d] Testes e validação contra histórico

SEMANA 3 (Novas Estratégias)
├── [4.0d] 3.1 — Flip Momentum (nova operation_mode)
└── [1.0d] Backtesting da estratégia com dados históricos

SEMANA 4 (Cascade + Técnico)
├── [5.0d] 3.2 — Cascade Entry (depende de 1.1 com histórico)
└── Avaliação de resultados das semanas anteriores

SEMANA 5+ (Projetos Maiores)
├── 3.3 — Cross-Exchange Arbitrage (1–2 semanas)
├── 3.4 — Modo Técnico completo (2–3 semanas)
└── 1.3 — Heatmap próprio de liquidações
```

---

## Tabela Consolidada

| ID | Estratégia / Melhoria | Frente | Esforço | Impacto | Prioridade | Depende de |
|---|---|---|---|---|---|---|
| 1.1 | Stream de liquidações (WS) | Infra | 1–2d | Alto | 🔴 P0 | — |
| 1.2 | Coleta de OI no syncer | Infra | 0.5d | Alto | 🔴 P0 | — |
| 2.1 | Predicted funding rate | Score | 2–4h | Médio | 🟡 P1 | — |
| 2.2 | RSI 15min no score | Score | 1d | Alto | 🟡 P1 | — |
| 4.1 | Notificações Telegram | Sistema | 0.5d | Alto | 🟡 P1 | — |
| 4.2 | Auto-compound | Sistema | 0.5d | Médio | 🟡 P1 | — |
| 4.3 | Heartbeat watchdog | Sistema | 1d | Alto | 🟡 P1 | 4.1 |
| 2.3 | OI Delta no score | Score | 1d | Alto | 🟡 P1 | 1.2 |
| 3.1 | Flip Momentum mode | Estratégia | 3–4d | Médio | 🟡 P1 | 1.2 |
| 2.4 | CVD Divergence | Score | 2d | Alto | 🔵 P2 | — |
| 3.2 | Cascade Entry mode | Estratégia | 3–5d | Alto | 🔵 P2 | 1.1 |
| 1.4 | Coinalyze API (backfill) | Infra | 0.5d | Médio | 🔵 P2 | — |
| 1.3 | Heatmap liquidações próprio | Infra | 2–3d | Alto | 🔵 P2 | 1.1 (7d dados) |
| 3.3 | Cross-Exchange Arb | Estratégia | 1–2 sem | Muito alto | 🔵 P2 | 1.2 |
| 3.4 | FR + RSI + S/R (modo técnico) | Estratégia | 2–3 sem | Alto | ⚪ P3 | 2.2, 2.4 |

---

## Já Implementado (hoje, 2026-02-28)

| Item | Descrição |
|---|---|
| ✅ Score weights ajustados | APY↑32, Consistency↓13, Momentum↓8, Int↓5, Vol 22 |
| ✅ Thresholds Coleta de Taxa | Forte 65, Moderado 52, Fraco 38 |
| ✅ Filtro taxa máxima (1%/ciclo) | Veto em `scoring.py` + campo no UI |
| ✅ Race condition maker → market | `asyncio.sleep(1)` após cancel_order |
| ✅ Balance paralelo corrigido | Usa `available_balance` via in-memory session |
| ✅ Bug abertura paralela (margin) | Desconta margem das posições abertas antes de calcular |

---

*Documento gerado automaticamente. Atualizar à medida que itens forem implementados.*
