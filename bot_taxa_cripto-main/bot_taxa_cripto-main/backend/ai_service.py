"""
Serviço de análise com IA (Google Gemini).
Analisa funding rates, LSR e dados de mercado para recomendar operações.
Retorna análise formatada + lista estruturada de moedas recomendadas.
"""

import os
import json
import re
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


async def analyze_funding_opportunities(
    top_positive: list[dict],
    top_negative: list[dict],
    lsr_data: dict,
    stats: dict,
    exchange: str,
) -> dict:
    """
    Envia os dados de mercado para o Gemini analisar e retorna recomendações.
    Retorna dict com 'analysis' (markdown) e 'recommended_coins' (lista estruturada).
    """
    if not GEMINI_API_KEY:
        return {
            "analysis": "❌ Chave da API Gemini não configurada. Adicione GEMINI_API_KEY no arquivo .env",
            "recommended_coins": [],
        }

    intervals_json = json.dumps(stats.get('intervals', {}), ensure_ascii=False)

    prompt = f"""Você é um analista quantitativo sênior de criptomoedas, especializado em estratégias direcionais com base no Funding Rate de futuros perpétuos.

Analise os dados da exchange **{exchange.upper()}** e forneça recomendações práticas de operação direcional. As operações NÃO são de arbitragem neutra. O objetivo é receber a taxa de funding e assumir o risco direcional ou buscar reversão de preço.

## Dados do Mercado

### Estatísticas Gerais
- Total de pares: {stats.get('totalPairs', 0)}
- Positivos: {stats.get('positiveCount', 0)} | Negativos: {stats.get('negativeCount', 0)} | Neutros: {stats.get('neutralCount', 0)}
- Taxa média: {stats.get('avgRatePercent', 0):.4f}%
- Distribuição de intervalos de funding: {intervals_json}

### Top 10 Maiores Funding Rates (positivos) — Oportunidades de SHORT
(Shorts recebem dos Longs quando o funding é positivo)
Cada item inclui: score (0-100), confidence (FORTE/MODERADO/FRACO/EVITAR), signal, shouldOpen (true/false) e motivos.
```json
{json.dumps(top_positive, ensure_ascii=False, indent=2)}
```

### Top 10 Menores Funding Rates (negativos) — Oportunidades de LONG
(Longs recebem dos Shorts quando o funding é negativo)
```json
{json.dumps(top_negative, ensure_ascii=False, indent=2)}
```

### Long/Short Ratio dos principais ativos
```json
{json.dumps(lsr_data, ensure_ascii=False, indent=2)}
```

## Critérios de Análise
1. Considere que operamos **APENAS MODO DIRECIONAL**. Nosso lucro ou prejuízo virá da soma de Funding PnL + Variação de Preço (Price PnL).
2. Não recomende posições neutras, de hedge ou Cash & Carry. O foco é receber o funding rate e avaliar o risco direcional.
3. Considere o **score** fornecido. SOMENTE recomende ativos com shouldOpen=true (score >= 50). Se a volatilidade direcional é demasiada frente ao funding, não recomende.
4. Identifique as **5 melhores oportunidades** ordenadas por score.
5. Para cada ativo recomendado, detalhe a justificativa focando na relação de assimetria: "O funding alto compensa o risco de operar vendido (SHORT) frente à volatilidade atual?", "Isso indica um topo/fundo exausto?".
6. Se houver divergência entre funding rate e LSR, alerte que pode haver squeeze direcional.
7. Destaque moedas com intervalos menores (ex: 4h) onde o pagamento cai mais vezes.

## Formato de Resposta OBRIGATÓRIO

Responda EXCLUSIVAMENTE com um bloco JSON válido no formato abaixo (sem texto fora do JSON, sem markdown fora do JSON):

```json
{{
  "market_overview": "Texto em markdown com visão geral do mercado (2-3 parágrafos). Use **negrito** para destaques, emojis para visual. Fale sobre sentimento, tendência de funding e a relação com o preço.",
  "recommended_coins": [
    {{
      "symbol": "BTCUSDT",
      "direction": "SHORT",
      "score": 85,
      "confidence": "FORTE",
      "rate_percent": 0.0523,
      "monthly_rate": 31.4,
      "funding_interval": 8,
      "justification": "Funding extremamente elevado sinalizando exaustão de tendência de alta. O prêmio compensa o risco de entrar SHORT agora.",
      "risk": "A moeda subiu 15% nas últimas 24h, pode buscar novo topo antes da reversão.",
      "strategy": "Funding Farming e Reversão"
    }}
  ]
}}
```

Regras:
- `recommended_coins` deve ter NO MÁXIMO 5 itens (apenas direction="LONG" ou "SHORT")
- `confidence` deve ser "FORTE", "MODERADO" ou "FRACO"
- `strategy` deve ser descritiva e voltada à direção (ex: "Funding Farming Direcional", "Aposta em Reversão (Squeeze)", etc). **NUNCA** usar "Hedge" ou "Arbitragem".
- `rate_percent` é a taxa por período em porcentagem (ex: 0.0523 para 0.0523%)
- `monthly_rate` é a taxa mensal em porcentagem
- Responda em português brasileiro
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return {
                "analysis": "⚠️ A IA não retornou resposta. Tente novamente.",
                "recommended_coins": [],
            }

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return {
                "analysis": "⚠️ Resposta vazia da IA.",
                "recommended_coins": [],
            }

        raw_text = parts[0].get("text", "")

        # Tentar extrair JSON da resposta
        return _parse_ai_response(raw_text)

    except httpx.HTTPStatusError as e:
        return {
            "analysis": f"❌ Erro na API Gemini ({e.response.status_code}): {e.response.text[:300]}",
            "recommended_coins": [],
        }
    except Exception as e:
        return {
            "analysis": f"❌ Erro ao comunicar com a IA: {str(e)}",
            "recommended_coins": [],
        }


def _parse_ai_response(raw_text: str) -> dict:
    """
    Tenta extrair JSON estruturado da resposta da IA.
    Fallback: retorna o texto bruto como análise.
    """
    try:
        # Tentar extrair JSON de dentro de blocos ```json ... ```
        json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', raw_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Tentar parsear o texto inteiro como JSON
            json_str = raw_text.strip()

        parsed = json.loads(json_str)

        market_overview = parsed.get("market_overview", "")
        recommended_coins = parsed.get("recommended_coins", [])

        # Validar e limpar recommended_coins
        clean_coins = []
        for coin in recommended_coins[:5]:
            clean_coins.append({
                "symbol": coin.get("symbol", ""),
                "direction": coin.get("direction", "LONG"),
                "score": coin.get("score", 0),
                "confidence": coin.get("confidence", "MODERADO"),
                "rate_percent": coin.get("rate_percent", 0),
                "monthly_rate": coin.get("monthly_rate", 0),
                "funding_interval": coin.get("funding_interval", 8),
                "justification": coin.get("justification", ""),
                "risk": coin.get("risk", ""),
                "strategy": coin.get("strategy", "Operação Direta"),
            })

        return {
            "analysis": market_overview,
            "recommended_coins": clean_coins,
        }

    except (json.JSONDecodeError, KeyError, TypeError):
        # Fallback: retornar texto bruto como análise
        return {
            "analysis": raw_text,
            "recommended_coins": [],
        }


async def analyze_bot_cycle(
    bot_config: dict,
    trades: list[dict],
    trigger_type: str = "manual",
    history_context: str = "",
) -> dict:
    """
    Analisa o desempenho de um bot após um ciclo completo de trades.
    Retorna análise em markdown + sugestões estruturadas de configuração.
    """
    if not GEMINI_API_KEY:
        return {
            "analysis": "❌ Chave da API Gemini não configurada.",
            "suggested_config": {},
        }

    if not trades:
        return {
            "analysis": "⚠️ Nenhum trade encontrado para análise.",
            "suggested_config": {},
        }

    # Resumo de performance
    total_pnl = sum(t.get("totalPnl", 0) for t in trades)
    total_funding = sum(t.get("fundingPnl", 0) for t in trades)
    total_fees = sum(t.get("feeCost", 0) for t in trades)
    total_price_pnl = sum(t.get("pricePnl", 0) for t in trades)
    wins = sum(1 for t in trades if t.get("totalPnl", 0) > 0)
    losses = len(trades) - wins
    win_rate = (wins / len(trades) * 100) if trades else 0

    avg_pnl_pct = sum(t.get("totalPnlPct", 0) for t in trades) / len(trades) if trades else 0
    avg_price_pnl_pct = sum(t.get("pricePnlPct", 0) for t in trades) / len(trades) if trades else 0

    # Profit Factor
    gross_wins = sum(t.get("totalPnl", 0) for t in trades if t.get("totalPnl", 0) > 0)
    gross_losses = abs(sum(t.get("totalPnl", 0) for t in trades if t.get("totalPnl", 0) < 0))
    profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else float("inf")

    # Fee Efficiency: quanto de funding foi capturado vs quanto pagou de fee
    fee_efficiency = round(total_funding / total_fees, 2) if total_fees > 0 else float("inf")

    # Máximo de losses consecutivos
    max_consec_losses = 0
    cur_consec = 0
    for t in trades:
        if t.get("totalPnl", 0) < 0:
            cur_consec += 1
            max_consec_losses = max(max_consec_losses, cur_consec)
        else:
            cur_consec = 0

    # PnL por motivo de fechamento
    reasons: dict[str, dict] = {}
    for t in trades:
        r = t.get("closeReason", "unknown")
        if r not in reasons:
            reasons[r] = {"count": 0, "total_pnl": 0.0}
        reasons[r]["count"] += 1
        reasons[r]["total_pnl"] = round(reasons[r]["total_pnl"] + t.get("totalPnl", 0), 4)

    # PnL por símbolo (top 5 melhores e piores)
    sym_pnl: dict[str, float] = {}
    for t in trades:
        s = t.get("symbol", "?")
        sym_pnl[s] = round(sym_pnl.get(s, 0.0) + t.get("totalPnl", 0), 4)
    sym_sorted = sorted(sym_pnl.items(), key=lambda x: x[1])
    worst_symbols = sym_sorted[:5]
    best_symbols = sym_sorted[-5:][::-1]

    # PnL por direção
    long_trades = [t for t in trades if t.get("direction") == "LONG"]
    short_trades = [t for t in trades if t.get("direction") == "SHORT"]
    long_pnl = round(sum(t.get("totalPnl", 0) for t in long_trades), 4)
    short_pnl = round(sum(t.get("totalPnl", 0) for t in short_trades), 4)
    longs = len(long_trades)
    shorts = len(short_trades)

    operation_mode = bot_config.get("operationMode", "manual")
    exit_seconds_display = "N/A (counter_trend sem timeout)" if operation_mode == "counter_trend" else f"{bot_config.get('exitSeconds', 30)}s"

    prompt = f"""Você é um consultor quantitativo especializado que opera nosso sistema de Funding Rate Trading para criptomoedas. Você tem conhecimento profundo de como nossa aplicação funciona e vai analisar o desempenho de um bot para sugerir melhorias.

