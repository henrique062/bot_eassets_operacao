# Auditoria Quantitativa (Funding Ratio + Counter-Trade) **com Validação de Stops**

Você é um **auditor quantitativo + auditor de execução (trade ops)** do meu sistema **Crypto Funding Rates (Vorxia)**. Sua resposta deve ser **100% baseada em dados**, com tabelas-resumo e conclusões certeiras.

**Ambiente / regras:**

* Exchange: Binance e/ou Bybit (se aplicável)
* Horário de referência: **GMT-3**
* Período de análise: **HOJE e ONTEM** (defina explicitamente o intervalo por timestamp em GMT-3)
* Fonte de dados: **Banco de dados do sistema** (operações, parâmetros, snapshots do sinal/score no momento da entrada) **+ tabela `server_logs`** (logs de decisão/execução disparados pelo sistema, transições maker→taker, arm/disparo de stops, erros e latência).

---

## 0) Contexto do Motor Vorxia

Temos **2 modos**:

### Modo A — Funding Ratio (Direcional / “Pegar a Taxa”)

**Vetos (risco inaceitável):**

* Volatilidade extrema: rejeita variação de preço de ±35% (24h)
* Baixa liquidez: rejeita volume 24h abaixo do mínimo (2M a 5M)

**Pontuação (0–100), pilares:**

* APY líquido (até 40)
* Liquidez (até 20)
* Consistência histórica (até 15)
* Intervalo menor (até 10)

### Modo B — Counter-Trade (Contra-tendência / reversão)

**Vetos:**

* Funding irrelevante: vetado se funding < 0,01%
* Falta de liquidez: vetado se volume < 2M

**Score (0–100), pilares:**

* Extremidade da taxa (até 40)
* Persistência insustentável (até 30) (até 5 dias / 20 ciclos)
* Liquidez absorvida (até 20)
* Bônus de volatilidade (até 10)

**Confiança:**

* FORTE (>= 75)
* MODERADO (50–74)
* FRACO/EVITAR (< 50)

---

## 1) Configuração Operacional (use os parâmetros do banco)

Além do modo, a estratégia possui estes parâmetros que podem mudar por execução:

**Seleção de moedas**

* Critério de seleção: `Score` OU `Funding Rate`
* Direção: `Long`, `Short` ou `Long + Short`
* Quantidade de moedas: `N`
* Pontuação mínima: `score_min`

**Execução / microestrutura**

* Capital total (USDT): `capital_total`
* Capital por símbolo: `capital_por_simbolo`
* Alavancagem: `leverage`
* Fee preferencial: `Maker` OU `Taker`
* Timeout maker (s): `timeout_maker` (espera pela ordem maker antes de usar taker)
* Delay pós-virada (s): `delay_pos_virada` (tempo após o funding/virada antes de executar/validar)

**Stops e gestão (extraia exatamente do setup do bot):**

* Stop loss por preço (%): `sl_preco_pct`
* Stop loss em USD: `sl_usd`
* Take profit alvo (%): `tp_alvo_pct`
* Trailing stop (% do preço): `trailing_pct`
* **Ativar trailing após** (% do preço): `trailing_ativa_apos_pct`
* **Break-even em lucro** (% do preço): `breakeven_pct`
* TP parcial em lucro (%): `tp_parcial_ativa_pct`
* Tamanho do TP parcial (% posição): `tp_parcial_tamanho_pct`
* **Lucro mínimo para fechar** (%): `lucro_min_fechar_pct`

---

## 2) Extração Obrigatória de Dados (Hoje + Ontem)

> **Obrigatório:** usar também `server_logs` para reconstruir a linha do tempo (decisão → envio de ordem → fill → arm de stop → disparo → fechamento), e para validar regras como delay pós-virada, timeout maker, break-even e trailing.
> **Puxe TODAS as operações reais** executadas no período e traga uma tabela por trade com:

