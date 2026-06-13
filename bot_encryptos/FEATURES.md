# Phoenix Bot — Funcionalidades

Documentação das funcionalidades além do core de trading. Stack: Rust (motor),
Python/FastAPI (API + scraper), Next.js (frontend), PostgreSQL externo.

---

## Paper Trading (modo de teste)

Permite ligar o bot e validar a qualidade das entradas **com preços reais**, sem
arriscar dinheiro. Padrão **seguro = paper** (só opera de verdade quando desligado
explicitamente).

**Como usar:** aba **Config → Controle do Bot** → deixe "Modo de teste (Paper
Trading)" ligado → "Iniciar Bot". O status mostra `Rodando (paper)`.

**Como funciona:**
- Config `paper_trading` (DB `eassets_bot_config.paper_trading`, default `TRUE`).
- Ao iniciar (`POST /api/eassets/bot/start`), a config é aplicada ao motor Rust
  via `/internal/start` (que agora lê o corpo e atualiza a config de runtime).
- No motor (`rust_core/engine/decision.rs`):
  - **paper:** simula o fill (sem chamar a Bybit), `order_id = PAPER-<uuid>`,
    `mode = "paper"`. Não envia TP/SL para a exchange.
  - **real:** envia ordem de mercado + TP/SL para a Bybit.
- `risk_manager` fecha posições paper apenas no banco (não toca na exchange);
  SL/TP/trailing são avaliados com **preço real** da Bybit.
- Posições e trades recebem coluna `mode` (`paper`|`live`) para separar as
  estatísticas (migration `003`).

**Sizing:** `capital_per_trade = capital_total / max_positions` (distribui a margem
da conta entre as posições, na alavancagem definida).

---

## Monitoração de Moedas

Marque qualquer moeda para acompanhar e ver **quanto subiu/caiu (valor e %) desde
que marcou**, com horário da marcação, métricas atuais e a virada do funding.

**Como usar:**
- No **Painel de Moedas**, clique no alvo (🎯) ao lado do ativo; ou
- Na aba **Monitoração**, digite o símbolo e clique "Monitorar".

**Como funciona:**
- Tabela `eassets_monitored` (migration `003`): guarda `mark_price`, `mark_score`,
  `mark_setup`, `marked_at`, snapshot de origem. Uma marcação ativa por símbolo.
- Endpoints (`/api/eassets/panel`):
  - `POST /monitor` `{symbol, note?}` — marca (captura preço/score atuais).
  - `DELETE /monitor/{symbol}` — desmarca (arquiva, não apaga).
  - `GET /monitored` — lista ativa com `delta_abs`, `delta_pct` (atual vs marcado),
    métricas do último snapshot e o bloco `funding`.

---

## Virada de Funding (Funding Turn)

O **funding rate** vira de sinal periodicamente; cada moeda tem seu intervalo.
Funding **negativo** = shorts pagando longs = munição para short squeeze (alta).
A "virada" para negativo é um sinal de interesse.

**Onde ver:** coluna **Funding (virada)** na aba Monitoração — mostra o funding
atual (verde se negativo) e um selo "virou há N snaps" quando detecta troca de sinal.

**Como funciona:**
- Sem tabela nova: o funding (`fr`) é lido do `raw_json` que já é salvo por moeda
  em `eassets_metrics` a cada snapshot.
- `GET /api/eassets/panel/funding/{symbol}` — série temporal + detecção da última
  virada de sinal (`direction`: `to_negative` bullish / `to_positive` bearish;
  `snapshots_since_flip`).
- Como cada moeda tem seu ciclo de funding e há volatilidade na virada, medimos em
  **nº de snapshots** desde a troca (não em tempo fixo), o que normaliza a cadência.

---

## Scraper com Sessão Persistente

Antes o scraper fazia **login a cada captura** (browser/contexto novos) — risco de
bloqueio por logins repetidos. Agora usa **contexto persistente** do Playwright.

**Como funciona:**
- `launch_persistent_context(EASSETS_USER_DATA_DIR)` — cookies/sessão salvos em
  disco (volume Docker `eassets_profile` em `/data/eassets_profile`).
- Loga só na 1ª vez (ou quando a sessão expira); `_login_if_needed` verifica se já
  está logado antes de enviar credenciais.

---

## Sincronização Painel ↔ Bot (contexto)

O motor **não tem score próprio**: consome o ranking do Painel
(`GET /api/eassets/panel/entry-candidates`) — moedas Setup de Ouro com o gate macro
do BTC aberto. Fonte única = o que aparece no Painel de Moedas.