## 📘 COMO NOSSA APLICAÇÃO FUNCIONA

### Conceito Core — Funding Rate Sniping
Exchanges de futuros perpétuos (Binance, Bybit) cobram/pagam "funding rate" a cada 8h (algumas 4h). Nosso bot faz **sniping**: entra segundos ANTES do settlement do funding, captura o pagamento, e sai segundos DEPOIS. O lucro vem do funding recebido menos a variação de preço e fees.

**Fluxo típico de um snipe:**
1. Bot monitora o tempo até o próximo funding de cada símbolo
2. Quando faltam `entrySeconds` para o settlement, abre posição na direção que RECEBE funding
3. Aguarda o settlement (recebe o funding rate automaticamente)
4. Após `exitSeconds` do settlement, fecha a posição
5. Lucro = funding recebido − variação de preço − taxas (fees)

**Regra de direção:**
- Funding Rate > 0 → Shorts pagam Longs → bot entra SHORT (recebe o funding)
- Funding Rate < 0 → Longs pagam Shorts → bot entra LONG (recebe o funding)

### Modos de Operação

1. **manual** — O usuário define manualmente quais símbolos (moedas) operar. O bot só faz snipe nessas moedas.

2. **auto_expiring** — Seleciona automaticamente as melhores moedas baseado em score + proximidade do settlement. Só seleciona moedas cujo funding vira dentro de `windowMinutes`. Ideal para capturar oportunidades imediatas.

