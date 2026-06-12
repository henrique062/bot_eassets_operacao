# -*- coding: utf-8 -*-
"""
Gerador do painel PHOENIX (estilo Encryptos) a partir de um snapshot eassets-panel-*.json.

Uso:
    python gerar_painel.py [caminho_do_json] [caminho_saida_html]

Sem argumentos, usa o JSON mais recente da pasta e gera painel_phoenix.html.

O JSON traz indicadores brutos por símbolo. SCORE e SETUP NÃO existem no JSON:
são derivados aqui pela lógica estrutural inferida da metodologia (cards do painel
original). Os pesos abaixo são ajustáveis sem mexer no resto do código.
"""
import json
import math
import sys
import glob
import os
import datetime as dt

# Fuso de exibição: tudo no banco é UTC; exibimos em GMT-3 (BRT).
BRT = dt.timezone(dt.timedelta(hours=-3))


def to_brt(ts, fmt="%d/%m/%Y %H:%M"):
    """Converte um timestamp ISO em UTC para string formatada em GMT-3 (BRT)."""
    if not ts:
        return "—"
    try:
        d = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(BRT).strftime(fmt)
    except Exception:
        return str(ts)

# ---------------------------------------------------------------------------
# PESOS DO SCORE (0-100). Ajuste livremente.
# Lógica: força = alinhamento EXP_btc em 3 timeframes (1D/4h/1h) + atividade de
# robôs (trades/min) + capitulação de shorts (LSR trend negativo) + entrada de
# Open Interest (OI trend positivo) + bônus de RSI em zona de momentum.
# ---------------------------------------------------------------------------
W_EXP   = 45   # alinhamento estrutural EXP (1D/4h/1h)
W_ROBOS = 20   # atividade de robôs (trades_minute:5m)
W_LSR   = 15   # LSR trend negativo = shorts capitulando = combustível de alta
W_OI    = 12   # OI trend positivo = novas posições entrando
W_RSI   =  8   # bônus de momentum (RSI 4h alto em tendência de alta)

TOP_N = 10     # ativos exibidos por padrão (botão "ver mais" expande no painel)

# Escalas de saturação (a partir das estatísticas reais do snapshot)
EXP_SCALE = {"1D": 200.0, "4h": 100.0, "1h": 60.0}   # valor que satura em 1.0
EXP_TF_W  = {"1D": 0.25, "4h": 0.45, "1h": 0.30}      # peso por timeframe
ROBOS_LO, ROBOS_HI = 20.0, 2000.0                      # faixa log de trades/min
LSR_FULL  = 15.0     # |lsr_trend| que dá pontuação cheia
OI_FULL   = 15.0     # oi_trend que dá pontuação cheia


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def num(v):
    return v if isinstance(v, (int, float)) else None


def trades_oi(e):
    """TRADES 1D por $1M de OI = intensidade de robôs/SM relativa ao capital.

    Conceito Phoenix: moeda de OI baixo com volume de trades alto = interesse
    desproporcional, SM trabalhando o ativo de forma focada (algo sendo preparado).
    BTC e large caps ficam baixos; small caps em acumulação disparam.
    """
    t1d = num(e.get("trades:1D"))
    oi = num(e.get("oi:5m"))
    if t1d is None or not oi or oi <= 0:
        return None
    return t1d / (oi / 1e6)


# Limiares de T/OI (calibrados nas estatísticas reais do scan)
TOI_ATENCAO = 40000.0    # ~p90 — começa a chamar atenção
TOI_FORTE   = 68000.0    # ~p95 — interesse desproporcional claro


def exp_align(e):
    """Alinhamento ponderado de EXP_btc em 1D/4h/1h, em [-1, 1]."""
    total = 0.0
    for tf, w in EXP_TF_W.items():
        v = num(e.get(f"exp_btc:{tf}"))
        if v is None:
            continue
        total += w * clamp(v / EXP_SCALE[tf], -1.0, 1.0)
    return total


def compute_score(e):
    align = exp_align(e)
    exp_pts = clamp(align, 0.0, 1.0) * W_EXP

    tm = num(e.get("trades_minute:5m")) or 0.0
    if tm > 0:
        rn = (math.log10(tm) - math.log10(ROBOS_LO)) / (math.log10(ROBOS_HI) - math.log10(ROBOS_LO))
    else:
        rn = 0.0
    robos_pts = clamp(rn) * W_ROBOS

    lsrt = num(e.get("lsr_trend:5m")) or 0.0
    lsr_pts = clamp(-lsrt / LSR_FULL) * W_LSR      # negativo = bullish

    oit = num(e.get("oi_trend:5m")) or 0.0
    oi_pts = clamp(oit / OI_FULL) * W_OI

    rsi = num(e.get("rsi:4h")) or 50.0
    rsi_pts = clamp((rsi - 50.0) / 30.0) * W_RSI

    score = exp_pts + robos_pts + lsr_pts + oi_pts + rsi_pts
    return round(score), align


