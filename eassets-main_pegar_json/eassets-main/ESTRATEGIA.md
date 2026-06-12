# BANCADA PHOENIX — Estratégia

## Visão Geral

Sistema de scanning de altcoins no mercado de futuros Binance (USDM).
Objetivo: identificar setups de entrada com alta probabilidade antes de movimentos de alta.

Dados de entrada: exportação do painel pago **Phoenix 2** (`dadosmoedas.txt`) + dados ao vivo da Binance REST API.

---

## 1. Filtro Macro (pré-requisito)

Antes de qualquer análise, o sistema verifica a saúde do mercado pelo **RSI diário do BTC**:

| RSI BTC 1D | Status | Ação |
|---|---|---|
| < 45 | 🔴 AMBIENTE HOSTIL | Não operar Modo Fênix |
| 45–55 | 🟡 NEUTRO | Operar com cautela |
| > 55 | 🟢 FAVORÁVEL | Janela de entrada |

---

## 2. Sistema de Score (0–40 pontos)

Cada altcoin recebe uma nota composta por 10 critérios:

| Critério | Pts | O que avalia |
|---|---|---|
| Tendência | 0–10 | EXP diário, OI trend, volume, LSR+OI, EXP 4H |
| RSI | 0–3 | Zona ideal: RSI entre 50–70 |
| EXP 15m | 0–3 | Ângulo exponencial vs BTC no curto prazo |
| Acumulação | 0–6 | `range_level` em timeframes diário + intra-day |
| Timing | 0–2 | Trades/min acelerando vs média de 5min |
| Score 1H | 0–2 | EXP 1H + RSI 1H alinhados |
| Score 4H | 0–2 | EXP 4H + RSI 4H alinhados |
| Funding Rate | -1/0 | Penaliza FR extremo (> 0.05% ou < -0.05%) |
| Força vs BTC | 0–2 | Alta própria acima do movimento do BTC |
| Jacaré | 0–2 | OI subindo + LSR caindo simultaneamente |
| Alinhamento | 0–2 | 3 timeframes (1m, 1H, 4H) confirmando |

**Veredito final:**
- ≥ 32 → ✅ ENTRAR AGORA
- 24–31 → ⏳ AGUARDAR CONFIRMAÇÃO
- 18–23 → 👁️ OBSERVAR
- < 18 → ❌ NÃO ENTRAR

---

## 3. Modo Fênix (critérios do método)

Detector de entrada imediata. Usa 4 critérios binários baseados no método do professor:

```
C1: EXP BTC 1m > 3          → combustível de curto prazo
C2: Trades 1m ≥ 80% do 5m   → volume entrando agora
C3: RSI 1m entre 50–70      → força sem sobrecompra
C4: Range Level 15m ≥ 3     → acumulação confirmada no curto
```

- Filtro mínimo: > 30.000 trades no dia (liquidez mínima)
- Score 4/4 → ENTRAR AGORA · 3/4 → ENTRAR · 2/4 → AGUARDAR
- **Bloqueado se macro HOSTIL**

---

## 4. Radar Fase 1 (pré-explosão)

Detecta moedas em fase de acumulação antes do movimento começar.

```
Score = range_level_1D × 20
      + range_level_4H × 10
      + range_level_1H ×  5
      + range_level_30m × 3
      + range_level_15m × 2
```

- ≥ 110 → 🟢 ALTA PROBABILIDADE
- ≥ 80  → 🟡 MÉDIA
- ≥ 30  → ⚪ MONITORAR

**Pre-Setup:** acumulação só nos timeframes menores (1D ainda zerado) → sinal antecipado.

---

## 5. Três Agentes de Análise

Cada veredito de entrada passa por 3 perspectivas independentes:

| Agente | Foco | Sinal verde |
|---|---|---|
| 🐊 **CZ** | OI + LSR (baleias) | OI subindo + LSR caindo = squeeze |
| ⚡ **Fênix** | Momentum (EXP + RSI + trades) | EXP 1m > 5 + RSI zona 50–70 |
| 🛡️ **Safe** | Força própria vs BTC | Alta do dia > BTC |

Consenso: 2/3 verdes sem veto → entrar. 2/3 vermelhos → não entrar.

---

## 6. Gestão da Operação

Sugestão padrão calculada sobre o preço de entrada:

```
Stop Loss : entrada × 0.97  (-3%)
Take Profit 1 : entrada × 1.05  (+5%)   → realizar 50%
Take Profit 2 : entrada × 1.10  (+10%)  → realizar tudo
Saída extra: RSI > 80 (sobrecomprado)
```

---

## 7. Métricas Chave

| Métrica | Fonte | Atualização |
|---|---|---|
| `exp_btc` | Phoenix 2 (painel pago) | Na importação |
| `range_level` | Phoenix 2 (painel pago) | Na importação |
| `trades_minute` | Phoenix 2 (painel pago) | Na importação |
| RSI (todos TFs) | Phoenix 2 (painel pago) | Na importação |
| Preço + var. 24h | Binance REST | A cada 3s |
| Funding Rate | Binance REST | A cada 5s |
| Open Interest | Binance REST | A cada 30s |
| Long/Short Ratio | Binance REST | A cada 60s |

---

## 8. Agente IA Encryptos/Phoenix

O prompt operacional completo para agentes de IA fica em
`PROMPT_SISTEMA_ENCRYPTOS_PHOENIX.md`.

A implementação atual do dashboard inclui uma aba **IA Encryptos** com:

- bloqueio macro por BTC RSI 15m/1h e BTCD quando disponível;
- filtros mínimos de `oi >= $10M` e `trades:1D >= 150k`;
- blacklist de ADA, XRP, DOGE, XLM, LUNC e símbolos `1000*`, salvo injeção astronômica;
- classificação nos Setups A-D: Reset, Pré-Ignição, Caça à Liquidez e Pullback/Continuidade;
- bloco fixo de gestão: alavancagem 3x-5x, RP parcial, stop no 0x0 e proibição de adicionar margem em posição perdedora.

---

## 9. Captura Automática eAssets

O fluxo de snapshot automático do painel eAssets está documentado em
`EASSETS_AUTOMACAO.md`.

Resumo:

- login via Playwright em `https://eassets.ai/panel`;
- clique no botão **Export for AI**;
- download pelo botão **Download JSON File**;
- validação do JSON e inserção em `snapshots`;
- agendamento padrão a cada 30 minutos;
- botão manual **Capturar IA** no dashboard.