3. **auto_strongest** — Seleciona moedas com o maior score de oportunidade geral, sem filtrar por proximidade. Pode pegar moedas cujo funding vira em horas.

4. **auto_highest_rate** — Seleciona moedas com o maior funding rate absoluto, sem exigir score mínimo. Mais agressivo, ignora sistema de scoring.

5. **counter_trend** — Estratégia oposta: entra APÓS a virada do funding, na direção CONTRÁRIA. Se funding era positivo (shorts pagavam) → muitos shorts fecham na virada → pressão compradora → LONG. Não captura funding, lucra com movimento de preço pós-settlement.

### Sistema de Scoring (0-100 pontos)
Cada ativo recebe um score baseado em:
- **Magnitude do funding** (0-30 pts): quanto maior |funding rate|, melhor
- **Risco/Retorno** (0-30 pts): funding vs volatilidade de preço
- **Volume/Liquidez** (0-20 pts): maior volume = menor slippage
- **Bônus intervalo** (0-10 pts): funding 4h dá bônus vs 8h
- **Proximidade settlement** (-10 a +10 pts): penaliza muito longe ou muito perto
- **Penalidades**: moedas de baixo volume ou extrema volatilidade são vetadas (score=0)

### Parâmetros Configuráveis
- **entrySeconds**: quantos segundos ANTES do funding para abrir posição. Valores menores = menos exposição ao preço mas risco de não conseguir entrar. No counter_trend, é o delay APÓS a virada.
- **exitSeconds**: quantos segundos APÓS o funding para fechar (somente modos de funding sniping). No counter_trend não existe timeout máximo por tempo.
- **leverage**: alavancagem da posição (1x-20x). Mais alavancagem = mais lucro por funding mas mais risco de liquidação.
- **stopLossPct**: % de perda máxima sobre a MARGEM antes de forçar fechamento.
- **minProfitPct**: % mínima de lucro sobre a margem para considerar fechar. Se não atingir, espera ou fecha no exitSeconds (somente modos de funding).
- **targetTakeProfitPct**: % alvo de lucro — se atingido, fecha antecipadamente com ordem limite.
- **trailingStartProfitPct**: lucro mínimo (%) da margem para armar o trailing stop. Antes disso, trailing não atua.
- **feeType**: "maker" (0.02%) ou "taker" (0.05%). Maker usa ordem limite (mais barato mas pode não executar). Taker usa ordem mercado (sempre executa).
- **makerTimeoutSeconds**: se usar maker e ordem não executar em X segundos, cancela e refaz como taker.
- **autoMaxSymbols**: número máximo de moedas simultâneas nos modos auto.
- **autoMinScore**: score mínimo para um ativo ser considerado (modos auto_expiring e auto_strongest).
- **autoWindowMinutes**: janela de proximidade do settlement (só auto_expiring).