* timestamp entrada / saída (GMT-3)
* modo (`Funding Ratio` ou `Counter-Trade`)
* exchange, símbolo
* direção (long/short)
* critério de seleção usado (Score ou Funding)
* score total e *componentes* (Extremidade/Persistência/Liquidez/Volatilidade **ou** APY/Liquidez/Consistência/Intervalo)
* funding no momento da entrada, e próximo funding (timestamp)
* preço entrada/saída
* tipo de execução (maker/taker) + fee real pago
* stop/saída acionada (TP, SL preço, SL USD, trailing, breakeven, lucro mínimo, timeout, manual, etc.)
* PNL bruto, PNL líquido (após fees e funding), PNL% sobre margem e sobre capital
* MFE (maior lucro flutuante) e MAE (maior perda flutuante) durante a operação

Se algum campo não existir em tabela, use **`server_logs`** (e logs do bot/snapshots) para completar. Se necessário, reconstrua via séries de preço do período. Se necessário, reconstrua via séries de preço do período.

---

## 3) Métricas Consolidadas (nível estratégia)

Calcule, por modo **e também no agregado**:

* Win rate
* Profit Factor
* Expectância (média de PNL por trade)
* Máximo drawdown (sequência e valor)
* ROI sobre banca de **$50** (e também sobre o capital total configurado)
* Distribuição de PNL (média, mediana, desvio, outliers)

Quebre também por:

* faixa de Score: 50–74 / 75–84 / 85–94 / 95–100
* direção (long vs short)
* critério de seleção (Score vs Funding)
* maker vs taker
* motivo de saída (TP/SL/trailing/breakeven/etc.)

---

## 4) Diagnóstico de Saturação do Score

Eu vejo muitas moedas batendo **Score 100**.

Faça:

1. Histograma/contagem de Score total por modo
2. Distribuição dos **componentes** do Score
3. Detecte saturação:

* quantos trades/seleções têm Score >= 95 e Score = 100
* quais pilares estão “colando no teto” (ex.: Extremidade=40, Persistência=30, etc.)

4. Verifique se Score alto **realmente prevê lucro**:

* compare PNL médio e win rate por faixa de Score
* correlação (Spearman e Pearson) entre pilares e PNL líquido

---

## 5) Auditoria dos Prejuízos (com simulação de ajustes)

Para cada trade com prejuízo:

* houve lucro flutuante? (MFE > 0)
* em quanto tempo ocorreu o MFE (seg/min após entrada)
* qual foi o “motivo real” de perder: continuação da tendência, atraso de entrada, spread/fee, stop curto, volatilidade, falha maker->taker, etc.

### 5.1 Simulações (replay) — sem mudar o sinal

Recalcule o resultado aplicando variações **apenas** nos parâmetros de execução/stops:

* delay pós-virada: 0s / 15s / 30s / 60s
* take profit alvo: 0,3% / 0,5% / 1%
* trailing: 0,3% / 0,5% / 0,8%
* trailing_ativa_apos: 1,0% / 1,5% / 2,0%
* breakeven: 0,2% / 0,3% / 0,5%
* lucro mínimo para fechar: 0,05% / 0,10% / 0,15%
* trocar maker->taker mais cedo (timeout maker 10s/20s/30s)

**Saída esperada:** uma tabela “antes vs depois” mostrando quanto o PNL líquido mudaria por variação e quais mudanças reduzem perdas sem destruir ganhos.

---

## 6) **Validação de Funcionamento dos Stops (correção + aderência ao esperado)**

Eu preciso validar se o **motor de stops** está funcionando corretamente (não só se foi lucrativo).

### 6.1 Checklist por trade (auditoria de lógica)

> Use `server_logs` como fonte principal para verificar **sequência de eventos**, **timestamps**, **parâmetros efetivos** aplicados em runtime e **motivo real** (ex.: `BE_ARM`, `BE_MOVE_SL`, `TRAIL_ARM`, `TRAIL_UPDATE`, `TRAIL_HIT`, `TP_PARTIAL`, `MAKER_TIMEOUT`, `SWITCH_TO_TAKER`, `ORDER_FILLED`, `CLOSE_REASON`, `ERROR`). Se os nomes exatos dos eventos forem diferentes, mapeie-os e documente o mapeamento.
> Para cada operação, valide com base em logs + preços:

* **Break-even**:

  * confirmou se a posição atingiu `breakeven_pct` de lucro (em preço) antes de mover o SL para entrada?
  * o SL foi movido para o preço correto (entry +/- fees se aplicável)?
  * após o BE ativar, houve execução do SL em BE quando o preço voltou?

* **Ativar trailing após**:

  * confirmou se o trailing **só** foi armado depois de atingir `trailing_ativa_apos_pct`?
  * o trailing passou a seguir o pico corretamente (pico para long / vale para short)?
  * o gatilho de saída do trailing respeitou `trailing_pct`?

* **TP parcial**:

  * ativou exatamente em `tp_parcial_ativa_pct`?
  * fechou exatamente `tp_parcial_tamanho_pct` da posição?
  * o restante da posição continuou com regras corretas (TP final, trailing, BE, lucro mínimo)?

* **Lucro mínimo para fechar**:

  * a lógica bloqueou fechamento antecipado até `lucro_min_fechar_pct`?
  * houve fechamento abaixo do mínimo (bug) em algum caso?

* **Stop loss por preço (% ) vs SL em USD**:

  * em trades que bateram stop, qual stop disparou primeiro e por quê?
  * houve conflito de regras (ex.: SL USD fechando antes do SL % de preço de forma inesperada)?

* **Maker/Taker + timeout**:

  * ordens maker expiraram após `timeout_maker` e migraram para taker corretamente?
  * ocorreu piora material de preço (slippage) por migração maker->taker?

### 6.2 Detecção de falhas (automática)

Marque como **falha** e explique quando:

* o preço atravessou o nível de stop/trigger e **não** executou (gap / latência / erro de API)
* o trigger ocorreu, mas a saída veio muito distante (slippage anormal)
* trailing/BE/TP parcial ativou fora do threshold
* logs mostram “executado”, mas PNL/ordens não batem (inconsistência)

### 6.3 Relatório de conformidade

Entregue um relatório com:

* % de trades com stops funcionando corretamente (por tipo de stop)
* top 5 padrões de falha (ex.: BE não moveu, trailing armou cedo, TP parcial não executou)
* impacto financeiro das falhas (PNL que seria evitado/ganho se stop tivesse funcionado)

---

## 7) Validação de Hipóteses do Counter-Trade

Teste estas hipóteses (com dados):

* Persistência máxima (20/20 ciclos) sinaliza reversão ou sinaliza **regime forte de continuação**?
* Funding extremo (ex.: > 0,15% e principalmente > 1%) reverte mais rápido ou tende a continuar com alta volatilidade?
* Volatilidade alta (bônus) melhora o edge ou aumenta ruído e stop-outs?

Entregue:

* tabelas comparando performance por quantis de persistência, extremidade e volatilidade
* conclusão objetiva (com números)

---

## 8) Recomendação Final (somente baseada em dados)

Responda no formato:

1. **O modo Funding Ratio está lucrativo?** (sim/não + métricas)
2. **O modo Counter-Trade está lucrativo?** (sim/não + métricas)
3. **Score está saturado?** (sim/não + evidência)
4. **Stops estão funcionando corretamente?** (taxa de conformidade + principais falhas)
5. **Quais 3 ajustes trazem maior ganho líquido esperado?**

   * ajuste #1 (parâmetro -> novo valor)
   * ajuste #2
   * ajuste #3
6. **Quais filtros adicionais você recomenda testar** (sem inventar dados):

   * ex.: score_min maior, funding_min maior, limite de persistência, condição de volatilidade, etc.

**Proibido:** opinião vaga, frases genéricas, “pode ser”.
**Obrigatório:** números, tabelas e justificativa estatística curta.
