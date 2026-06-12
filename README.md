# PHOENIX MEMBROS — Painel Encryptos

Painel web local (Flask + SQLite) que transforma snapshots brutos do
`eassets-panel-*.json` em um dashboard de análise de cripto seguindo a
**metodologia Encryptos**: score estrutural, Setup de Ouro, radar de acumulação
e histórico de cada moeda ao longo do tempo.

Tudo roda **localmente**, sem chamar API externa. Você cola/importa o JSON, o
sistema calcula as métricas derivadas, salva o snapshot completo no banco e
abre o painel daquele dia.

---

## Para que serve

- **Importar** um snapshot (JSON) e ver o painel completo (top 10, cards, BTC).
- **Guardar histórico** de todos os snapshots no SQLite (nada do JSON é descartado).
- **Comparar dias**: clicar numa moeda mostra a série temporal dela em todos os scans.
- **Estudar padrões** que antecedem boas operações (recorrência no topo, acumulação).
- **Registrar análises** da metodologia feitas no chat (skill `analise-encryptos`).

> Painel **educativo** — não constitui recomendação de investimento.

---

## Como rodar

Requisito: Python 3 com Flask instalado.

```powershell
pip install flask
python app.py
```

Abre em **http://127.0.0.1:5000**. O banco (`phoenix.db`) é criado/migrado
automaticamente no primeiro start.

Fluxo de uso:

1. Clique em **＋ IMPORTAR JSON**, cole o conteúdo de um `eassets-panel-*.json`
   (ou envie o arquivo) e clique em **PROCESSAR**.
2. O snapshot é salvo e o painel daquele dia abre.
3. Use o seletor de snapshots para revisitar dias anteriores e os menus do topo
   para as visões especializadas.

---

## Estrutura do projeto

| Arquivo | Papel |
|---|---|
| `app.py` | App Flask: rotas, templates das páginas, modal de import, navegação. |
| `gerar_painel.py` | **Core** da metodologia: cálculo de score, classificação de setup, checklist do Setup de Ouro, gate macro do BTC, formatação e render do painel HTML. Também roda standalone via CLI. |
| `db.py` | Camada SQLite: schema, migrations, ingestão, consultas (histórico, radar, topo recorrente, análises). |
| `analise_dados.py` | Prepara os dados do último snapshot para análise **no chat** (sem API). Seleciona candidatos e imprime relatório compacto. |
| `salvar_analise.py` | Grava no banco uma análise da metodologia feita no chat. |
| `phoenix.db` | Banco SQLite com todos os snapshots, métricas e análises. |
| `Json extraidos encryptos/` | Snapshots `eassets-panel-*.json` de origem. |
| `Manuais/` | Documentação da metodologia Encryptos (briefing, manual operacional, master guide). |
| `.claude/skills/analise-encryptos/` | Skill que roda a análise Encryptos no chat. |

---

## Rotas do painel

| Rota | O que mostra |
|---|---|
| `/` | Último snapshot importado. |
| `/snapshot/<id>` | Um snapshot específico. |
| `/historico/<symbol>` | Série temporal de uma moeda (score, rank, EXP, OI… ao longo do tempo) + sparkline. |
| `/setup` | **Setup de Ouro**: checklist de entrada (7 critérios) com gate do BTC. |
| `/radar` | **Radar de Acumulação**: T/OI e persistência (dias no topo de intensidade). |
| `/topo` | **Topo Recorrente**: moedas que mais apareceram no TOP 10. |
| `/analises` | Análises IA salvas (metodologia feita no chat). |
| `/snapshots` | Lista de todos os snapshots no banco. |
| `/ingest` | (POST) recebe o JSON e salva o snapshot. |

---

## A metodologia (resumo técnico)

### SCORE (0–100) — força estrutural
Não vem do JSON; é derivado em `gerar_painel.py`. Soma ponderada de:

- **EXP (45)** — alinhamento de `exp_btc` (força vs BTC) em 1D/4h/1h.
- **ROBÔS (20)** — atividade de `trades_minute:5m` (escala log).
- **LSR (15)** — `lsr_trend` negativo = shorts capitulando = combustível de alta.
- **OI (12)** — `oi_trend` positivo = dinheiro novo entrando.
- **RSI (8)** — bônus de momentum (RSI 4h alto em tendência).

Os pesos e escalas ficam no topo de `gerar_painel.py` e são ajustáveis.

### Gate macro do BTC
Só faz sentido caçar entrada quando o BTC está em **reset/neutralidade**
(RSI 30m/1h ≤ 50). RSI ≥ 68 = pump → evitar. Define se a "janela" está aberta.

### Setup de Ouro — 7 critérios
`exp_pos` (força vs BTC em 5m/15m/1h) · `tpm_hot` (trades acelerando) ·
`lsr_fuel` (LSR<1 ou caindo) · `oi_in` (OI subindo) · `rsi_runway`
(RSI quente sem exaustão) · `accumulation` (range comprimido) ·
`funding_neg` (funding negativo).

**Setup de Ouro** = BTC em janela + `exp_pos` + `tpm_hot` + ≥5/7 critérios.
Abaixo disso, ≥4/7 com janela = **PARCIAL**.

### T/OI — radar de acumulação
`trades:1D ÷ ($1M de OI)` = intensidade de robôs/SM relativa ao capital. OI baixo
recebendo muitos trades = interesse desproporcional, SM trabalhando o ativo.

### Armadilha
Preço caindo + LSR subindo + OI caindo = armadilha de varejo (marcada no painel).

---

## Banco de dados (SQLite)

- **`snapshots`** — um registro por scan importado (timestamp, exchange, setup,
  nº de ativos, gate do BTC).
- **`metrics`** — uma linha por moeda por snapshot. Colunas indexadas para
  consulta rápida **+ `raw_json`** com o dict bruto completo (nada é perdido).
- **`analises`** — análises da metodologia feitas no chat, ligadas a um snapshot.

Migrations automáticas (`_migrate` em `db.py`) adicionam colunas novas em bancos
antigos e fazem backfill a partir do `raw_json`.

---

## Uso via linha de comando (sem o app)

```powershell
# Gera um painel HTML estático a partir de um JSON
python gerar_painel.py "Json extraidos encryptos/eassets-panel-20260609-125841.json" painel.html

# Prepara o relatório de candidatos do último snapshot para análise no chat
python analise_dados.py 30

# Salva no banco uma análise (JSON) feita no chat
python salvar_analise.py analise.json
```

---

## Notas

- Fuso: tudo é guardado em **UTC** e exibido em **GMT-3 (BRT)**.
- O painel é renderizado server-side com templates embutidos nos arquivos Python
  (sem build de frontend).