### Motivos de Fechamento (closeReason)
- **"funding"**: fechamento normal após exitSeconds — cenário ideal
- **"stop_loss"**: preço moveu contra a posição além do stopLossPct
- **"take_profit"**: atingiu o targetTakeProfitPct
- **"manual"**: fechado manualmente pelo usuário
- **"timeout"**: tempo máximo de posição atingido (somente modos com funding; não se aplica ao counter_trend)

### Cálculo de PnL
- **fundingPnl** = |fundingRate| × valor da posição (sempre positivo no snipe normal)
- **pricePnl** = (exitPrice − entryPrice) × size (para LONG) ou (entryPrice − exitPrice) × size (para SHORT)
- **feeCost** = valor da posição × feeRate × 2 (entrada + saída)
- **totalPnl** = fundingPnl + pricePnl − feeCost

## ⚙️ CONFIGURAÇÃO ATUAL DO BOT
- **Modo**: {operation_mode}
- **Exchange**: {bot_config.get('exchange', 'binance')}
- **Capital**: ${bot_config.get('capital', 0):.2f}
- **Alavancagem**: {bot_config.get('leverage', 1)}x
- **Fee type**: {bot_config.get('feeType', 'maker')}
- **Entry seconds**: {bot_config.get('entrySeconds', 30)}s
- **Exit seconds**: {exit_seconds_display}
- **Stop Loss**: {bot_config.get('stopLossPct', 'Não configurado')}%
- **Min Profit**: {bot_config.get('minProfitPct', 'Não configurado')}%
- **Take Profit**: {bot_config.get('targetTakeProfitPct', 'Não configurado')}%
- **Trailing Start Profit**: {bot_config.get('trailingStartProfitPct', 'Não configurado')}%
- **Max Symbols**: {bot_config.get('autoMaxSymbols', 8)}
- **Min Score**: {bot_config.get('autoMinScore', 50)}
- **Maker timeout**: {bot_config.get('makerTimeoutSeconds', 8)}s
- **Símbolos**: {', '.join(bot_config.get('symbols', [])[:20])}

## 📊 PERFORMANCE DO CICLO ({len(trades)} trades)
- **PnL Total**: ${total_pnl:.4f}
- **Funding PnL**: ${total_funding:.4f}
- **Price PnL**: ${total_price_pnl:.4f}
- **Fees Total**: ${total_fees:.4f}
- **Win Rate**: {win_rate:.1f}% ({wins}W / {losses}L)
- **Profit Factor**: {profit_factor} (>1.5 = bom, <1.0 = sem edge)
- **Fee Efficiency**: {fee_efficiency}x (funding/fees — deve ser >2 para ser sustentável)
- **Max Losses Consecutivos**: {max_consec_losses}
- **PnL Médio %**: {avg_pnl_pct:.4f}%
- **Price PnL Médio %**: {avg_price_pnl_pct:.4f}%
- **Por Direção**: LONGs={longs} trades (PnL=${long_pnl:.4f}) / SHORTs={shorts} trades (PnL=${short_pnl:.4f})
- **Por Motivo de Fechamento**: {json.dumps(reasons, ensure_ascii=False)}
- **Piores Símbolos**: {dict(worst_symbols)}
- **Melhores Símbolos**: {dict(best_symbols)}

## 📋 TRADES DETALHADOS (últimos 20)
```json
{json.dumps(trades[:20], ensure_ascii=False, indent=2, default=str)}
```

## 🎯 INSTRUÇÕES

Analise o desempenho usando seu conhecimento sobre como nossa aplicação funciona. Identifique:
1. Se o bot está capturando funding eficientemente
2. Se as perdas de preço (pricePnl) estão anulando os ganhos de funding
3. Se os parâmetros de timing (entry/exit) estão adequados
4. Se o modo de operação escolhido é o melhor para o cenário atual
5. Se há problemas com fees, slippage ou stop losses disparando cedo demais

Responda EXCLUSIVAMENTE com JSON:

```json
{{
  "summary": "Resumo rápido e direto (1-2 frases) do resultado e do principal problema/solução.",
  "details": "Texto em markdown. Use **negrito**, emojis e bullet points. Inclua: 1) Visão geral do ciclo, 2) Pontos fortes, 3) Pontos fracos. Foque em ir direto ao ponto. Em português brasileiro.",
  "suggested_config": {{
    "entrySeconds": {{
      "value": 25,
      "reason": "Reduzido para não perder o repique inicial."
    }},
    "exitSeconds": {{
      "value": 45,
      "reason": "Aumentado para capturar mais do movimento."
    }}
  }}
}}
```

HISTÓRICO DE ALTERAÇÕES AUTOMÁTICAS:
{history_context if history_context else "Nenhuma alteração automática registrada ainda."}