def classify_setup(e, align, toi=None):
    """Retorna (badge, classe_css). Prioridade: contradição > short > acum silenciosa > acum range > robôs > força."""
    pc1d = num(e.get("price_change:1D")) or 0.0
    e1d  = num(e.get("exp_btc:1D")) or 0.0
    e4h  = num(e.get("exp_btc:4h")) or 0.0
    e1h  = num(e.get("exp_btc:1h")) or 0.0
    tm   = num(e.get("trades_minute:5m")) or 0.0
    r4h  = num(e.get("range_level:4h")) or 0.0
    r1d  = num(e.get("range_level:1D")) or 0.0
    if toi is None:
        toi = trades_oi(e)

    lsrt = num(e.get("lsr_trend:5m")) or 0.0
    all_pos = e1d > 0 and e4h > 0 and e1h > 0

    # 1) Estrutura contraditória: preço sobe mas perde força vs BTC, ou TFs em conflito forte
    if (pc1d > 5 and e4h < -10) or (e1d > 50 and e4h < -10) or (pc1d > 5 and e1d < -50):
        return "ESTRUTURA CONTRADITÓRIA", "contra"

    # 2) Short entrando: shorts abrindo de forma agressiva sem estrutura de alta confirmada
    if lsrt <= -25 and not all_pos:
        return "SHORT ENTRANDO", "contra"

    # 3) Acumulação silenciosa: T/OI desproporcional com preço ainda parado = SM preparando
    if toi is not None and toi >= TOI_FORTE and pc1d < 6 and not all_pos:
        return "ACUM SILENCIOSA", "silent"

    # 4) Acumulação: range_level alto em 4h ou 1D
    if r4h >= 3 or r1d >= 3:
        return "ACUM 4H/1D", "acum"

    # 4) Robôs ligados: muita atividade + alinhamento positivo nos 3 TFs
    if tm >= 300 and all_pos:
        return "ROBOS LIGADOS", "robos-on"

    # 5) Robôs ativos: muita atividade mas alinhamento misto
    if tm >= 300:
        return "ROBOS ATIVO", "robos-act"

    # 6) Força estrutural: alinhamento positivo
    if e4h > 0 and (e1d > 0 or e1h > 0):
        return "FORÇA ESTRU", "forca"

    return "NEUTRO", "neutro"


# ---------------------------------------------------------------------------
# CHECKLIST DE ENTRADA (Protocolo Encryptos) — camada acionável
# Gate macro: só faz sentido caçar entrada quando o BTC está em RESET
# (RSI 30m/1h em neutralidade/sobrevenda). Nunca comprar em pump vertical.
# Setup de Ouro = confluência de força (exp_btc, trades) + financiamento
# (OI subindo, LSR<1, funding negativo) + acumulação (range_level).
# ---------------------------------------------------------------------------
BTC_RESET_RSI = 50.0     # RSI 30m/1h abaixo disso = reset/neutralidade (janela)
BTC_PUMP_RSI  = 68.0     # RSI alto = pump, evitar entradas
TPM_HOT       = 800.0    # trades/min absoluto = combustão clara
TPM_BASE      = 250.0    # piso para considerar aceleração relativa
TPM_ACCEL     = 1.4      # tm5m >= 1.4x tm1h = aceleração relativa


def btc_macro(btc):
    """Estado macro do BTC -> decide se a janela de entrada está aberta."""
    if not btc:
        return {"state": "—", "safe": False, "reset": False,
                "rsi_30m": None, "rsi_1h": None, "rsi_5m": None}
    r30 = num(btc.get("rsi:30m"))
    r1h = num(btc.get("rsi:1h"))
    r5m = num(btc.get("rsi:5m"))
    ref = r1h if r1h is not None else (r30 if r30 is not None else 50.0)
    if ref >= BTC_PUMP_RSI:
        state, safe, reset = "PUMP · EVITAR", False, False
    elif ref <= 30:
        state, safe, reset = "OVERSOLD · JANELA", True, True
    elif ref <= BTC_RESET_RSI:
        state, safe, reset = "RESET · NEUTRO", True, True
    else:
        state, safe, reset = "AQUECENDO · CAUTELA", False, False
    return {"state": state, "safe": safe, "reset": reset,
            "rsi_30m": r30, "rsi_1h": r1h, "rsi_5m": r5m}