Regras:
- `suggested_config` deve conter APENAS campos que você sugere ALTERAR formados por um objeto com `value` e `reason`. Campos disponíveis: entrySeconds, exitSeconds, stopLossPct, minProfitPct, autoMaxSymbols, leverage, makerTimeoutSeconds
- Campos disponíveis também incluem: trailingStartProfitPct
- Se o modo atual for `counter_trend`, NÃO sugira `exitSeconds`.
- Se o bot está performando bem, `suggested_config` deve ser {{}} (vazio)
- O motivo (`reason`) deve ser curto e ir direto ao ponto.
- Use o histórico de alterações anteriores para aprender o que funcionou e o que não funcionou.
- Responda em português brasileiro.
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 4096,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return {"analysis": "⚠️ A IA não retornou resposta.", "suggested_config": {}}

        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        result = _parse_bot_analysis(raw_text)
        if operation_mode == "counter_trend":
            result.get("suggested_config", {}).pop("exitSeconds", None)
        return result

    except httpx.HTTPStatusError as e:
        return {
            "analysis": f"❌ Erro na API Gemini ({e.response.status_code}): {e.response.text[:300]}",
            "suggested_config": {},
        }
    except Exception as e:
        return {
            "analysis": f"❌ Erro ao comunicar com a IA: {str(e)}",
            "suggested_config": {},
        }


async def analyze_symbol_for_blacklist(
    symbol: str,
    consecutive_losses: int,
    recent_trades: list,
) -> dict:
    """
    Analisa um símbolo com múltiplos losses consecutivos e decide se deve ser bloqueado.
    Retorna: {"should_blacklist": bool, "cooldown_hours": int, "reason": str, "analysis": str}
    """
    if not GEMINI_API_KEY:
        return {"should_blacklist": False, "cooldown_hours": 0, "reason": "API key não configurada", "analysis": ""}

    total_pnl = sum(float(t.get("total_pnl", 0)) for t in recent_trades)
    avg_pnl = total_pnl / len(recent_trades) if recent_trades else 0
    wins = sum(1 for t in recent_trades if float(t.get("total_pnl", 0)) >= 0)
    losses_count = len(recent_trades) - wins

    prompt = f"""Você é um gerenciador de risco para um sistema de Funding Rate Sniping em criptomoedas.

O bot detectou **{consecutive_losses} losses consecutivos** no símbolo **{symbol}**.

## Trades recentes de {symbol}
```json
{json.dumps(recent_trades, ensure_ascii=False, indent=2, default=str)}
```

## Estatísticas
- Total de trades analisados: {len(recent_trades)}
- Wins / Losses: {wins}W / {losses_count}L
- PnL total acumulado: ${total_pnl:.4f}
- PnL médio por trade: ${avg_pnl:.4f}

## Sua tarefa
Analise se este símbolo deve ser temporariamente bloqueado do bot automático para proteger o capital.
Considere:
1. Os losses são por variação de preço (pricePnl negativo) ou falha no funding?
2. A magnitude das perdas é crescente (tendência piorando)?
3. O padrão sugere um problema estrutural ou apenas volatilidade passageira?
4. Qual seria o tempo ideal de cooldown para o mercado se reorganizar?

Responda EXCLUSIVAMENTE com JSON:

```json
{{
  "should_blacklist": true,
  "cooldown_hours": 8,
  "reason": "Perdas crescentes por volatilidade direcional; funding não compensa o risco.",
  "analysis": "Análise detalhada em markdown..."
}}
```

Regras:
- `should_blacklist`: true apenas se os losses indicam risco estrutural real
- `cooldown_hours`: 0 (sem bloqueio), 4, 8, 12 ou 24 horas
- `reason`: máx 200 caracteres, direto ao ponto
- Se os losses são pequenos e aleatórios (< 0.1% da margem cada), prefira NÃO bloquear
- Responda em português brasileiro
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GEMINI_URL, params={"key": GEMINI_API_KEY}, json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw_text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', raw_text, re.DOTALL)
        json_str = json_match.group(1).strip() if json_match else raw_text.strip()
        parsed = json.loads(json_str)

        cooldown = int(parsed.get("cooldown_hours", 0))
        if cooldown not in (0, 4, 8, 12, 24):
            cooldown = 0

        return {
            "should_blacklist": bool(parsed.get("should_blacklist", False)),
            "cooldown_hours": cooldown,
            "reason": str(parsed.get("reason", ""))[:300],
            "analysis": str(parsed.get("analysis", "")),
        }
    except Exception as e:
        return {"should_blacklist": False, "cooldown_hours": 0, "reason": str(e)[:200], "analysis": ""}


async def generate_bot_config(
    recommended_coins: list,
    capital: float,
    leverage: int,
    exchange: str,
    operation_mode: str,
    historical_stats: dict,
) -> dict:
    """
    Gera configuração de bot otimizada pela IA a partir de um relatório de análise.
    Retorna configuração compatível com start_trading().
    """
    if not GEMINI_API_KEY:
        raise ValueError("Chave da API Gemini não configurada.")
    if capital < 10:
        raise ValueError("Capital mínimo é $10.")

    # Sizing dinâmico: ajusta capital baseado na confiança das moedas top
    top_coins = sorted(recommended_coins, key=lambda c: c.get("score", 0), reverse=True)[:5]
    top_confidence = top_coins[0].get("confidence", "MODERADO") if top_coins else "MODERADO"
    if top_confidence == "FORTE":
        capital_suggested = capital
    elif top_confidence == "MODERADO":
        capital_suggested = round(capital * 0.8, 2)
    else:
        capital_suggested = round(capital * 0.6, 2)

    now_str = datetime.now(timezone.utc).strftime("%H%M")
    # Calibra stopLoss para a alavancagem informada
    _sl_min = max(5.0, round(leverage * 1.5, 1))
    _sl_suggested = max(5.0, min(20.0, round(leverage * 2.0, 1)))

    prompt = f"""Você é um especialista em Funding Rate Sniping e deve criar a configuração ideal para um bot automático.