def entry_checklist(e):
    """Avalia os 7 critérios do Setup de Ouro para uma moeda. Retorna dict + score."""
    e5  = num(e.get("exp_btc:5m"))
    e15 = num(e.get("exp_btc:15m"))
    e1h = num(e.get("exp_btc:1h"))
    tm5 = num(e.get("trades_minute:5m")) or 0.0
    tm1h = num(e.get("trades_minute:1h")) or 0.0
    lsr = num(e.get("lsr:5m"))
    lsrt = num(e.get("lsr_trend:5m"))
    oit = num(e.get("oi_trend:5m"))
    r1h_rsi = num(e.get("rsi:1h"))
    r4h_rsi = num(e.get("rsi:4h"))
    r4 = num(e.get("range_level:4h")) or 0.0
    rg1 = num(e.get("range_level:1h")) or 0.0
    fr = num(e.get("fr"))

    chk = {
        # força relativa vs BTC nos TFs curtos (verde em 5m/15m/1h)
        "exp_pos": bool(e5 and e15 and e1h and e5 > 0 and e15 > 0 and e1h > 0),
        # combustão: trades acelerando (absoluto ou salto relativo)
        "tpm_hot": tm5 >= TPM_HOT or (tm5 >= TPM_BASE and tm1h > 0 and tm5 >= TPM_ACCEL * tm1h),
        # combustível: varejo/elite short (LSR<1 ou caindo)
        "lsr_fuel": (lsr is not None and lsr < 1.0) or (lsrt is not None and lsrt < -2),
        # dinheiro novo entrando
        "oi_in": oit is not None and oit > 0,
        # RSI quente mas com espaço (não exausto)
        "rsi_runway": r1h_rsi is not None and r1h_rsi >= 50 and (r4h_rsi is None or r4h_rsi < 70),
        # mola comprimida (acumulação)
        "accumulation": r4 >= 3 or rg1 >= 4,
        # shorts presos (funding negativo = primed pra short squeeze)
        "funding_neg": fr is not None and fr < 0,
    }
    chk["score"] = sum(1 for k, v in chk.items() if k != "score" and v)
    return chk


def setup_grade(chk, btc_safe):
    """Classifica a qualidade da entrada. Exige gate do BTC + critérios-núcleo."""
    s = chk["score"]
    core_ok = chk["exp_pos"] and chk["tpm_hot"]
    if btc_safe and core_ok and s >= 5:
        return "SETUP DE OURO", "ouro", s
    if btc_safe and s >= 4:
        return "PARCIAL", "parcial", s
    return "", "none", s


def is_trap(e):
    """Armadilha de varejo: preço caindo + LSR subindo + OI caindo."""
    pc = num(e.get("price_change:1D")) or 0.0
    lsrt = num(e.get("lsr_trend:5m")) or 0.0
    oit = num(e.get("oi_trend:5m")) or 0.0
    return pc < 0 and lsrt > 1 and oit < 0


def fmt_price(p):
    if p is None:
        return "—"
    if p >= 100:
        return f"${p:,.2f}"
    if p >= 1:
        return f"${p:.4f}"
    return f"${p:.5f}"


def fmt_usd(v):
    if v is None:
        return "—"
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= div:
            return f"${v/div:.1f}{suf}"
    return f"${v:.0f}"


def fmt_num(v, dec=2, plus=False):
    if v is None:
        return "—"
    s = f"{v:+.{dec}f}" if plus else f"{v:.{dec}f}"
    return s


def fmt_compact(v):
    """Número grande compacto: 751949 -> 752K, 14216467 -> 14.2M."""
    if v is None:
        return "—"
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{v/div:.1f}{suf}"
    return f"{v:.0f}"


def toi_cls(v):
    """Classe de cor para T/OI por intensidade."""
    if v is None:
        return "muted"
    if v >= TOI_FORTE:
        return "toi-hi"
    if v >= TOI_ATENCAO:
        return "toi-mid"
    return "muted"


def build_rows(data, btc=None):
    if btc is None:
        btc = data.get("BTCUSDT")
    macro = btc_macro(btc)
    rows = []
    for sym, e in data.items():
        score, align = compute_score(e)
        toi = trades_oi(e)
        badge, cls = classify_setup(e, align, toi)
        chk = entry_checklist(e)
        grade, grade_cls, escore = setup_grade(chk, macro["safe"])
        rows.append({
            "symbol": sym,
            "asset": sym.replace("USDT", ""),
            "toi": toi,
            "trades1d": num(e.get("trades:1D")),
            "entry_score": escore,
            "entry_grade": grade,
            "entry_cls": grade_cls,
            "checklist": chk,
            "trap": is_trap(e),
            "price": fmt_price(num(e.get("price"))),
            "change": num(e.get("price_change:1D")),
            "score": score,
            "badge": badge,
            "badge_cls": cls,
            "trades": num(e.get("trades_minute:5m")),
            "exp1d": num(e.get("exp_btc:1D")),
            "exp4h": num(e.get("exp_btc:4h")),
            "exp1h": num(e.get("exp_btc:1h")),
            "oitrend": num(e.get("oi_trend:5m")),
            "lsr": num(e.get("lsr:5m")),
            "lsrtrend": num(e.get("lsr_trend:5m")),
            "rsi4h": num(e.get("rsi:4h")),
            "oiusd": fmt_usd(num(e.get("oi:5m"))),
            "range4h": num(e.get("range_level:4h")),
            "range1d": num(e.get("range_level:1D")),
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def cls_pn(v):
    if v is None:
        return "muted"
    return "pos" if v >= 0 else "neg"


def render_html(meta, rows, btc=None, nav="", asset_link=False):
    ts = meta.get("timestamp", "")
    ts_fmt = to_brt(ts, "%d %b %Y · %H:%M") + " BRT"

    # KPIs de topo: melhores valores do scan
    top = rows[0] if rows else {}
    best_exp1d = max((r for r in rows if r["exp1d"] is not None), key=lambda r: r["exp1d"], default=None)
    best_exp4h = max((r for r in rows if r["exp4h"] is not None), key=lambda r: r["exp4h"], default=None)
    n100 = sum(1 for r in rows if r["score"] >= 100)
    top_badge = "◆ DUPLO SCORE 100" if n100 >= 2 else "▲ TOP 10 · AO VIVO"

    # Banner macro do BTC (gate de entrada)
    macro = btc_macro(btc)
    n_ouro = sum(1 for r in rows if r["entry_cls"] == "ouro")
    banner_cls = "ok" if macro["safe"] else "warn"
    macro_banner = (
        f'<div class="macro {banner_cls}">'
        f'<span class="m-state">BTC {macro["state"]}</span>'
        f'<span class="m-rsi">RSI 30m {fmt_num(macro["rsi_30m"],1)} · 1h {fmt_num(macro["rsi_1h"],1)} · 5m {fmt_num(macro["rsi_5m"],1)}</span>'
        f'<span class="m-msg">{"Janela aberta — caçar Setup de Ouro" if macro["safe"] else "Sem reset — evitar entradas, aguardar"}</span>'
        f'<span class="m-ouro">{n_ouro} setup{"s" if n_ouro!=1 else ""} de ouro</span>'
        f'</div>'
    )

    table_rows = []
    for i, r in enumerate(rows, 1):
        chg = r["change"]
        score_w = max(4, min(100, r["score"]))
        # linhas acima do TOP_N começam ocultas (botão "ver mais" revela)
        hidden = " extra" if i > TOP_N else ""
        asset_cell = (f'<a class="asset-link" href="/historico/{r["symbol"]}">{r["asset"]}</a>'
                      if asset_link else r['asset'])
        table_rows.append(f"""
      <tr class="row{hidden}" data-rank="{i}">
        <td class="rank">{i:02d}</td>
        <td class="asset">{asset_cell}</td>
        <td class="price">{r['price']}</td>
        <td class="{cls_pn(chg)}">{fmt_num(chg,2,True)}%</td>
        <td class="score-cell">
          <span class="score-val">{r['score']}</span>
          <span class="score-bar"><i style="width:{score_w}%"></i></span>
        </td>
        <td class="entry e-{r['entry_cls']}" title="Critérios do Setup de Ouro atendidos">{('★ ' if r['entry_cls']=='ouro' else '')}{r['entry_score']}/7</td>
        <td><span class="badge {r['badge_cls']}">{r['badge']}</span></td>
        <td class="muted">{'' if r['trades'] is None else int(r['trades'])}</td>
        <td class="{toi_cls(r['toi'])}" title="trades 1D por $1M de OI">{fmt_compact(r['toi'])}</td>
        <td class="{cls_pn(r['exp1d'])}">{fmt_num(r['exp1d'],2,True)}</td>
        <td class="{cls_pn(r['exp4h'])}">{fmt_num(r['exp4h'],2,True)}</td>
        <td class="{cls_pn(r['exp1h'])}">{fmt_num(r['exp1h'],2,True)}</td>
        <td class="{cls_pn(r['oitrend'])}">{fmt_num(r['oitrend'],2,True)}</td>
        <td class="muted">{fmt_num(r['lsr'],3)}</td>
        <td class="{cls_pn(r['lsrtrend'])}">{fmt_num(r['lsrtrend'],2,True)}</td>
        <td class="rsi">{fmt_num(r['rsi4h'],2)}</td>
        <td class="oi">{r['oiusd']}</td>
      </tr>""")

    # Cards de análise dos top 5 + card de contexto do BTC (6º, sempre)
    cards = []
    for r in rows[:5]:
        narr = build_narrative(r)
        cards.append(f"""
      <div class="card">
        <div class="card-head">
          <span class="card-asset">{r['asset']}</span>
          <span class="{cls_pn(r['change'])} card-chg">{fmt_num(r['change'],2,True)}%</span>
        </div>
        <div class="card-badge"><span class="badge {r['badge_cls']}">{r['badge']}</span><span class="card-score">SCORE {r['score']}</span></div>
        <div class="card-grid">
          <div><label>EXP 4H</label><b class="{cls_pn(r['exp4h'])}">{fmt_num(r['exp4h'],2,True)}</b></div>
          <div><label>EXP 1D</label><b class="{cls_pn(r['exp1d'])}">{fmt_num(r['exp1d'],2,True)}</b></div>
          <div><label>EXP 1H</label><b class="{cls_pn(r['exp1h'])}">{fmt_num(r['exp1h'],2,True)}</b></div>
          <div><label>ROBOS</label><b>{'' if r['trades'] is None else int(r['trades'])}</b></div>
          <div><label>OI TREND</label><b class="{cls_pn(r['oitrend'])}">{fmt_num(r['oitrend'],2,True)}</b></div>
          <div><label>RSI 4H</label><b>{fmt_num(r['rsi4h'],2)}</b></div>
        </div>
        <p class="card-text">{narr}</p>
      </div>""")
    if btc:
        cards.append(render_btc_card(btc))

    return PAGE.format(
        ts=ts_fmt,
        setup=meta.get("setup", ""),
        exchange=meta.get("exchange", ""),
        nsym=meta.get("symbols", len(rows)),
        ntotal=len(rows),
        topn=TOP_N,
        top_badge=top_badge,
        top_asset=top.get("asset", "—"),
        top_score=top.get("score", "—"),
        best1d_a=(best_exp1d or {}).get("asset", "—"),
        best1d_v=fmt_num((best_exp1d or {}).get("exp1d"), 2, True),
        best4h_a=(best_exp4h or {}).get("asset", "—"),
        best4h_v=fmt_num((best_exp4h or {}).get("exp4h"), 2, True),
        nav=nav,
        macro_banner=macro_banner,
        rows="".join(table_rows),
        cards="".join(cards),
    )


def render_btc_card(e):
    r4h = num(e.get("rsi:4h"))
    r1h = num(e.get("rsi:1h"))
    r1d = num(e.get("rsi:1D"))
    chg = num(e.get("price_change:1D")) or 0.0
    oit = num(e.get("oi_trend:5m"))
    rng = num(e.get("range_level:1h"))
    parts = []
    if r4h is not None:
        z = "oversold macro" if r4h <= 30 else ("sobrecompra" if r4h >= 70 else "zona neutra")
        parts.append(f"BTC RSI 4H {r4h:.0f} = {z}.")
    if r1d is not None and r1d <= 30:
        parts.append(f"RSI 1D {r1d:.0f} = oversold histórico persiste.")
    if oit is not None:
        parts.append(("OI trend {0:+.0f} = posições entrando." if oit > 0 else "OI trend {0:+.0f} = fechamento de posições.").format(oit))
    parts.append("Rotação de capital para alts quando BTC lateraliza em oversold.")
    return f"""
      <div class="card card-btc">
        <div class="card-head">
          <span class="card-asset">BTC</span>
          <span class="{cls_pn(chg)} card-chg">{fmt_num(chg,2,True)}%</span>
        </div>
        <div class="card-badge"><span class="badge btc-tag">CONTEXTO MACRO</span><span class="card-score">RANGE {('' if rng is None else int(rng))}</span></div>
        <div class="card-grid">
          <div><label>RSI 4H</label><b class="rsi">{fmt_num(r4h,2)}</b></div>
          <div><label>RSI 1H</label><b class="rsi">{fmt_num(r1h,2)}</b></div>
          <div><label>RSI 1D</label><b class="rsi">{fmt_num(r1d,2)}</b></div>
          <div><label>OI TREND</label><b class="{cls_pn(oit)}">{fmt_num(oit,2,True)}</b></div>
          <div><label>PREÇO</label><b>{fmt_price(num(e.get('price')))}</b></div>
          <div><label>1D %</label><b class="{cls_pn(chg)}">{fmt_num(chg,2,True)}%</b></div>
        </div>
        <p class="card-text">{' '.join(parts)}</p>
      </div>"""


def build_narrative(r):
    parts = []
    e1d, e4h, e1h = r["exp1d"] or 0, r["exp4h"] or 0, r["exp1h"] or 0
    if e1d > 0 and e4h > 0 and e1h > 0:
        parts.append(f"Alinhamento 3TF positivo (1D {e1d:+.0f} / 4H {e4h:+.0f} / 1H {e1h:+.0f}) = força estrutural.")
    elif r["badge"] == "ESTRUTURA CONTRADITÓRIA":
        parts.append(f"Preço {r['change']:+.1f}% mas EXP em conflito (1D {e1d:+.0f} / 4H {e4h:+.0f}) — atividade sem confirmação de tendência.")
    else:
        parts.append(f"EXP 1D {e1d:+.0f} / 4H {e4h:+.0f} / 1H {e1h:+.0f}.")
    if r["trades"]:
        parts.append(f"ROBOS={int(r['trades'])}.")
    if r.get("toi") is not None and r["toi"] >= TOI_ATENCAO:
        parts.append(f"T/OI={fmt_compact(r['toi'])} = robôs desproporcionais ao OI (SM focado).")
    if r["lsrtrend"] is not None and r["lsrtrend"] < -5:
        parts.append(f"LSR trend {r['lsrtrend']:.0f} = shorts capitulando.")
    if r["oitrend"] is not None and r["oitrend"] > 5:
        parts.append(f"OI trend {r['oitrend']:+.0f} = posições entrando.")
    if r["rsi4h"] is not None:
        z = "sobrecompra" if r["rsi4h"] >= 70 else ("sobrevenda" if r["rsi4h"] <= 30 else "neutra")
        parts.append(f"RSI 4H {r['rsi4h']:.0f} ({z}).")
    return " ".join(parts)


PAGE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PHOENIX MEMBROS</title>
<style>
  :root {{
    --bg:#07090c; --panel:#0d1117; --panel2:#11161d; --line:#1c242e;
    --txt:#c9d4df; --muted:#5e6b78; --pos:#27d796; --neg:#ff5470;
    --gold:#e8b84b; --cyan:#46c9e0; --accent:#ff4b3e;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--bg); color:var(--txt);
    font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif; font-size:13px;
  }}
  .wrap {{ max-width:1360px; margin:0 auto; padding:14px; }}
  /* topo */
  .topbar {{ display:flex; align-items:center; gap:16px; padding:10px 14px;
    background:linear-gradient(90deg,#0d1117,#0a0d12); border:1px solid var(--line);
    border-radius:8px; margin-bottom:12px; }}
  .logo {{ width:54px; height:54px; border-radius:8px;
    background:radial-gradient(circle at 30% 30%,#3a2218,#120a07);
    border:1px solid #3a2a1a; flex:0 0 auto; }}
  .brand h1 {{ margin:0; font-size:22px; letter-spacing:3px; font-weight:800; }}
  .brand h1 b {{ color:var(--accent); }}
  .brand small {{ color:var(--muted); letter-spacing:2px; font-size:10px; }}
  .topkpis {{ margin-left:auto; text-align:right; font-size:11px; color:var(--muted);
    line-height:1.6; }}
  .topkpis b {{ color:var(--txt); }}
  .clock {{ border:1px solid var(--line); border-radius:6px; padding:8px 12px;
    text-align:center; }}
  .clock .live {{ color:var(--pos); font-size:10px; letter-spacing:1px; }}
  .clock .d {{ font-size:13px; color:var(--txt); }}
  /* kpi cards */
  .kpis {{ display:grid; grid-template-columns:repeat(6,1fr); gap:10px; margin-bottom:14px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:8px;
    padding:10px 12px; }}
  .kpi .t {{ color:var(--muted); font-size:9px; letter-spacing:1px; text-transform:uppercase; }}
  .kpi .v {{ font-size:20px; font-weight:700; margin:4px 0 2px; }}
  .kpi .s {{ font-size:10px; color:var(--muted); }}
  /* tabela */
  .table-wrap {{ background:var(--panel); border:1px solid var(--line); border-radius:8px;
    overflow:hidden; margin-bottom:16px; }}
  table {{ width:100%; border-collapse:collapse; }}
  thead th {{ font-size:9px; letter-spacing:.5px; color:var(--muted); text-transform:uppercase;
    text-align:right; padding:10px 8px; border-bottom:1px solid var(--line); font-weight:600; }}
  thead th.l {{ text-align:left; }}
  tbody td {{ padding:9px 8px; text-align:right; border-bottom:1px solid #131922;
    font-variant-numeric:tabular-nums; white-space:nowrap; }}
  tbody tr:hover {{ background:#0f151d; }}
  .rank {{ color:var(--muted); text-align:left; font-weight:700; }}
  .asset {{ text-align:left; font-weight:700; color:#fff; letter-spacing:.5px; }}
  .price {{ color:var(--txt); }}
  .pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }} .muted {{ color:var(--muted); }}
  .rsi {{ color:var(--gold); }} .oi {{ color:var(--cyan); }}
  .toi-hi {{ color:#c77dff; font-weight:700; }}  /* T/OI forte = SM focado */
  .toi-mid {{ color:#9d8bd8; }}                   /* T/OI em atenção */
  .entry {{ font-weight:700; }}
  .e-ouro {{ color:#27d796; }}      /* Setup de Ouro */
  .e-parcial {{ color:var(--gold); }} /* parcial */
  .e-none {{ color:var(--muted); font-weight:400; }}
  .score-cell {{ display:flex; align-items:center; gap:8px; justify-content:flex-end; }}
  .score-val {{ font-weight:700; color:#fff; min-width:24px; }}
  .score-bar {{ width:70px; height:5px; background:#1a222c; border-radius:3px; overflow:hidden; }}
  .score-bar i {{ display:block; height:100%; background:linear-gradient(90deg,var(--accent),var(--gold)); }}
  .badge {{ font-size:9px; letter-spacing:.5px; padding:3px 7px; border-radius:4px;
    font-weight:700; text-transform:uppercase; white-space:nowrap; }}
  .robos-on  {{ background:rgba(39,215,150,.12); color:var(--pos); border:1px solid rgba(39,215,150,.4); }}
  .robos-act {{ background:rgba(70,201,224,.12); color:var(--cyan); border:1px solid rgba(70,201,224,.4); }}
  .forca     {{ background:rgba(70,201,224,.10); color:#7fd8ea; border:1px solid rgba(70,201,224,.3); }}
  .acum      {{ background:rgba(232,184,75,.12); color:var(--gold); border:1px solid rgba(232,184,75,.4); }}
  .contra    {{ background:rgba(255,84,112,.12); color:var(--neg); border:1px solid rgba(255,84,112,.45); }}
  .silent    {{ background:rgba(199,125,255,.12); color:#c77dff; border:1px solid rgba(199,125,255,.45); }}
  .neutro    {{ background:#161d26; color:var(--muted); border:1px solid var(--line); }}
  .btc-tag   {{ background:rgba(232,184,75,.12); color:var(--gold); border:1px solid rgba(232,184,75,.35); }}
  /* linhas extras (acima do TOP_N) ocultas até "ver mais" */
  .row.extra {{ display:none; }}
  .show-all .row.extra {{ display:table-row; }}
  /* barra de controle ver mais */
  .controls {{ display:flex; align-items:center; gap:8px; padding:8px 10px;
    border-top:1px solid var(--line); background:#0a0e13; }}
  .controls .info {{ color:var(--muted); font-size:10px; margin-right:auto; letter-spacing:.5px; }}
  .controls button {{ background:#11161d; color:var(--txt); border:1px solid var(--line);
    border-radius:5px; padding:5px 12px; font-size:11px; cursor:pointer; letter-spacing:.5px;
    font-weight:600; transition:.15s; }}
  .controls button:hover {{ border-color:var(--accent); color:#fff; }}
  .controls button.active {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
  /* cards */
  .sec-title {{ font-size:10px; letter-spacing:2px; color:var(--muted); text-transform:uppercase;
    margin:0 0 10px; padding-left:4px; border-left:2px solid var(--accent); }}
  .cards {{ display:grid; grid-template-columns:repeat(6,1fr); gap:10px; }}
  .card {{ background:var(--panel2); border:1px solid var(--line); border-radius:8px; padding:12px; }}
  .card-btc {{ border-color:rgba(232,184,75,.35); }}
  .card-head {{ display:flex; justify-content:space-between; align-items:baseline; }}
  .card-asset {{ font-size:18px; font-weight:800; color:#fff; }}
  .card-chg {{ font-size:13px; font-weight:700; }}
  .card-badge {{ display:flex; justify-content:space-between; align-items:center; margin:8px 0 10px; }}
  .card-score {{ font-size:10px; color:var(--muted); font-weight:700; }}
  .card-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px 6px; margin-bottom:10px; }}
  .card-grid div {{ background:#0b1016; border:1px solid #161d26; border-radius:5px; padding:6px; }}
  .card-grid label {{ display:block; font-size:8px; color:var(--muted); letter-spacing:.5px; }}
  .card-grid b {{ font-size:13px; }}
  .card-text {{ font-size:10.5px; color:#8b97a4; line-height:1.55; margin:0; }}
  .footbar {{ display:flex; justify-content:space-between; align-items:center; gap:12px;
    border-top:1px solid var(--line); margin-top:18px; padding:12px 4px; flex-wrap:wrap; }}
  .footbar span {{ color:var(--muted); font-size:10px; letter-spacing:.5px; }}
  .footbar .disc {{ color:#7a8794; text-transform:uppercase; }}
  /* nav / toolbar */
  .nav {{ display:flex; align-items:center; gap:8px; margin-bottom:12px; flex-wrap:wrap; }}
  .nav a, .nav button.navbtn {{ background:#11161d; color:var(--txt); border:1px solid var(--line);
    border-radius:6px; padding:7px 14px; font-size:11px; cursor:pointer; letter-spacing:.5px;
    font-weight:600; text-decoration:none; transition:.15s; }}
  .nav a:hover, .nav button.navbtn:hover {{ border-color:var(--accent); color:#fff; }}
  .nav .primary {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
  .nav select {{ background:#11161d; color:var(--txt); border:1px solid var(--line);
    border-radius:6px; padding:7px 10px; font-size:11px; }}
  .nav .spacer {{ margin-left:auto; }}
  .asset-link {{ color:#fff; text-decoration:none; border-bottom:1px dotted #3a4654; }}
  .asset-link:hover {{ color:var(--accent); border-color:var(--accent); }}
  .flash {{ background:rgba(255,75,62,.12); border:1px solid rgba(255,75,62,.4); color:#ffb4ac;
    padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:10px; }}
  /* banner macro BTC */
  .macro {{ display:flex; align-items:center; gap:14px; padding:10px 14px; border-radius:8px;
    margin-bottom:12px; font-size:12px; flex-wrap:wrap; }}
  .macro.ok {{ background:rgba(39,215,150,.10); border:1px solid rgba(39,215,150,.4); }}
  .macro.warn {{ background:rgba(232,184,75,.10); border:1px solid rgba(232,184,75,.4); }}
  .macro .m-state {{ font-weight:800; letter-spacing:1px; }}
  .macro.ok .m-state {{ color:var(--pos); }}
  .macro.warn .m-state {{ color:var(--gold); }}
  .macro .m-rsi {{ color:var(--muted); }}
  .macro .m-msg {{ color:var(--txt); }}
  .macro .m-ouro {{ margin-left:auto; color:var(--pos); font-weight:700; }}
  /* modal import */
  .modal {{ position:fixed; inset:0; background:rgba(0,0,0,.7); display:none;
    align-items:center; justify-content:center; z-index:50; }}
  .modal.open {{ display:flex; }}
  .modal-box {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
    width:min(640px,92vw); padding:20px; }}
  .modal-box h3 {{ margin:0 0 4px; font-size:15px; color:#fff; letter-spacing:1px; }}
  .modal-box p {{ margin:0 0 12px; font-size:11px; color:var(--muted); }}
  .modal-box textarea {{ width:100%; height:180px; background:#0a0e13; color:var(--txt);
    border:1px solid var(--line); border-radius:6px; padding:10px; font-family:monospace;
    font-size:11px; resize:vertical; }}
  .modal-box input[type=file] {{ font-size:11px; color:var(--muted); margin:10px 0; }}
  .modal-actions {{ display:flex; gap:8px; justify-content:flex-end; margin-top:12px; }}
  .modal-actions button {{ padding:8px 16px; border-radius:6px; font-size:12px; cursor:pointer;
    border:1px solid var(--line); background:#11161d; color:var(--txt); font-weight:600; }}
  .modal-actions .go {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
  @media(max-width:1300px) {{ .cards{{grid-template-columns:repeat(3,1fr)}} }}
  @media(max-width:1100px) {{ .kpis{{grid-template-columns:repeat(3,1fr)}} .cards{{grid-template-columns:repeat(2,1fr)}} .table-wrap{{overflow-x:auto}} }}
</style>
</head>
<body>
<div class="wrap">

  <div class="topbar">
    <div class="logo"></div>
    <div class="brand">
      <h1>PHOENIX <b>MEMBROS</b></h1>
      <small>METODOLOGIA ENCRYPTOS · {exchange} · SETUP {setup} · {nsym} ATIVOS</small>
    </div>
    <div class="topkpis">
      TOP SCORE <b>{top_asset} ({top_score})</b><br>
      MAIOR EXP 1D <b>{best1d_a} {best1d_v}</b> · MAIOR EXP 4H <b>{best4h_a} {best4h_v}</b>
    </div>
    <div class="clock">
      <div class="live">{top_badge}</div>
      <div class="d">{ts}</div>
    </div>
  </div>

  {nav}

  {macro_banner}

  <div class="kpis">
    <div class="kpi"><div class="t">Top Score</div><div class="v">{top_asset}</div><div class="s">score {top_score}</div></div>
    <div class="kpi"><div class="t">Maior EXP 1D</div><div class="v pos">{best1d_v}</div><div class="s">{best1d_a}</div></div>
    <div class="kpi"><div class="t">Maior EXP 4H</div><div class="v pos">{best4h_v}</div><div class="s">{best4h_a}</div></div>
    <div class="kpi"><div class="t">Setup</div><div class="v">{setup}</div><div class="s">{exchange}</div></div>
    <div class="kpi"><div class="t">Ativos Escaneados</div><div class="v">{nsym}</div><div class="s">binance usdm</div></div>
    <div class="kpi"><div class="t">Atualizado</div><div class="v" style="font-size:13px">{ts}</div><div class="s">horário de Brasília</div></div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th class="l">#</th><th class="l">ATIVO</th><th>PREÇO</th><th>ID %</th>
          <th>SCORE</th><th>ENTRADA</th><th class="l">SETUP</th><th>TRADES/M</th><th>T/OI</th>
          <th>EXP 1D</th><th>EXP 4H</th><th>EXP 1H</th><th>OI TREND</th>
          <th>LSR</th><th>LSR TREND</th><th>RSI 4H</th><th>OI USD</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>
    <div class="controls">
      <span class="info" id="info">Exibindo TOP {topn} de {ntotal} ativos</span>
      <button data-n="10" class="active" onclick="setView(this,10)">TOP 10</button>
      <button data-n="25" onclick="setView(this,25)">TOP 25</button>
      <button data-n="50" onclick="setView(this,50)">TOP 50</button>
      <button data-n="0" onclick="setView(this,0)">TODOS ({ntotal})</button>
    </div>
  </div>

  <div class="sec-title">Análise Estrutural · Top 5 + BTC</div>
  <div class="cards">{cards}</div>

  <div class="footbar">
    <span>PHOENIX MEMBROS · METODOLOGIA ENCRYPTOS · {ts}</span>
    <span class="disc">Painel educativo — não constitui recomendação de investimento · opere com gestão de risco</span>
    <span>PHOENIX PRO © 2026</span>
  </div>

</div>
<script>
function setView(btn, n) {{
  document.querySelectorAll('.controls button').forEach(function(b){{ b.classList.remove('active'); }});
  btn.classList.add('active');
  var rows = document.querySelectorAll('tbody tr.row');
  var total = rows.length;
  var limit = n === 0 ? total : n;
  rows.forEach(function(tr){{
    var rk = parseInt(tr.getAttribute('data-rank'), 10);
    tr.classList.toggle('extra', rk > limit);
  }});
  var info = document.getElementById('info');
  info.textContent = n === 0 ? ('Exibindo TODOS os ' + total + ' ativos') : ('Exibindo TOP ' + n + ' de ' + total + ' ativos');
}}
</script>
</body>
</html>"""


def main():
    args = sys.argv[1:]
    if args:
        src = args[0]
    else:
        cands = sorted(glob.glob("eassets-panel-*.json"))
        if not cands:
            print("Nenhum eassets-panel-*.json encontrado.")
            return 1
        src = cands[-1]
    out = args[1] if len(args) > 1 else "painel_phoenix.html"

    with open(src, encoding="utf-8") as f:
        doc = json.load(f)

    rows = build_rows(doc["data"])
    btc = doc["data"].get("BTCUSDT")
    html = render_html(doc, rows, btc)

    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"OK: {len(rows)} ativos -> {out}  (fonte: {src})")
    print(f"Top 5: " + ", ".join(f"{r['asset']}({r['score']})" for r in rows[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