## Dados do Relatório IA — Moedas recomendadas (máx 5)
```json
{json.dumps(top_coins, ensure_ascii=False, indent=2)}
```

## Parâmetros solicitados pelo usuário
- Capital disponível: ${capital:.2f} (sugerido usar ${capital_suggested:.2f} com base na confiança)
- Alavancagem: {leverage}x
- Exchange: {exchange.upper()}
- Modo de operação preferido: {operation_mode or "auto_strongest"}

## Histórico de sucesso do usuário (parâmetros de trades lucrativos)
```json
{json.dumps(historical_stats, ensure_ascii=False, indent=2)}
```

## Detecção de Regime de Mercado
Com base nas moedas recomendadas e suas taxas:
- Analise se o mercado está calmo (taxas baixas/uniformes), volátil (alta dispersão) ou em tendência (maioria no mesmo lado)
- Regime calmo: prefira entrySeconds menor, stopLossPct maior
- Regime volátil: prefira stopLossPct mais justo, makerTimeoutSeconds menor
- Regime tendência: considere aumentar autoMaxSymbols na direção dominante

## Sua tarefa
Crie a configuração JSON ideal para um bot de funding rate sniping considerando:
1. As moedas com maior score e confiança (no máx 8 símbolos)
2. O histórico de parâmetros que deram mais lucro ao usuário
3. O regime de mercado atual
4. O capital e alavancagem informados

Responda EXCLUSIVAMENTE com JSON:

```json
{{
  "sessionName": "IA-Bot-{exchange.upper()}-{now_str}",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "operationMode": "auto_strongest",
  "entrySeconds": 25,
  "exitSeconds": 45,
  "stopLossPct": {_sl_suggested:.1f},
  "autoMinScore": 55,
  "autoMaxSymbols": 5,
  "autoWindowMinutes": 30,
  "feeType": "maker",
  "capital": {capital_suggested:.2f},
  "leverage": {leverage},
  "ai_justification": "Justificativa da configuração em português..."
}}
```

Regras:
- `symbols` deve usar APENAS moedas da lista recomendada (máx 8)
- `operationMode` deve ser: auto_strongest, auto_expiring, ou counter_trend
- `entrySeconds` entre 15 e 60
- `exitSeconds` entre 20 e 90 (omita se counter_trend)
- `stopLossPct` entre **{_sl_min:.1f} e 20.0** para {leverage}x de alavancagem (price_move_stop = stopLossPct/leverage — valores pequenos disparam no ruído!)
- `autoMinScore` entre 45 e 75
- `autoMaxSymbols` entre 2 e 8
- `autoWindowMinutes` entre 15 e 90, obrigatório se operationMode="auto_expiring"; omita nos demais
- `feeType` deve ser "maker" ou "taker"
- `capital` não pode exceder ${capital:.2f}
- NÃO inclua `minProfitPct` — em sniping o bot fecha no exitSeconds normalmente
- Responda em português brasileiro
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            GEMINI_URL, params={"key": GEMINI_API_KEY}, json=payload,
        )
        response.raise_for_status()
        data = response.json()

    raw_text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', raw_text, re.DOTALL)
    json_str = json_match.group(1).strip() if json_match else raw_text.strip()
    parsed = json.loads(json_str)

    # Validações e clamps básicos de segurança
    parsed["capital"] = min(float(parsed.get("capital", capital_suggested)), capital)
    parsed["leverage"] = leverage
    parsed["symbols"] = [s for s in (parsed.get("symbols") or []) if s][:8]
    if not parsed["symbols"]:
        parsed["symbols"] = [c["symbol"] for c in top_coins[:5]]
    if "stopLossPct" in parsed:
        parsed["stopLossPct"] = max(_sl_min, min(25.0, float(parsed["stopLossPct"])))
    if "autoWindowMinutes" in parsed:
        parsed["autoWindowMinutes"] = max(15, min(90, int(parsed["autoWindowMinutes"])))

    return parsed


async def analyze_market_for_bot_config(
    capital: float,
    leverage: int,
    exchange: str,
    historical_stats: dict,
    live_rates: list[dict],
) -> dict:
    """
    Analisa mercado ao vivo (sem relatório prévio) e retorna config de bot otimizada.
    Retorna JSON compatível com start_trading().
    """
    if not GEMINI_API_KEY:
        raise ValueError("Chave da API Gemini não configurada.")
    if capital < 10:
        raise ValueError("Capital mínimo é $10.")

    now_str = datetime.now(timezone.utc).strftime("%H%M")
    # Calibra stopLoss baseado na alavancagem: price_move_para_stop = stopLossPct / leverage
    # Valores muito baixos disparam no ruído normal de mercado e destroem o edge do bot
    stop_loss_min = max(5.0, round(leverage * 1.5, 1))
    stop_loss_suggested = max(5.0, min(20.0, round(leverage * 2.0, 1)))
    stop_loss_volatil = min(20.0, round(stop_loss_suggested * 1.3, 1))
    stop_loss_tendencia = min(20.0, round(stop_loss_suggested * 1.2, 1))
    price_trigger_5 = round(5 / leverage, 2)
    price_trigger_10 = round(10 / leverage, 2)
    price_trigger_15 = round(15 / leverage, 2)
    price_trigger_20 = round(20 / leverage, 2)
    price_trigger_at_min = round(stop_loss_min / leverage, 2)

    prompt = f"""Você é um especialista em Funding Rate Sniping e deve criar a configuração ideal para um bot automático, analisando as taxas de funding ao vivo.

## Taxas de Funding ao vivo — {exchange.upper()} (top 30 por |taxa|)
```json
{json.dumps(live_rates[:30], ensure_ascii=False, indent=2)}
```

## Parâmetros solicitados pelo usuário
- Capital disponível: ${capital:.2f}
- Alavancagem: {leverage}x
- Exchange: {exchange.upper()}

## Histórico de sucesso do usuário (parâmetros de trades lucrativos)
```json
{json.dumps(historical_stats, ensure_ascii=False, indent=2)}
```

## ⚠️ Relação Stop Loss × Alavancagem — LEIA COM ATENÇÃO
`stopLossPct` é % da MARGEM investida, NÃO do preço.
Fórmula: variação de preço para acionar o stop = `stopLossPct ÷ alavancagem`

Com alavancagem **{leverage}x**, cada 1% de stopLoss corresponde a **{round(1/leverage, 3):.3f}%** de variação de preço.

Tabela de referência para {leverage}x:
- stopLossPct=5%  → stop aciona com **{price_trigger_5:.2f}%** de variação de preço
- stopLossPct=10% → stop aciona com **{price_trigger_10:.2f}%** de variação de preço
- stopLossPct=15% → stop aciona com **{price_trigger_15:.2f}%** de variação de preço
- stopLossPct=20% → stop aciona com **{price_trigger_20:.2f}%** de variação de preço

**REGRA CRÍTICA:** com {leverage}x use `stopLossPct` mínimo de **{stop_loss_min:.1f}%** (stop aciona com {price_trigger_at_min:.2f}% de variação de preço).
Valores abaixo de {stop_loss_min:.1f}% causam stops acidentais por ruído normal de mercado — elimina o edge do bot.

## Detecção de Regime de Mercado
Com base nas taxas ao vivo (campo `price_24h_pcnt` = variação de preço em 24h):

**MERCADO CALMO** (|price_24h_pcnt| < 2% na maioria, taxas uniformes):
- `entrySeconds`=25-35, `exitSeconds`=45-60, `stopLossPct`={stop_loss_suggested:.1f}%
- `autoMaxSymbols`=5-8, `operationMode`="auto_strongest"
- Captura as maiores taxas sem urgência, risco de preço baixo

**MERCADO VOLÁTIL** (|price_24h_pcnt| > 5% ou alta dispersão nas taxas):
- `entrySeconds`=45-60, `exitSeconds`=25-40 (sair rápido antes da reversão)
- `stopLossPct`={stop_loss_volatil:.1f}% (mais folga para absorver ruído)
- `autoMaxSymbols`=2-3, `operationMode`="auto_expiring", `autoWindowMinutes`=20-30
- Operar apenas oportunidades imediatas reduz exposição ao risco de preço

**MERCADO EM TENDÊNCIA** (maioria das taxas no mesmo sinal + preços unidirecionais):
- Prefira símbolos com rate NA DIREÇÃO CONTRÁRIA à tendência do preço (squeeze risk menor)
- `entrySeconds`=35-50, `stopLossPct`={stop_loss_tendencia:.1f}%
- `operationMode`="auto_strongest" focando nos melhores taxa/risco

## Sua tarefa
Selecione os melhores símbolos e crie a configuração ideal considerando:
1. Símbolos com maior |taxa de funding| E volume alto (`volume_24h` — menos slippage)
2. Evite símbolos com volume diário abaixo de $500k (slippage alto prejudica o edge)
3. Calibre `stopLossPct` para {leverage}x de alavancagem — mínimo obrigatório: {stop_loss_min:.1f}%
4. Detecte o regime de mercado e ajuste timing/risco conforme a tabela acima
5. Use o histórico do usuário para parâmetros que já funcionaram antes

Responda EXCLUSIVAMENTE com JSON:

```json
{{
  "sessionName": "IA-Live-{exchange.upper()}-{now_str}",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "operationMode": "auto_strongest",
  "entrySeconds": 30,
  "exitSeconds": 50,
  "stopLossPct": {stop_loss_suggested:.1f},
  "autoMinScore": 55,
  "autoMaxSymbols": 5,
  "autoWindowMinutes": 30,
  "feeType": "maker",
  "capital": {capital:.2f},
  "leverage": {leverage},
  "ai_justification": "Justificativa da configuração em português..."
}}
```

Regras obrigatórias:
- `symbols`: use APENAS símbolos das taxas ao vivo; máx 8; priorize volume alto e maior |taxa|
- `operationMode`: "auto_strongest", "auto_expiring" ou "counter_trend"
- `entrySeconds`: entre 15 e 60
- `exitSeconds`: entre 20 e 90 (omita se operationMode="counter_trend")
- `stopLossPct`: entre **{stop_loss_min:.1f} e 20.0** para {leverage}x de alavancagem — NUNCA abaixo de {stop_loss_min:.1f}%
- `autoMinScore`: entre 45 e 75
- `autoMaxSymbols`: entre 2 e 8
- `autoWindowMinutes`: entre 15 e 90, obrigatório se operationMode="auto_expiring"; omita nos demais modos
- `feeType`: "maker" (mais barato, requer liquidez) ou "taker" (sempre executa)
- `capital`: não pode exceder ${capital:.2f}
- NÃO inclua `minProfitPct` — em sniping o bot fecha no exitSeconds normalmente; minProfitPct causa fechamentos prematuros sem benefício claro
- Responda em português brasileiro
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            GEMINI_URL, params={"key": GEMINI_API_KEY}, json=payload,
        )
        response.raise_for_status()
        data = response.json()

    # Detecta resposta bloqueada por filtro de segurança
    finish_reason = (
        data.get("candidates", [{}])[0].get("finishReason", "")
    )
    if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
        raise RuntimeError(f"Gemini bloqueou a resposta (finishReason={finish_reason}). Tente novamente.")

    raw_text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )

    parsed = _extract_json_from_gemini(raw_text)
    if parsed is None:
        raise RuntimeError(f"Gemini retornou resposta sem JSON válido. Resposta: {raw_text[:300]!r}")

    parsed["capital"] = min(float(parsed.get("capital", capital)), capital)
    parsed["leverage"] = leverage
    parsed["symbols"] = [s for s in (parsed.get("symbols") or []) if s][:8]
    if not parsed["symbols"]:
        parsed["symbols"] = [r["symbol"] for r in live_rates[:5] if r.get("symbol")]
    # Garante stopLoss dentro do range seguro para a alavancagem
    if "stopLossPct" in parsed:
        parsed["stopLossPct"] = max(stop_loss_min, min(25.0, float(parsed["stopLossPct"])))
    # Clamp de autoWindowMinutes (apenas para auto_expiring)
    if "autoWindowMinutes" in parsed:
        parsed["autoWindowMinutes"] = max(15, min(90, int(parsed["autoWindowMinutes"])))

    return parsed


def _extract_json_from_gemini(raw_text: str) -> dict | None:
    """
    Tenta extrair JSON da resposta do Gemini com múltiplos fallbacks:
    1. Bloco ```json ... ```
    2. Primeiro objeto JSON { ... } no texto
    Retorna None se não conseguir parsear.
    """
    if not raw_text or not raw_text.strip():
        return None
    # Fallback 1: bloco ```json ... ```
    json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', raw_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Fallback 2: bloco ``` ... ``` sem especificar linguagem
    code_match = re.search(r'```\s*\n?(.*?)\n?\s*```', raw_text, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Fallback 3: primeiro objeto JSON { ... } no texto inteiro
    obj_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass
    # Fallback 4: texto inteiro como JSON
    try:
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        return None


def _parse_bot_analysis(raw_text: str) -> dict:
    """Parse da resposta da IA para análise de bot."""
    try:
        json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', raw_text, re.DOTALL)
        json_str = json_match.group(1).strip() if json_match else raw_text.strip()
        parsed = json.loads(json_str)

        summary = parsed.get("summary", "")
        details = parsed.get("details", "")
        suggested = parsed.get("suggested_config", {})
        
        # Retro-compatibilidade se a IA retornar formato antigo
        if "analysis" in parsed and not details:
            details = parsed["analysis"]

        # Validar campos permitidos
        allowed = {"entrySeconds", "exitSeconds", "stopLossPct", "minProfitPct",
                    "autoMaxSymbols", "leverage", "makerTimeoutSeconds", "trailingStartProfitPct"}
        
        clean_config = {}
        for k, v in suggested.items():
            if k in allowed:
                # Tratar tanto formato novo {"value": 10, "reason": "..."} quanto antigo 10
                if isinstance(v, dict) and "value" in v:
                    clean_config[k] = {"value": v["value"], "reason": v.get("reason", "")}
                else:
                    clean_config[k] = {"value": v, "reason": ""}

        # Juntar summary e details usando uma tag que o frontend corta
        final_analysis = ""
        if summary:
            final_analysis = f"**Resumo:** {summary}\n\n<!-- MORE -->\n\n{details}"
        else:
            final_analysis = details

        return {"analysis": final_analysis, "suggested_config": clean_config}

    except (json.JSONDecodeError, KeyError, TypeError):
        return {"analysis": raw_text, "suggested_config": {}}
