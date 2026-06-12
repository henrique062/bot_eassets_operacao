#!/usr/bin/env python3
"""
BANCADA PHOENIX — Motor de análise
Módulo importável: processa dadosmoedas e retorna resultados + HTML.
"""

import json
from datetime import datetime, timezone

ENCRYPTOS_BLACKLIST = {
    "ADA", "XRP", "DOGE", "XLM", "LUNC",
}
ENCRYPTOS_BLACKLIST_PREFIXES = ("1000",)
ENCRYPTOS_MIN_OI = 10_000_000
ENCRYPTOS_MIN_TRADES_1D = 150_000
ENCRYPTOS_ASTRONOMICAL_OI = 100_000_000
ENCRYPTOS_ASTRONOMICAL_TRADES_1D = 1_000_000

# ── HELPERS ───────────────────────────────────────────────────────────────────

def g(d, key, default=None):
    v = d.get(key, default)
    return v if v is not None else default

def fmt_price(price):
    if price is None:
        return "—"
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 100:
        return f"{price:.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    elif price >= 0.001:
        return f"{price:.6f}"
    else:
        return f"{price:.8f}"

def fmt_pct(v, decimals=4):
    if v is None:
        return "—"
    return f"{v:.{decimals}f}%"

def fmt_compact_int(v):
    if v is None:
        return "-"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v / 1_000:.0f}k"
    return str(int(v))

def fmt_money_usd(v):
    if v is None:
        return "$0"
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    return f"${v / 1_000_000:.1f}M"

def sym_to_base(symbol):
    if symbol.endswith("USDT"):
        return symbol[:-4]
    return symbol

def coin_trend_label(price_change):
    if price_change is None:
        return "ESTÁVEL"
    if price_change > 3:
        return "CRESCENTE"
    elif price_change < -3:
        return "CAINDO"
    return "ESTÁVEL"

# ── SCORING ───────────────────────────────────────────────────────────────────

def calc_tendencia(coin, btc):
    pts = 0
    itens = []

    exp_1d  = g(coin, "exp_btc:1D")
    exp_4h  = g(coin, "exp_btc:4h", 0) or 0
    oi_tr   = g(coin, "oi_trend:5m", 0) or 0
    lsr_tr  = g(coin, "lsr_trend:5m", 0) or 0
    tm_1d   = g(coin, "trades_minute:1D", 0) or 0

    if exp_1d is not None:
        if exp_1d > 5:
            pts += 2
            itens.append("🟢 EXP diário acelerando")
        elif exp_1d > 0:
            pts += 1
            itens.append("🟡 EXP diário positivo")
        else:
            itens.append("🔴 EXP diário negativo")

    if oi_tr > 5:
        pts += 2
        itens.append(f"🟢 OI crescendo +{oi_tr:.1f}% (baleias entrando)")
    elif oi_tr > 0:
        pts += 1
        itens.append("🟡 OI levemente crescendo")
    else:
        itens.append("🔴 OI caindo")

    if tm_1d > 100:
        pts += 1
        itens.append("🟢 Volume diário crescendo com EXP (confirmação)")

    if lsr_tr < -8 and oi_tr > 3:
        pts += 2
        itens.append("🐊 LSR caindo + OI subindo (squeeze acumulando)")
    elif lsr_tr < -3 and oi_tr > 0:
        pts += 1
        itens.append("🟡 LSR caindo levemente")

    if exp_4h > 10:
        pts += 2
        itens.append("🟢 EXP 4H subindo (4H confirma o diário)")
    elif exp_4h > 0:
        pts += 1
        itens.append("🟡 EXP 4H positivo")
    elif exp_4h < 0:
        itens.append("🔴 EXP 4H caindo (fraqueza no intermediário)")

    return min(pts, 10), itens


def calc_rsi(coin):
    rsi = g(coin, "rsi:15m") or g(coin, "rsi:1m", 50) or 50
    if 50 <= rsi <= 70:
        return 3, "🟢 ZONA PERFEITA pra entrar", rsi
    elif 70 < rsi <= 80:
        return 1, "🟡 Subindo, ainda dá", rsi
    elif 40 <= rsi < 50:
        return 1, "🟡 RSI neutro, levemente fraco", rsi
    elif rsi < 40:
        return 0, "😴 Fraca, sem força", rsi
    else:
        return -1, "🔴 SOBRECOMPRADA — risco de reversão", rsi


def calc_exp(coin):
    exp = g(coin, "exp_btc:15m")
    if exp is None:
        return 0, "⚪ EXP não disponível", 0
    if exp > 15:
        return 3, "🚀 Subindo mais que o BTC (força própria)", exp
    elif exp > 5:
        return 2, "✅ Combustível ideal, espaço pra subir", exp
    elif exp > 0:
        return 1, "🟡 Combustível fraco", exp
    else:
        return 0, "🔴 Sem combustível (EXP negativo)", exp


def calc_acum(coin):
    rl_1d  = g(coin, "range_level:1D",  0) or 0
    rl_4h  = g(coin, "range_level:4h",  0) or 0
    rl_1h  = g(coin, "range_level:1h",  0) or 0
    rl_30m = g(coin, "range_level:30m", 0) or 0
    rl_15m = g(coin, "range_level:15m", 0) or 0

    pts = 0

    if rl_1d >= 4:
        pts += 3
        msg_daily = f"💎 Diário: ACUMULAÇÃO FORTE (1D = {rl_1d})"
    elif rl_1d >= 2:
        pts += 1
        msg_daily = f"🟡 Diário: Acumulação parcial (1D = {rl_1d})"
    else:
        msg_daily = "📊 Diário: Sem acumulação"

    strong = sum(1 for r in [rl_30m, rl_15m, rl_1h, rl_4h] if r >= 4)
    med    = sum(1 for r in [rl_30m, rl_15m, rl_1h, rl_4h] if r >= 2)

    if strong >= 3:
        pts += 3
        msg_intra = f"💎💎 ACUMULAÇÃO CONFIRMADA EM TODOS TIMEFRAMES (30m={rl_30m}, 15m={rl_15m}, 1h={rl_1h}, 4h={rl_4h})"
    elif strong >= 2:
        pts += 2
        msg_intra = f"⚡ ACUMULAÇÃO INTRA-DAY (pre-setup) (30m={rl_30m}, 15m={rl_15m}, 1h={rl_1h}, 4h={rl_4h})"
    elif med >= 2:
        pts += 1
        msg_intra = f"⚡ ACUMULAÇÃO INTRA-DAY (pre-setup) (30m={rl_30m}, 15m={rl_15m}, 1h={rl_1h}, 4h={rl_4h})"
    else:
        msg_intra = f"📊 Intra-day: fraco (30m={rl_30m}, 15m={rl_15m}, 1h={rl_1h}, 4h={rl_4h})"

    return pts, msg_daily, msg_intra


def calc_timing(coin):
    tm_1m = g(coin, "trades_minute:1m", 0) or 0
    tm_5m = g(coin, "trades_minute:5m", 0) or 0
    if tm_5m > 0 and tm_1m > tm_5m * 1.15 and tm_1m > 30:
        return 2, "🟢 HORA CERTA - move tá começando"
    elif tm_1m > 10:
        return 0, "⚪ Timing neutro"
    return 0, "⚪ Timing neutro"


def calc_tf_scores(coin):
    exp_1h = g(coin, "exp_btc:1h", 0) or 0
    rsi_1h = g(coin, "rsi:1h",     50) or 50
    exp_4h = g(coin, "exp_btc:4h", 0) or 0
    rsi_4h = g(coin, "rsi:4h",     50) or 50

    if exp_1h > 10 and 50 <= rsi_1h <= 80:
        s1h = 2
    elif exp_1h > 0 and rsi_1h > 50:
        s1h = 1
    else:
        s1h = 0

    if exp_4h > 20 and 50 <= rsi_4h <= 80:
        s4h = 2
    elif rsi_4h > 80:
        s4h = 1
    elif exp_4h > 0 and rsi_4h > 50:
        s4h = 1
    else:
        s4h = 0

    dir_1h = "↑" if rsi_1h > 50 else "↓"
    dir_4h = "↑" if rsi_4h > 50 else "↓"
    em_1h = "✅" if s1h >= 2 else ("🟢" if s1h == 1 else "⚪")
    em_4h = "✅" if s4h >= 2 else ("🟢" if s4h == 1 else "⚪")
    msg_1h = f"{em_1h} 1H: EXP {exp_1h} | RSI {rsi_1h:.0f} {dir_1h} (score 1h: +{s1h})"
    msg_4h = f"{em_4h} 4H: EXP {exp_4h} | RSI {rsi_4h:.0f} {dir_4h} (score 4h: +{s4h})"

    return s1h, s4h, msg_1h, msg_4h


def calc_fr(coin):
    fr = g(coin, "fr", 0) or 0
    fr_pct = fr * 100
    if fr_pct > 0.05:
        return -1, f"🟡 FR elevado — cautela (FR {fr_pct:.4f}%)"
    elif fr_pct < -0.05:
        return -1, f"⚠️ FR negativo — shorts dominando (FR {fr_pct:.4f}%)"
    else:
        return 0, f"⚪ FR neutro (FR {fr_pct:.4f}%)"


def calc_btc_ind(coin, btc):
    pc  = g(coin, "price_change:1D", 0) or 0
    bpc = g(btc,  "price_change:1D", 0) or 0
    if pc > bpc + 1:
        return 2, "💪 Sobe sozinha, não depende do BTC"
    elif pc > bpc - 1:
        return 1, "⚪ Movimento próximo ao BTC"
    else:
        return 0, "🔴 Fraca vs BTC"


def calc_jacare(coin):
    oi_tr  = g(coin, "oi_trend:5m", 0) or 0
    lsr_tr = g(coin, "lsr_trend:5m", 0) or 0
    oi     = g(coin, "oi:5m", 0) or 0
    lsr    = g(coin, "lsr:5m", 1) or 1
    oi_m   = oi / 1_000_000

    if oi_tr > 3 and lsr_tr < -8:
        return 2, True, f"🐊 Jacaré CONFIRMADO (OI +{oi_tr:.1f}% em 30m, +{oi_tr*0.9:.1f}% em 1h) | 🐊 LSR tendência caindo + OI subindo — squeeze se formando."
    elif oi_tr > 2 and lsr_tr < -3:
        return 1, False, f"🐊 Jacaré PARCIAL — só 5m. OI 1h: {oi_tr*0.7:.1f}%. OI: ${oi_m:.1f}M (🟡 liquidez moderada). Verificar CoinGlass."
    else:
        return 0, False, "🐊 Jacaré fechado — sem squeeze no momento."


def calc_alignment(coin):
    rsi_1m = g(coin, "rsi:1m",  50) or 50
    rsi_1h = g(coin, "rsi:1h",  50) or 50
    rsi_4h = g(coin, "rsi:4h",  50) or 50
    exp_1m = g(coin, "exp_btc:1m", 0) or 0
    exp_1h = g(coin, "exp_btc:1h", 0) or 0
    exp_4h = g(coin, "exp_btc:4h", 0) or 0

    aligned = sum([
        rsi_1m > 50 and exp_1m > 0,
        rsi_1h > 50 and exp_1h > 0,
        rsi_4h > 50 and exp_4h > 0,
    ])

    if aligned >= 3:
        return 2, "✅ Os 3 tempos confirmam (curto, médio, longo)"
    elif aligned >= 2:
        return 1, "⏳ Tempos não alinhados ainda"
    return 0, "⏳ Tempos não alinhados ainda"


def score_coin(symbol, coin, btc):
    pts_tend, itens_tend = calc_tendencia(coin, btc)
    pts_rsi,  msg_rsi,  rsi_val = calc_rsi(coin)
    pts_exp,  msg_exp,  exp_val = calc_exp(coin)
    pts_acum, msg_daily, msg_intra = calc_acum(coin)
    pts_timing, msg_timing = calc_timing(coin)
    s1h, s4h, msg_1h, msg_4h = calc_tf_scores(coin)
    pts_fr,  msg_fr  = calc_fr(coin)
    pts_btc, msg_btc = calc_btc_ind(coin, btc)
    pts_jac, jacare_ok, msg_jac = calc_jacare(coin)
    pts_align, msg_align = calc_alignment(coin)

    total = (pts_tend + pts_rsi + pts_exp + pts_acum
             + pts_timing + s1h + s4h + pts_fr
             + pts_btc + pts_jac + pts_align)
    total = max(0, min(40, total))

    fr_pct = (g(coin, "fr", 0) or 0) * 100
    oi     = g(coin, "oi:5m", 0) or 0
    oi_tr  = g(coin, "oi_trend:5m", 0) or 0
    lsr    = g(coin, "lsr:5m", 1) or 1
    lsr_tr = g(coin, "lsr_trend:5m", 0) or 0
    pc     = g(coin, "price_change:1D", 0) or 0

    return {
        "symbol":       symbol,
        "base":         sym_to_base(symbol),
        "price":        g(coin, "price", 0) or 0,
        "price_change": pc,
        "score":        total,
        "fr_pct":       fr_pct,
        "rsi":          rsi_val,
        "exp_15m":      exp_val,
        "oi":           oi,
        "oi_trend":     oi_tr,
        "lsr":          lsr,
        "lsr_trend":    lsr_tr,
        "trades_1d":    g(coin, "trades:1D", 0) or 0,
        "jacare_ok":    jacare_ok,
        "tend_pts":     pts_tend,
        "tend_itens":   itens_tend,
        "msg_rsi":      msg_rsi,
        "msg_exp":      msg_exp,
        "msg_daily":    msg_daily,
        "msg_intra":    msg_intra,
        "msg_timing":   msg_timing,
        "msg_1h":       msg_1h,
        "msg_4h":       msg_4h,
        "msg_fr":       msg_fr,
        "msg_btc":      msg_btc,
        "msg_jac":      msg_jac,
        "msg_align":    msg_align,
        "exp_1m":  g(coin, "exp_btc:1m", 0) or 0,
        "exp_1h":  g(coin, "exp_btc:1h", 0) or 0,
        "exp_4h":  g(coin, "exp_btc:4h", 0) or 0,
        "rsi_1m":  g(coin, "rsi:1m",  50) or 50,
        "rsi_1h":  g(coin, "rsi:1h",  50) or 50,
        "rsi_4h":  g(coin, "rsi:4h",  50) or 50,
        "tm_1m":   g(coin, "trades_minute:1m", 0) or 0,
        "tm_1d":   g(coin, "trades_minute:1D", 0) or 0,
    }

# ── MACRO ─────────────────────────────────────────────────────────────────────

def calc_macro(btc, all_coins):
    rsi_btc = g(btc, "rsi:1D", 50) or 50
    frs = [g(c, "fr", 0) or 0 for c in all_coins.values() if g(c, "fr") is not None]
    avg_fr = (sum(frs) / len(frs) * 100) if frs else 0

    if rsi_btc < 45:
        return {"status": "AMBIENTE HOSTIL", "color": "#D92D20", "bg": "rgba(217,45,32,0.08)",
                "border": "rgba(217,45,32,0.25)", "icon": "🔴", "hostile": True,
                "msg": "Cuidado: BTC fraco ou Dominância subindo. Risco de queda nas Altcoins.",
                "rsi_btc": rsi_btc, "avg_fr": avg_fr}
    elif rsi_btc < 55:
        return {"status": "MERCADO NEUTRO", "color": "#DC6803", "bg": "rgba(220,104,3,0.08)",
                "border": "rgba(220,104,3,0.25)", "icon": "🟡", "hostile": False,
                "msg": "Mercado lateral. Operar com cautela e stops bem posicionados.",
                "rsi_btc": rsi_btc, "avg_fr": avg_fr}
    else:
        return {"status": "AMBIENTE FAVORÁVEL", "color": "#039855", "bg": "rgba(3,152,85,0.08)",
                "border": "rgba(3,152,85,0.25)", "icon": "🟢", "hostile": False,
                "msg": "BTC forte. Boa janela para entradas em altcoins selecionadas.",
                "rsi_btc": rsi_btc, "avg_fr": avg_fr}

# ── MODO FÊNIX ────────────────────────────────────────────────────────────────

def check_fenix(symbol, coin, macro):
    tm_1d  = g(coin, "trades:1D", 0) or 0
    if tm_1d < 30_000:
        return None

    exp_1m = g(coin, "exp_btc:1m", 0) or 0
    tm_1m  = g(coin, "trades_minute:1m", 0) or 0
    tm_5m  = g(coin, "trades_minute:5m", 0) or 0
    rsi_1m = g(coin, "rsi:1m", 50) or 50
    rl_15m = g(coin, "range_level:15m", 0) or 0
    oi_tr  = g(coin, "oi_trend:5m", 0) or 0
    lsr_tr = g(coin, "lsr_trend:5m", 0) or 0

    c1 = exp_1m > 3
    c2 = (tm_5m > 0 and tm_1m >= tm_5m * 0.8) or tm_1m > 50
    c3 = 50 <= rsi_1m <= 70
    c4 = rl_15m >= 3

    score = sum([c1, c2, c3, c4])
    if score < 2:
        return None

    jacare = oi_tr > 2 and lsr_tr < -5

    return {
        "symbol":   sym_to_base(symbol),
        "pair":     symbol,
        "price":    g(coin, "price", 0) or 0,
        "score":    score,
        "c1": c1, "c1_val": exp_1m,
        "c2": c2, "c2_val": tm_1m,
        "c3": c3, "c3_val": rsi_1m,
        "c4": c4, "c4_val": rl_15m,
        "tm_1d":    tm_1d,
        "jacare":   jacare,
        "blocked":  macro["hostile"],
    }

# ── MODO FÊNIX V2 ────────────────────────────────────────────────────────────

def check_fenix_v2(symbol, coin, macro, btc):
    # ── Pré-filtros: liquidez mínima ──
    tm_1d  = g(coin, "trades:1D", 0) or 0
    oi_val = g(coin, "oi:5m", 0) or 0
    if tm_1d < 300_000 or oi_val < 5_000_000:
        return None

    # ── Leitura de campos ──
    exp_15m    = g(coin, "exp_btc:15m", 0) or 0   # principal — maior peso
    exp_5m     = g(coin, "exp_btc:5m",  0) or 0   # secundário (ignição curta)
    exp_1m     = g(coin, "exp_btc:1m",  0) or 0   # confirmação de ignição
    tm_5m      = g(coin, "trades_minute:5m", 0) or 0
    tm_1m      = g(coin, "trades_minute:1m", 0) or 0
    rsi_15m    = g(coin, "rsi:15m", 50) or 50
    rsi_1m     = g(coin, "rsi:1m",  50) or 50
    rsi_btc_1m = g(btc,  "rsi:1m",  50) or 50
    rl_30m     = g(coin, "range_level:30m", 0) or 0
    rl_1h      = g(coin, "range_level:1h",  0) or 0
    oi_tr      = g(coin, "oi_trend:5m", 0) or 0
    lsr_tr     = g(coin, "lsr_trend:5m", 0) or 0
    lsr_val    = g(coin, "lsr:5m", 1) or 1

    # C1 — EXP: 15m é o principal; 5m e 1m confirmam ignição
    c1 = exp_15m >= 2 and exp_1m >= 1
    c1_boost = exp_5m >= 2  # 5m também acelerando = sinal extra (não muda score)

    # C2 — Volume institucional (5m ou combinação 1m forte)
    c2 = tm_5m >= 150 or (tm_1m >= 50 and tm_5m >= 50)

    # C3 — RSI 15m ganhando tração ou Alt descolando do BTC
    c3 = rsi_15m >= 55 or rsi_1m > rsi_btc_1m

    # C4 — Acumulação estrutural (30m + 1h, nível 3 mínimo)
    c4 = rl_30m >= 3 and rl_1h >= 3

    score = sum([c1, c2, c3, c4])
    if score < 3:
        return None

    jacare       = oi_tr >= 1 and lsr_tr <= -1
    squeeze_real = jacare and lsr_val <= 1.0

    rsi_btc_1h = g(btc, "rsi:1h", 50) or 50
    reset_opp  = rsi_btc_1h < 35

    return {
        "symbol":       sym_to_base(symbol),
        "pair":         symbol,
        "price":        g(coin, "price", 0) or 0,
        "score":        score,
        "c1": c1, "c1_val": exp_15m, "c1_5m": exp_5m, "c1_1m": exp_1m, "c1_boost": c1_boost,
        "c2": c2, "c2_val": tm_5m, "c2_1m": tm_1m,
        "c3": c3, "c3_val": rsi_15m, "c3_alt": rsi_1m > rsi_btc_1m,
        "c4": c4, "c4_30m": rl_30m, "c4_1h": rl_1h,
        "oi_val":       oi_val,
        "oi_tr":        oi_tr,
        "lsr_val":      lsr_val,
        "lsr_tr":       lsr_tr,
        "jacare":       jacare,
        "squeeze_real": squeeze_real,
        "reset_opp":    reset_opp,
        "tm_1d":        tm_1d,
        "blocked":      macro["hostile"],
    }


def html_fenix_v2_card(f):
    blocked = f["blocked"]
    opacity_style = 'style="opacity:0.45;filter:grayscale(60%);border:1px solid rgba(217,45,32,.4);"' if blocked else ""

    if blocked:
        verdict_style = 'style="background:rgba(217,45,32,.12);color:#D92D20;"'
        verdict_text  = "🔴 BLOQUEADO — MACRO HOSTIL"
    elif f["score"] == 4 and f["jacare"]:
        verdict_style = 'style="background:rgba(21,112,239,.15);color:#1570EF;"'
        verdict_text  = "🐊✅ FÓRMULA 1 — ENTRAR AGORA"
    elif f["score"] == 4:
        verdict_style = 'style="background:rgba(3,152,85,.12);color:#039855;"'
        verdict_text  = "✅ ENTRAR AGORA"
    elif f["score"] == 3:
        verdict_style = 'style="background:rgba(3,152,85,.08);color:#039855;"'
        verdict_text  = "🟢 ENTRAR"
    else:
        verdict_style = 'style="background:rgba(220,104,3,.12);color:#DC6803;"'
        verdict_text  = "⚠️ AGUARDAR"

    def ck(ok): return f'<span class="ck" style="color:{("#1570EF" if ok else "#D92D20")};">{"✅" if ok else "❌"}</span>'

    boost_html = ' <span style="color:#ffd700;font-size:10px;">⚡5m</span>' if f.get("c1_boost") else ""

    jacare_html = ""
    if f["squeeze_real"]:
        jacare_html = '<div class="fv2-badge" style="background:rgba(21,112,239,.12);color:#1570EF;border-color:rgba(21,112,239,.3);">🐊 Squeeze Real — LSR ≤ 1.0</div>'
    elif f["jacare"]:
        jacare_html = '<div class="fv2-badge">🐊 Jacaré V2 — OI↑ LSR↓</div>'

    reset_html = '<div class="fv2-badge" style="background:rgba(163,113,247,.15);color:#a371f7;border-color:#a371f760;">⚡ BTC em Reset — oportunidade</div>' if f["reset_opp"] else ""

    oi_m     = f["oi_val"] / 1_000_000
    c1_label = f'EXP15m {f["c1_val"]:.1f}/1m {f["c1_1m"]:.1f}'
    c2_label = f'Tr5m {f["c2_val"]}/1m {f["c2_1m"]}'
    c3_label = f'RSI15m {f["c3_val"]:.0f}{"↑BTC" if f["c3_alt"] else ""}'
    tm_label = f'{f["tm_1d"]/1000:.0f}k' if f["tm_1d"] < 1_000_000 else f'{f["tm_1d"]/1_000_000:.2f}M'

    return f"""<div class="fv2-card" {opacity_style}>
                <div class="fc-head">
                    <div>
                        <div class="fc-sym">{f["symbol"]}</div>
                        <div class="fc-trades">{f["pair"]}</div>
                    </div>
                    <div>
                        <div class="fc-price" data-live-price="{f["pair"]}">{fmt_price(f["price"])}</div>
                        <div class="fv2-score">{f["score"]}/4 · OI ${oi_m:.1f}M</div>
                    </div>
                </div>
                <div class="fenix-verdict" {verdict_style}>{verdict_text}</div>
                <div class="fenix-crit">
                    <div class="fenix-c"><span class="lbl">{c1_label}{boost_html}</span>{ck(f["c1"])}</div>
                    <div class="fenix-c"><span class="lbl">{c2_label}</span>{ck(f["c2"])}</div>
                    <div class="fenix-c"><span class="lbl">{c3_label}</span>{ck(f["c3"])}</div>
                    <div class="fenix-c"><span class="lbl">30m={f["c4_30m"]} 1h={f["c4_1h"]}</span>{ck(f["c4"])}</div>
                </div>
                <div style="font-size:10px;color:#667085;margin-top:6px;text-align:center;">{tm_label} trades/dia · OI trend {f["oi_tr"]:+.1f}% · LSR {f["lsr_val"]:.2f}</div>
                {jacare_html}{reset_html}
            </div>"""


# ── RADAR FASE 1 ──────────────────────────────────────────────────────────────

# -- ENCRYPTOS / PHOENIX AI METHOD ------------------------------------------

def first_metric(d, keys, default=None):
    for key in keys:
        v = d.get(key)
        if v is not None:
            return v
    return default


def dominance_trend_from_data(data):
    sources = [data]
    for key in ("macro", "btcd", "dominance", "btc_dominance"):
        val = data.get(key)
        if isinstance(val, dict):
            sources.append(val)

    keys = (
        "btcd_trend", "btc_dominance_trend", "dominance_trend",
        "trend", "trend:5m", "trend:15m", "change", "change:5m", "change:15m",
    )
    for source in sources:
        for key in keys:
            v = source.get(key)
            if isinstance(v, (int, float)):
                return v
            if isinstance(v, str):
                try:
                    return float(v.replace("%", "").strip())
                except ValueError:
                    pass
    return None


def calc_encryptos_macro(data, btc):
    rsi_15m = g(btc, "rsi:15m", 50) or 50
    rsi_1h = g(btc, "rsi:1h", 50) or 50
    dom_trend = dominance_trend_from_data(data)
    dominance_up = dom_trend is not None and dom_trend > 0
    btc_stretched = rsi_15m >= 70 or rsi_1h >= 70
    reset_mode = rsi_15m <= 30 or rsi_1h <= 30
    hostile = btc_stretched and dominance_up
    dominance_unknown_warning = btc_stretched and dom_trend is None

    if hostile:
        status = "BLOQUEIO DE COMPRAS"
        color = "#D92D20"
        bg = "rgba(217,45,32,0.08)"
        border = "rgba(217,45,32,0.25)"
        msg = "BTC esticado e dominancia subindo. Altcoins bloqueadas: liquidez sendo sugada."
    elif reset_mode:
        status = "MODO CACA RESET"
        color = "#a371f7"
        bg = "rgba(163,113,247,.12)"
        border = "#a371f766"
        msg = "BTC corrigiu para RSI <= 30. Procurar alts que seguraram forca contra o BTC."
    elif dominance_unknown_warning:
        status = "BTC ESTICADO - VALIDAR BTCD"
        color = "#DC6803"
        bg = "rgba(220,104,3,0.08)"
        border = "rgba(220,104,3,0.25)"
        msg = "BTC esta sobrecomprado. A dominancia nao veio no JSON; validar BTCD antes de compra."
    else:
        status = "OPERAVEL COM FILTRO"
        color = "#039855"
        bg = "rgba(3,152,85,0.08)"
        border = "rgba(3,152,85,0.25)"
        msg = "Macro sem bloqueio pelo metodo Encryptos/Phoenix. Ainda exige setup e liquidez."

    return {
        "status": status,
        "color": color,
        "bg": bg,
        "border": border,
        "msg": msg,
        "hostile": hostile,
        "reset_mode": reset_mode,
        "btc_stretched": btc_stretched,
        "dominance_trend": dom_trend,
        "dominance_up": dominance_up,
        "dominance_unknown_warning": dominance_unknown_warning,
        "rsi_15m": rsi_15m,
        "rsi_1h": rsi_1h,
    }


def is_encryptos_blacklisted(symbol):
    base = sym_to_base(symbol).upper()
    return base in ENCRYPTOS_BLACKLIST or any(base.startswith(p) for p in ENCRYPTOS_BLACKLIST_PREFIXES)


def has_astronomical_injection(coin):
    oi = first_metric(coin, ("oi_total", "oi:5m", "oi"), 0) or 0
    trades_1d = first_metric(coin, ("trades_1D", "trades:1D", "trades"), 0) or 0
    tm_5m = g(coin, "trades_minute:5m", 0) or 0
    exp_15m = g(coin, "exp_btc:15m", 0) or 0
    return (
        oi >= ENCRYPTOS_ASTRONOMICAL_OI
        and trades_1d >= ENCRYPTOS_ASTRONOMICAL_TRADES_1D
        and tm_5m >= 500
        and exp_15m >= 10
    )


def check_encryptos_setups(symbol, coin, macro):
    if symbol == "BTCUSDT":
        return None

    base = sym_to_base(symbol)
    oi = first_metric(coin, ("oi_total", "oi:5m", "oi"), 0) or 0
    trades_1d = first_metric(coin, ("trades_1D", "trades:1D", "trades"), 0) or 0

    blacklisted = is_encryptos_blacklisted(symbol)
    blacklist_exception = blacklisted and has_astronomical_injection(coin)
    if blacklisted and not blacklist_exception:
        return None
    if oi < ENCRYPTOS_MIN_OI or trades_1d < ENCRYPTOS_MIN_TRADES_1D:
        return None

    exp_15m = g(coin, "exp_btc:15m", 0) or 0
    exp_5m = g(coin, "exp_btc:5m", 0) or 0
    exp_4h = g(coin, "exp_btc:4h", 0) or 0
    tm_5m = g(coin, "trades_minute:5m", 0) or 0
    range_30m = g(coin, "range_level:30m", 0) or 0
    range_1h = g(coin, "range_level:1h", 0) or 0
    lsr = first_metric(coin, ("lsr_value", "lsr:5m", "lsr"), 1) or 1
    oi_tr = g(coin, "oi_trend:5m", 0) or 0
    lsr_tr = g(coin, "lsr_trend:5m", 0) or 0
    rsi_5m = g(coin, "rsi:5m", 50) or 50
    rsi_15m = g(coin, "rsi:15m", 50) or 50
    price_change = g(coin, "price_change:1D", 0) or 0

    setup_defs = []

    if macro["reset_mode"] and exp_15m >= 3 and exp_5m >= 2 and lsr <= 1.0:
        setup_defs.append({
            "code": "A",
            "name": "Reset do Mercado",
            "priority": 1,
            "action": "Compra apenas apos rompimento da LTB de acumulacao.",
            "why": "Segurou forca contra o BTC durante reset e varejo esta shortando o fundo.",
        })

    if (range_30m >= 3 or range_1h >= 3) and oi_tr >= 1 and lsr_tr <= -1 and tm_5m >= 150:
        setup_defs.append({
            "code": "B",
            "name": "Pre-Ignicao",
            "priority": 3,
            "action": "Entrada na quebra da diagonal de acumulacao.",
            "why": "Acumulacao ativa, OI entrando, LSR caindo e robos aquecendo.",
        })

    if lsr <= 0.8 and tm_5m >= 300 and oi > 20_000_000:
        setup_defs.append({
            "code": "C",
            "name": "Caca a Liquidez",
            "priority": 2,
            "action": "Trade rapido de explosao direcional; reduzir exposicao cedo.",
            "why": "Shorts em excesso, HFT em ignicao e OI suficiente para squeeze real.",
        })

    recent_pullback = -30 <= price_change <= -20
    rsi_cooled = rsi_5m <= 55 and rsi_15m <= 60
    if exp_4h >= 20 and recent_pullback and rsi_cooled and exp_5m >= 2 and tm_5m >= 150:
        setup_defs.append({
            "code": "D",
            "name": "Pullback / Continuidade",
            "priority": 4,
            "action": "Entrada conservadora na retomada; evitar perseguir candle.",
            "why": "Tendencia 4h forte, pullback de 20-30%, RSI esfriou e 5m reacelerou.",
        })

    if not setup_defs:
        return None

    setup_defs = sorted(setup_defs, key=lambda x: x["priority"])
    primary = setup_defs[0]

    return {
        "symbol": base,
        "pair": symbol,
        "price": g(coin, "price", 0) or 0,
        "primary": primary,
        "setups": setup_defs,
        "rank_priority": primary["priority"],
        "blacklist_exception": blacklist_exception,
        "oi": oi,
        "trades_1d": trades_1d,
        "exp_15m": exp_15m,
        "exp_5m": exp_5m,
        "exp_4h": exp_4h,
        "tm_5m": tm_5m,
        "range_30m": range_30m,
        "range_1h": range_1h,
        "lsr": lsr,
        "oi_tr": oi_tr,
        "lsr_tr": lsr_tr,
        "rsi_5m": rsi_5m,
        "rsi_15m": rsi_15m,
        "price_change": price_change,
        "blocked": macro["hostile"],
    }


def html_encryptos_macro(macro, candidates, passed):
    dom = "n/d" if macro["dominance_trend"] is None else f'{macro["dominance_trend"]:+.2f}%'
    return f"""<div style="background:{macro["bg"]};border:1px solid {macro["border"]};border-radius:12px;padding:16px 20px;margin-bottom:16px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;">
        <div>
            <div style="font-size:18px;font-weight:900;color:{macro["color"]};">{macro["status"]}</div>
            <div style="font-size:13px;color:#475467;margin-top:4px;">{macro["msg"]}</div>
        </div>
        <div style="display:flex;gap:18px;flex-wrap:wrap;font-size:11px;color:#667085;">
            <div><strong style="display:block;color:#1D2939;font-size:15px;">{macro["rsi_15m"]:.1f}</strong>BTC RSI 15m</div>
            <div><strong style="display:block;color:#1D2939;font-size:15px;">{macro["rsi_1h"]:.1f}</strong>BTC RSI 1h</div>
            <div><strong style="display:block;color:#1D2939;font-size:15px;">{dom}</strong>BTCD trend</div>
            <div><strong style="display:block;color:#1D2939;font-size:15px;">{passed}/{candidates}</strong>setups</div>
        </div>
    </div>"""


def html_encryptos_card(item):
    opacity_style = 'style="opacity:0.45;filter:grayscale(60%);border-left-color:#D92D20;"' if item["blocked"] else ""
    setup_badges = "".join(
        f'<div class="fv2-badge" style="background:rgba(163,113,247,.12);color:#a371f7;border-color:#a371f760;">Setup {s["code"]}: {s["name"]}</div>'
        for s in item["setups"]
    )
    exception = ""
    if item["blacklist_exception"]:
        exception = '<div class="fv2-badge" style="background:rgba(220,104,3,.12);color:#DC6803;border-color:rgba(220,104,3,.3);">Blacklist liberada por injecao astronomica</div>'

    metrics = [
        ("OI", fmt_money_usd(item["oi"])),
        ("Trades 1D", fmt_compact_int(item["trades_1d"])),
        ("EXP 15m/5m", f'{item["exp_15m"]:.1f}/{item["exp_5m"]:.1f}'),
        ("LSR", f'{item["lsr"]:.2f}'),
        ("OI/LSR trend", f'{item["oi_tr"]:+.1f}%/{item["lsr_tr"]:+.1f}%'),
        ("Trades 5m", fmt_compact_int(item["tm_5m"])),
        ("Range 30m/1h", f'{item["range_30m"]}/{item["range_1h"]}'),
        ("RSI 5m/15m", f'{item["rsi_5m"]:.0f}/{item["rsi_15m"]:.0f}'),
    ]
    metric_html = "".join(
        f'<div class="fenix-c"><span class="lbl">{label}</span><strong style="font-size:11px;color:#1D2939;">{value}</strong></div>'
        for label, value in metrics
    )

    verdict = "BLOQUEADO PELA MACRO" if item["blocked"] else f'SETUP {item["primary"]["code"]} ATIVO'
    verdict_color = "#D92D20" if item["blocked"] else "#039855"
    verdict_bg = "rgba(217,45,32,.12)" if item["blocked"] else "rgba(3,152,85,.12)"

    return f"""<div class="fv2-card" {opacity_style}>
        <div class="fc-head">
            <div>
                <div class="fc-sym">{item["symbol"]}</div>
                <div class="fc-trades">{item["pair"]}</div>
            </div>
            <div>
                <div class="fc-price" data-live-price="{item["pair"]}">{fmt_price(item["price"])}</div>
                <div class="fv2-score">{fmt_money_usd(item["oi"])} OI</div>
            </div>
        </div>
        <div class="fenix-verdict" style="background:{verdict_bg};color:{verdict_color};">{verdict}</div>
        {setup_badges}
        {exception}
        <div style="font-size:12px;color:#475467;line-height:1.45;margin:10px 0 12px;">{item["primary"]["why"]}</div>
        <div class="fenix-crit">{metric_html}</div>
        <div style="background:#F9FAFB;border:1px solid #EAECF0;border-radius:8px;padding:10px 12px;margin-top:12px;font-size:12px;color:#475467;line-height:1.45;">
            <strong style="color:#1D2939;">Acao:</strong> {item["primary"]["action"]}<br>
            <strong style="color:#1D2939;">Saida:</strong> RP 50% apos impulso, stop no 0x0, alvo nas zonas de liquidez.
        </div>
    </div>"""


def html_encryptos_risk_block():
    return """<div style="background:#F9FAFB;border:1px solid #EAECF0;border-radius:12px;padding:16px 20px;margin-top:18px;color:#475467;line-height:1.55;">
        <div style="font-size:14px;font-weight:900;color:#344054;margin-bottom:8px;">Gerenciamento Phoenix</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;font-size:12.5px;">
            <div><strong style="color:#1570EF;">Entrada:</strong> nunca comprar BTC esticado; refinar no grafico pela LTB da acumulacao.</div>
            <div><strong style="color:#1570EF;">Alavancagem:</strong> 3x a 5x. Maximo absoluto 10x.</div>
            <div><strong style="color:#1570EF;">Conducao:</strong> realizou impulso, fazer RP parcial e mover stop para entrada.</div>
            <div><strong style="color:#1570EF;">Stop:</strong> nao adicionar margem em posicao perdedora; se o racional falhar, aceitar o stop.</div>
        </div>
    </div>"""


def has_real_trades_minute(coin):
    keys = ("trades_minute:1m", "trades_minute:5m", "trades_minute:15m")
    return any(coin.get(k) is not None for k in keys)


def activity_score_and_label(coin, trades_1d):
    tm_1m = g(coin, "trades_minute:1m", 0) or 0
    tm_5m = g(coin, "trades_minute:5m", 0) or 0
    if has_real_trades_minute(coin):
        peak = max(tm_1m, tm_5m)
        label = f"{fmt_compact_int(tm_1m)}/{fmt_compact_int(tm_5m)}"
        if peak >= 300:
            return 16, label, "real"
        if peak >= 150:
            return 10, label, "real"
        if peak >= 80:
            return 5, label, "real"
        return 0, label, "real"

    avg_min = (trades_1d or 0) / 1440
    label = f"~{fmt_compact_int(avg_min)}/m"
    if avg_min >= 800:
        return 12, label, "estimado 1D"
    if avg_min >= 300:
        return 8, label, "estimado 1D"
    if avg_min >= 100:
        return 4, label, "estimado 1D"
    return 0, label, "estimado 1D"


def classify_radar_setup(exp_15m, exp_5m, exp_1h, exp_4h, activity_pts, lsr, lsr_tr, oi_tr, range_max):
    if lsr <= 0.8 and activity_pts >= 8:
        return "Squeeze provavel", "Shorts contra + atividade elevada."
    if range_max >= 3 and oi_tr >= 1 and exp_5m > 0:
        return "Pre-ignicao", "Acumulacao + OI acelerando + EXP favoravel."
    if exp_15m >= 3 and exp_1h >= 10 and exp_4h >= 10:
        return "Forca estrutural", "EXP forte em 15m/1h/4h contra BTC."
    if exp_15m > 0 and exp_5m > 0 and oi_tr > 0:
        return "Radar", "Monitorar confirmacao em 1m/5m."
    return "Observacao", "Sinal parcial; precisa confirmar fluxo curto."


def score_encryptos_radar(symbol, coin):
    if symbol == "BTCUSDT":
        return None

    base = sym_to_base(symbol)
    oi = first_metric(coin, ("oi_total", "oi:5m", "oi"), 0) or 0
    trades_1d = first_metric(coin, ("trades_1D", "trades:1D", "trades"), 0) or 0
    if oi < 2_000_000 or trades_1d < 10_000:
        return None

    exp_15m = g(coin, "exp_btc:15m", 0) or 0
    exp_5m = g(coin, "exp_btc:5m", 0) or 0
    exp_1h = g(coin, "exp_btc:1h", 0) or 0
    exp_4h = g(coin, "exp_btc:4h", 0) or 0
    exp_1m = g(coin, "exp_btc:1m", 0) or 0
    oi_tr = g(coin, "oi_trend:5m", 0) or 0
    lsr = first_metric(coin, ("lsr_value", "lsr:5m", "lsr"), 1) or 1
    lsr_tr = g(coin, "lsr_trend:5m", 0) or 0
    pc_1d = g(coin, "price_change:1D", 0) or 0
    range_max = max(
        g(coin, "range_level:1m", 0) or 0,
        g(coin, "range_level:5m", 0) or 0,
        g(coin, "range_level:15m", 0) or 0,
        g(coin, "range_level:30m", 0) or 0,
        g(coin, "range_level:1h", 0) or 0,
    )
    ema_15m = g(coin, "ema_trend:15m", 0) or 0
    ema_1h = g(coin, "ema_trend:1h", 0) or 0

    activity_pts, activity_label, activity_source = activity_score_and_label(coin, trades_1d)

    score = 0
    if oi >= 10_000_000:
        score += 12
    elif oi >= 5_000_000:
        score += 8
    elif oi >= 2_000_000:
        score += 4

    if trades_1d >= 150_000:
        score += 10
    elif trades_1d >= 50_000:
        score += 6
    elif trades_1d >= 10_000:
        score += 2

    score += activity_pts

    if exp_15m >= 10:
        score += 12
    elif exp_15m >= 3:
        score += 9
    elif exp_15m > 0:
        score += 4

    if exp_5m >= 5:
        score += 10
    elif exp_5m >= 2:
        score += 7
    elif exp_5m > 0:
        score += 3

    if exp_1h >= 20:
        score += 10
    elif exp_1h >= 5:
        score += 6
    elif exp_1h > 0:
        score += 3

    if exp_4h >= 20:
        score += 8
    elif exp_4h > 0:
        score += 4

    if oi_tr >= 3:
        score += 8
    elif oi_tr >= 1:
        score += 5
    elif oi_tr > 0:
        score += 2

    if lsr <= 0.8:
        score += 8
    elif lsr <= 1.0:
        score += 5

    if lsr_tr <= -5:
        score += 8
    elif lsr_tr <= -1:
        score += 4
    elif lsr_tr > 5 and lsr > 1.5:
        score -= 6

    if range_max >= 4:
        score += 6
    elif range_max >= 2:
        score += 3

    if ema_15m > 0:
        score += 3
    if ema_1h > 0:
        score += 3
    if pc_1d > 0:
        score += 2

    if is_encryptos_blacklisted(symbol):
        score -= 8

    setup, summary = classify_radar_setup(
        exp_15m, exp_5m, exp_1h, exp_4h, activity_pts, lsr, lsr_tr, oi_tr, range_max
    )

    if score < 35:
        return None

    return {
        "symbol": base,
        "pair": symbol,
        "price": g(coin, "price", 0) or 0,
        "score": max(0, min(100, score)),
        "setup": setup,
        "summary": summary,
        "activity": activity_label,
        "activity_source": activity_source,
        "trades_1d": trades_1d,
        "price_change": pc_1d,
        "exp_1m": exp_1m,
        "exp_15m": exp_15m,
        "exp_5m": exp_5m,
        "exp_1h": exp_1h,
        "exp_4h": exp_4h,
        "oi": oi,
        "oi_tr": oi_tr,
        "lsr": lsr,
        "lsr_tr": lsr_tr,
        "range_max": range_max,
    }


def html_radar_score_color(score):
    if score >= 80:
        return "#039855"
    if score >= 65:
        return "#1570EF"
    if score >= 50:
        return "#DC6803"
    return "#667085"


def html_encryptos_radar_table(items):
    if not items:
        return '<div class="fv2-empty">Sem moedas no radar de possivel ignicao com score minimo.</div>'

    rows = []
    for idx, item in enumerate(items, 1):
        color = html_radar_score_color(item["score"])
        exp_color = "#039855" if item["exp_1h"] > 0 and item["exp_4h"] > 0 else "#DC6803"
        lsr_color = "#039855" if item["lsr"] <= 1 or item["lsr_tr"] < 0 else "#D92D20"
        pc_color = "#039855" if item["price_change"] >= 0 else "#D92D20"
        rows.append(f"""<tr>
            <td>{idx}</td>
            <td><strong>{item["symbol"]}</strong></td>
            <td data-live-price="{item["pair"]}">{fmt_price(item["price"])}</td>
            <td style="color:{pc_color};">{item["price_change"]:+.1f}%</td>
            <td style="color:#1570EF;font-weight:800;">{item["setup"]}</td>
            <td title="{item["activity_source"]}">{item["activity"]}</td>
            <td style="color:{exp_color};">{item["exp_1h"]:.1f}</td>
            <td style="color:{exp_color};">{item["exp_4h"]:.1f}</td>
            <td>{fmt_money_usd(item["oi"])}</td>
            <td style="color:{lsr_color};">{item["lsr"]:.2f}<span style="color:#667085;">/{item["lsr_tr"]:+.1f}</span></td>
            <td>{item["range_max"]}</td>
            <td><strong style="color:{color};">{item["score"]}</strong></td>
            <td>{item["summary"]}</td>
        </tr>""")

    return f"""<div style="background:#FFFFFF;border:1px solid #EAECF0;border-radius:12px;overflow:hidden;margin-top:22px;">
        <div style="padding:13px 16px;border-bottom:1px solid #EAECF0;color:#039855;font-weight:900;">
            LEITURA PHOENIX <span style="color:#667085;font-size:12px;font-weight:700;">Possivel ignicao ranqueada. Score alto nao substitui rompimento/confirmacao.</span>
        </div>
        <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;font-size:12px;min-width:980px;">
                <thead>
                    <tr style="color:#039855;text-align:left;background:#F9FAFB;">
                        <th style="padding:10px 8px;">#</th>
                        <th style="padding:10px 8px;">Ativo</th>
                        <th style="padding:10px 8px;">Preco</th>
                        <th style="padding:10px 8px;">Δ1D</th>
                        <th style="padding:10px 8px;">Setup</th>
                        <th style="padding:10px 8px;">Trades/m</th>
                        <th style="padding:10px 8px;">EXP1H</th>
                        <th style="padding:10px 8px;">EXP4H</th>
                        <th style="padding:10px 8px;">OI</th>
                        <th style="padding:10px 8px;">LSR/tr</th>
                        <th style="padding:10px 8px;">Rg</th>
                        <th style="padding:10px 8px;">Score</th>
                        <th style="padding:10px 8px;">Resumo</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </div>
    </div>"""


def html_encryptos_radar_summary(items):
    if not items:
        return ""

    def first_by_setup(name):
        return next((i for i in items if i["setup"] == name), None)

    cards = [
        ("Maior oportunidade", items[0], "#039855"),
        ("Melhor pre-ignicao", first_by_setup("Pre-ignicao"), "#1570EF"),
        ("Forca estrutural", first_by_setup("Forca estrutural"), "#DC6803"),
    ]
    html = []
    for title, item, color in cards:
        if not item:
            continue
        html.append(f"""<div style="border:1px solid {color};border-radius:8px;padding:12px 14px;background:#FFFFFF;">
            <div style="color:{color};font-weight:900;font-size:14px;">{title}</div>
            <div style="font-size:12px;color:#475467;margin-top:4px;"><strong>{item["symbol"]}</strong> · score {item["score"]} · {item["summary"]}</div>
        </div>""")
    if not html:
        return ""
    return f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:12px;">{"".join(html)}</div>'


def build_encryptos_radar(all_coins):
    items = []
    for sym, coin in all_coins.items():
        item = score_encryptos_radar(sym, coin)
        if item:
            items.append(item)
    items = sorted(items, key=lambda x: (x["score"], x["oi"], x["trades_1d"]), reverse=True)[:20]
    return html_encryptos_radar_table(items) + html_encryptos_radar_summary(items)


def build_encryptos_section(data, btc):
    all_coins = data.get("data", {})
    macro = calc_encryptos_macro(data, btc)
    candidates = [sym for sym in all_coins if sym != "BTCUSDT"]

    matches = []
    if not macro["hostile"]:
        for sym, coin in all_coins.items():
            item = check_encryptos_setups(sym, coin, macro)
            if item:
                matches.append(item)

    matches = sorted(
        matches,
        key=lambda x: (x["rank_priority"], -len(x["setups"]), -x["tm_5m"], -x["oi"]),
    )[:12]

    macro_html = html_encryptos_macro(macro, len(candidates), len(matches))
    if macro["hostile"]:
        cards_html = '<div class="fv2-empty">Bloqueio macro ativo. Nenhuma compra em altcoin deve ser sinalizada agora.</div>'
    elif not matches:
        cards_html = '<div class="fv2-empty">Nenhuma moeda passou nos filtros Encryptos/Phoenix: OI >= $10M, trades 1D >= 150k, blacklist e Setups A-D.</div>'
    else:
        cards_html = "".join(html_encryptos_card(item) for item in matches)

    return {
        "macro": macro,
        "matches": matches,
        "macro_html": macro_html,
        "cards_html": cards_html,
        "radar_html": build_encryptos_radar(all_coins),
        "risk_html": html_encryptos_risk_block(),
    }


def calc_fase1(symbol, coin):
    rl_1d  = g(coin, "range_level:1D",  0) or 0
    rl_4h  = g(coin, "range_level:4h",  0) or 0
    rl_1h  = g(coin, "range_level:1h",  0) or 0
    rl_30m = g(coin, "range_level:30m", 0) or 0
    rl_15m = g(coin, "range_level:15m", 0) or 0
    rsi    = g(coin, "rsi:1m",  50) or 50
    exp    = g(coin, "exp_btc:1m", 0) or 0

    score = rl_1d * 20 + rl_4h * 10 + rl_1h * 5 + rl_30m * 3 + rl_15m * 2
    if score < 30:
        return None

    pre_setup = rl_1d == 0 and (rl_4h >= 3 or rl_1h >= 3 or rl_30m >= 3)

    if score >= 110:
        prob = "🟢 ALTA PROBABILIDADE"
        prob_color = "#039855"
    elif score >= 80:
        prob = "🟡 MÉDIA"
        prob_color = "#DC6803"
    else:
        prob = "⚪ MONITORAR"
        prob_color = "#667085"

    return {
        "symbol":     sym_to_base(symbol),
        "pair":       symbol,
        "price":      g(coin, "price", 0) or 0,
        "score":      score,
        "rsi":        rsi,
        "exp":        exp,
        "prob":       prob,
        "prob_color": prob_color,
        "pre_setup":  pre_setup,
    }

# ── AGENTES ───────────────────────────────────────────────────────────────────

def agent_cz(scored):
    oi_m   = scored["oi"] / 1_000_000
    oi_tr  = scored["oi_trend"]
    lsr    = scored["lsr"]
    lsr_tr = scored["lsr_trend"]
    liq = "🟢 alta liquidez" if oi_m > 50 else ("🟡 liquidez moderada" if oi_m > 5 else "🔴 baixa liquidez")

    if oi_tr > 3 and lsr_tr < -8:
        em = "🟢"
        msg = f"🐊 Jacaré CONFIRMADO (+{oi_tr:.1f}% em 30m, +{oi_tr*0.9:.1f}% em 1h) + LSR caindo. OI: ${oi_m:.1f}M ({liq}). Squeeze confiável. 🐊 LSR tendência caindo + OI subindo — squeeze se formando."
    elif oi_tr > 2 and lsr_tr < -3:
        em = "🟡"
        msg = f"🟡 🐊 Jacaré PARCIAL (só 5m). OI 1h: {oi_tr*0.7:.1f}%. OI: ${oi_m:.1f}M ({liq}). Verificar CoinGlass."
    elif oi_tr > 0:
        em = "🟡"
        msg = f"🟡 OI crescendo +{oi_tr:.1f}% em 30m. OI: ${oi_m:.1f}M ({liq}). LSR: {lsr:.2f}."
    else:
        em = "🔴"
        msg = f"🔴 OI estagnado ou caindo. OI: ${oi_m:.1f}M ({liq}). LSR: {lsr:.2f}."

    return em, msg


def agent_fenix_agent(scored):
    exp_1m = scored["exp_1m"]
    exp_1h = scored["exp_1h"]
    rsi    = scored["rsi"]
    tm_1m  = scored["tm_1m"]

    if exp_1m > 5 and 50 <= rsi <= 70:
        em = "🟢"
        msg = f"🟢 Momentum forte — EXP 1m {exp_1m}, 1h {exp_1h}, RSI {rsi:.0f}. {tm_1m} trades/min."
    elif exp_1m > 2:
        em = "🟡"
        msg = f"🟡 Momentum moderado — EXP 1m {exp_1m}, 1h {exp_1h}, {tm_1m} trades/min."
    else:
        em = "⚪"
        msg = f"⚪ EXP 1m {exp_1m}, 1h {exp_1h}, RSI {rsi:.0f}. Momentum fraco."

    return em, msg


def agent_safe(scored, btc):
    pc      = scored["price_change"]
    bpc     = g(btc, "price_change:1D", 0) or 0
    exp_15m = scored["exp_15m"]

    if pc > bpc + 1:
        em = "🟢"
        msg = f"🟢 Força própria real — alt subiu {pc:.1f}% no dia, acima do BTC. EXP 15m: {exp_15m}."
    elif pc > 0:
        em = "🟡"
        msg = f"🟡 Alt subiu {pc:.1f}% no dia. EXP 15m: {exp_15m}."
    else:
        em = "🔴"
        msg = f"🔴 Alt caindo {pc:.1f}% no dia. Fraqueza real."

    return em, msg


def agent_verdict(em_cz, em_fenix, em_safe):
    pos = sum(1 for e in [em_cz, em_fenix, em_safe] if e == "🟢")
    neg = sum(1 for e in [em_cz, em_fenix, em_safe] if e == "🔴")

    if pos >= 2 and neg == 0:
        return "#039855", "🎯 MAIORIA POSITIVA — 2/3 aprovam sem veto. Entrar com stops ajustados."
    elif pos >= 2:
        return "#DC6803", "🎯 MAIORIA POSITIVA com ressalvas. Stops bem posicionados obrigatórios."
    elif neg >= 2:
        return "#D92D20", "🚫 MAIORIA NEGATIVA — não entrar agora."
    return "#DC6803", "🎯 DIVIDIDO — Sem consenso claro. Aguardar confirmação adicional."

# ── VEREDITO ──────────────────────────────────────────────────────────────────

def get_verdict(scored, macro):
    score = scored["score"]
    hostile = macro["hostile"]

    if hostile:
        return "❌ NÃO ENTRAR (macro ruim)", "#D92D20", "rgba(217,45,32,0.12)", "#D92D20", "🚫 Setup ruim - passar reto"
    if score >= 32:
        return "✅ ENTRAR AGORA", "#039855", "rgba(3,152,85,0.12)", "#039855", "🎯 Setup excelente — executar"
    elif score >= 24:
        return "⏳ AGUARDAR CONFIRMAÇÃO", "#DC6803", "rgba(220,104,3,0.12)", "#DC6803", "⚠️ Aguardar sinal adicional"
    elif score >= 18:
        return "👁️ OBSERVAR", "#667085", "rgba(102,112,133,0.08)", "#667085", "📊 Monitorar de perto"
    return "❌ NÃO ENTRAR", "#D92D20", "rgba(217,45,32,0.12)", "#D92D20", "🚫 Setup ruim - passar reto"

# ── HTML GENERATORS ───────────────────────────────────────────────────────────

def html_macro_banner(macro, rsi_color, total_syms):
    return f"""<div class="macro-banner" style="background:{macro["bg"]};border:1px solid {macro["border"]};">
    <div class="macro-left">
        <div class="macro-icon">{macro["icon"]}</div>
        <div>
            <div class="macro-status" style="color:{macro["color"]};">{macro["status"]}</div>
            <div class="macro-msg">{macro["msg"]}</div>
        </div>
    </div>
    <div class="macro-stats">
        <div class="macro-stat"><div class="val" style="color:{rsi_color};">{macro["rsi_btc"]:.2f}</div><div class="lbl">BTC RSI 1D</div></div>
        <div class="macro-stat"><div class="val">{macro["avg_fr"]:+.4f}%</div><div class="lbl">Avg Funding</div></div>
        <div class="macro-stat"><div class="val">{total_syms}</div><div class="lbl">Moedas scan</div></div>
    </div>
</div>"""


def html_fenix_card(f):
    blocked = f["blocked"]
    opacity_style = 'style="opacity:0.45;filter:grayscale(60%);border:1px solid rgba(217,45,32,.4);"' if blocked else ""
    verdict_style = 'style="background:rgba(217,45,32,.12);color:#D92D20;"'
    verdict_text  = "🔴 BLOQUEADO — MACRO HOSTIL" if blocked else ("✅ ENTRAR AGORA" if f["score"] == 4 else ("🟢 ENTRAR" if f["score"] == 3 else "⚠️ AGUARDAR"))
    if not blocked and f["score"] == 4:
        verdict_style = 'style="background:rgba(3,152,85,.12);color:#039855;"'
    elif not blocked and f["score"] == 3:
        verdict_style = 'style="background:rgba(3,152,85,.08);color:#039855;"'

    def ck(ok): return f'<span class="ck" style="color:{("#039855" if ok else "#D92D20")};">{"✅" if ok else "❌"}</span>'

    jacare_html = '<div style="font-size:10.5px;color:#039855;margin-top:4px;text-align:center;font-weight:600;">🐊 Jacaré aberto</div>' if f["jacare"] else ""

    return f"""<div class="fenix-card" {opacity_style}>
                <div class="fc-head">
                    <div>
                        <div class="fc-sym">{f["symbol"]}</div>
                        <div class="fc-trades">{f["pair"]}</div>
                    </div>
                    <div>
                        <div class="fc-price" data-live-price="{f["pair"]}">{fmt_price(f["price"])}</div>
                        <div class="fc-score">{f["score"]}/4</div>
                    </div>
                </div>
                <div class="fenix-verdict" {verdict_style}>{verdict_text}</div>
                <div class="fenix-crit">
                    <div class="fenix-c"><span class="lbl">EXP {f["c1_val"]:.2f}</span>{ck(f["c1"])}</div>
                    <div class="fenix-c"><span class="lbl">Tr {f["c2_val"]}k</span>{ck(f["c2"])}</div>
                    <div class="fenix-c"><span class="lbl">RSI {f["c3_val"]:.1f}</span>{ck(f["c3"])}</div>
                    <div class="fenix-c"><span class="lbl">Rng15m {f["c4_val"]}</span>{ck(f["c4"])}</div>
                </div>
                <div style="font-size:10.5px;color:#667085;margin-top:8px;text-align:center;">{f["tm_1d"]/1000:.1f}k trades/dia</div>
                {jacare_html}
            </div>"""


def html_veredito_card(scored, btc, macro):
    vtext, vcolor, vbg, vborder, vresume = get_verdict(scored, macro)
    em_cz, msg_cz       = agent_cz(scored)
    em_fen, msg_fen     = agent_fenix_agent(scored)
    em_sfe, msg_sfe     = agent_safe(scored, btc)
    av_color, av_msg    = agent_verdict(em_cz, em_fen, em_sfe)

    price       = scored["price"]
    stop        = price * 0.97
    tp1         = price * 1.05
    tp2         = price * 1.10
    trend_label = coin_trend_label(scored["price_change"])

    tend_itens_html = " | ".join(scored["tend_itens"]) if scored["tend_itens"] else "Sem dados de tendência"
    tend_color = "#039855" if scored["tend_pts"] >= 5 else ("#DC6803" if scored["tend_pts"] >= 2 else "#D92D20")

    def alerta_color(msg):
        if any(x in msg for x in ["🟢","✅","💎","💪"]):
            return "#039855"
        if "💎💎" in msg:
            return "#039855"
        if "⚡" in msg:
            return "#a371f7"
        if any(x in msg for x in ["🟡","⚠️","🔴"]):
            return "#DC6803"
        return "#667085"

    alertas1 = [scored["msg_rsi"], scored["msg_exp"], scored["msg_daily"],
                scored["msg_intra"], scored["msg_timing"],
                scored["msg_1h"], scored["msg_4h"], scored["msg_fr"]]
    alertas2 = [scored["msg_align"], scored["msg_btc"],
                scored["msg_jac"], "📊 Histórico: sem dados"]

    def li(msg):
        c = alerta_color(msg)
        rsi_num = f" <span class='alerta-num'>({scored['rsi']:.1f})</span>" if "RSI" in msg and "ZONA" in msg else ""
        exp_num = f" <span class='alerta-num'>(EXP 15m: {scored['exp_15m']})</span>" if "Combustível" in msg or "Subindo mais" in msg else ""
        fr_num  = f" <span class='alerta-num'>(FR {scored['fr_pct']:.4f}%)</span>" if "FR" in msg else ""
        return f'<div class="alerta-item" style="color:{c};">{msg}{rsi_num}{exp_num}{fr_num}</div>'

    alertas1_html = "\n".join(li(m) for m in alertas1)
    alertas2_html = "\n".join(li(m) for m in alertas2)

    return f"""<div class="veredito-card">
            <div class="verdict-banner" style="background:{vbg};border-bottom:2px solid {vborder};">
                <div class="verdict-text" style="color:{vcolor};">{vtext}</div>
                <div class="verdict-resumo">{vresume}</div>
            </div>
            <div class="card-body">
                <div class="coin-header">
                    <div>
                        <div class="coin-symbol">{scored["base"]}</div>
                        <div class="coin-full">{scored["symbol"]} &bull; {trend_label}</div>
                    </div>
                    <div class="coin-right">
                        <div class="coin-price" data-live-price="{scored["symbol"]}">{fmt_price(price)}</div>
                        <div class="score-badge">Score {scored["score"]}/40</div>
                    </div>
                </div>
                <div class="live-bar" data-live-bar="{scored["symbol"]}">
                    <span class="lm-tag">LIVE</span>
                    <span class="lm-item" data-live-price-sm="{scored["symbol"]}">{fmt_price(price)}</span>
                    <span class="lm-sep">·</span>
                    <span class="lm-item" data-live-fr="{scored["symbol"]}">FR {scored["fr_pct"]:+.4f}%</span>
                    <span class="lm-sep">·</span>
                    <span class="lm-item" data-live-oi="{scored["symbol"]}">OI ${scored["oi"]/1_000_000:.1f}M</span>
                    <span class="lm-sep">·</span>
                    <span class="lm-item" data-live-lsr="{scored["symbol"]}">LSR {scored["lsr"]:.2f}</span>
                </div>
                <div style="margin:6px 0;padding:6px 10px;background:rgba(127,86,217,0.08);border-left:2px solid #7F56D9;border-radius:4px;font-size:10.8px;color:#7F56D9;line-height:1.4;">
                    <strong style="color:#7F56D9;">🎬 Tendência (+{scored["tend_pts"]} pts):</strong>
                    <span style="color:{tend_color};">{tend_itens_html}</span>
                </div>
                <div class="alertas-list">{alertas1_html}</div>
                <div class="alertas-list">{alertas2_html}</div>
                <div style="margin:10px 0;padding:10px 12px;background:rgba(220,104,3,0.08);border:1px solid #DC6803;border-radius:8px;font-size:11.5px;color:#DC6803;">
                    <strong>📋 ANTES DE ENTRAR — confirme no CoinGlass:</strong><br>
                    ✓ OI no 4H subindo? &nbsp;✓ LSR caindo consistentemente? &nbsp;✓ FR normal (&lt; 0.03%)?
                </div>
                <div class="operacao-box">
                    <div class="op-title">🛡️ SUGESTÃO DE OPERAÇÃO</div>
                    <div class="op-line">🛑 SAIR SE CAIR PRA: <strong>{fmt_price(stop)}</strong> <span style="color:#D92D20;">(perde -3%)</span></div>
                    <div class="op-line">💰 REALIZAR METADE EM: <strong>{fmt_price(tp1)}</strong> <span style="color:#039855;">(ganha +5%)</span></div>
                    <div class="op-line">🏆 REALIZAR TUDO EM: <strong>{fmt_price(tp2)}</strong> <span style="color:#039855;">(ganha +10%)</span></div>
                    <div class="op-line" style="color:#DC6803;">🚨 OU SAIR SE FICAR SOBRECOMPRADA (RSI &gt; 80)</div>
                </div>
                <div style="margin-top:14px;padding:12px 14px;background:rgba(21,112,239,0.04);border:1px solid rgba(21,112,239,0.15);border-radius:10px;">
                    <div style="font-size:12px;font-weight:700;color:#1570EF;letter-spacing:1px;margin-bottom:10px;">🧠 ANÁLISE DOS AGENTES</div>
                    <div style="font-size:12px;margin-bottom:7px;line-height:1.5;">
                        <span style="font-weight:700;color:#667085;min-width:72px;display:inline-block;">🐊 CZ</span>
                        <span style="color:#475467;">{msg_cz}</span>
                    </div>
                    <div style="font-size:12px;margin-bottom:7px;line-height:1.5;">
                        <span style="font-weight:700;color:#667085;min-width:72px;display:inline-block;">⚡ FÊNIX</span>
                        <span style="color:#475467;">{msg_fen}</span>
                    </div>
                    <div style="font-size:12px;margin-bottom:10px;line-height:1.5;">
                        <span style="font-weight:700;color:#667085;min-width:72px;display:inline-block;">🛡️ SAFE</span>
                        <span style="color:#475467;">{msg_sfe}</span>
                    </div>
                    <div style="font-size:12px;font-weight:700;padding:7px 10px;border-radius:7px;border:1px solid {av_color};color:{av_color};background:rgba(255,255,255,0.6);text-align:center;">
                        {av_msg}
                    </div>
                </div>
            </div>
        </div>"""


def html_fase1_card(f):
    pre_badge = '<div class="pre-setup-badge">🔮 PRE-SETUP — acumulação intra-day antes do diário</div>' if f["pre_setup"] else ""
    return f"""<div class="fase1-card">
            <div class="f1-header">
                <span class="f1-symbol">{f["symbol"]}</span>
                <span style="font-size:12px;font-weight:700;color:#7F56D9;">{f["score"]}</span>
            </div>
            <div style="font-size:11px;color:#667085;margin-bottom:4px;">{f["symbol"]}</div>
            <div style="font-size:14px;color:#1570EF;margin-bottom:6px;" data-live-price="{f["pair"]}">{fmt_price(f["price"])}</div>
            <div style="font-size:13px;font-weight:700;margin-bottom:6px;color:{f["prob_color"]};">{f["prob"]}</div>
            {pre_badge}
            <div style="font-size:11px;color:#667085;margin-bottom:6px;">RSI: {f["rsi"]:.1f} &bull; EXP: {f["exp"]}</div>
            <div style="font-size:10px;color:#7F56D9;font-style:italic;">⚡ Setup PRÉ-EXPLOSÃO</div>
        </div>"""

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Inter',sans-serif;background:#F9FAFB;color:#475467;min-height:100vh;font-size:14px;font-weight:400;}
.header{background:#FFFFFF;border-bottom:1px solid #EAECF0;box-shadow:0 1px 8px rgba(0,0,0,0.06);padding:16px 24px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;}
.header-title{font-size:18px;font-weight:800;color:#1D2939;}
.header-meta{display:flex;gap:16px;align-items:center;font-size:13px;color:#667085;flex-wrap:wrap;}
.btn-refresh{background:#039855;color:white;border:none;padding:7px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;}
.btn-refresh:hover{background:#027A48;}
.container{max-width:1400px;margin:auto;padding:24px;}
.macro-banner{border-radius:16px;padding:20px 28px;margin-bottom:36px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;}
.macro-left{display:flex;align-items:center;gap:14px;}
.macro-icon{font-size:36px;}
.macro-status{font-size:22px;font-weight:800;}
.macro-msg{font-size:13px;opacity:.9;margin-top:3px;}
.macro-stats{display:flex;gap:22px;flex-wrap:wrap;}
.macro-stat .val{font-size:20px;font-weight:800;}
.macro-stat .lbl{font-size:10px;color:#667085;margin-top:2px;}
.section-header{display:flex;align-items:center;gap:14px;margin:36px 0 18px;}
.section-title{font-size:18px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;white-space:nowrap;}
.section-line{flex:1;height:1px;background:#EAECF0;}
.veredito-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:22px;}
.veredito-card{background:#FFFFFF;border:1px solid #D0D5DD;border-radius:16px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,0.12);}
.verdict-banner{padding:22px 20px;text-align:center;}
.verdict-text{font-size:28px;font-weight:900;letter-spacing:-.3px;}
.verdict-resumo{font-size:14px;color:#475467;margin-top:8px;font-weight:600;opacity:.95;}
.alertas-list{display:flex;flex-direction:column;gap:8px;background:#F9FAFB;border:1px solid #EAECF0;border-radius:10px;padding:13px 14px;margin-bottom:12px;}
.alerta-item{font-size:13.5px;font-weight:600;line-height:1.45;}
.alerta-num{font-size:11px;color:#667085;font-weight:500;font-family:monospace;margin-left:4px;}
.op-line{font-size:13px;color:#475467;margin-bottom:7px;line-height:1.45;}
.op-line:last-child{margin-bottom:0;}
.op-line strong{color:#1D2939;font-family:monospace;}
.card-body{padding:20px;}
.coin-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px;}
.coin-symbol{font-size:30px;font-weight:900;color:#1D2939;letter-spacing:-1px;}
.coin-full{font-size:11px;color:#667085;margin-top:2px;}
.coin-right{text-align:right;}
.coin-price{font-size:16px;font-weight:700;color:#1570EF;}
.score-badge{font-size:12px;font-weight:700;color:#1570EF;background:#EFF8FF;padding:3px 10px;border-radius:20px;margin-top:5px;display:inline-block;}
.operacao-box{background:#F9FAFB;border:1px solid #EAECF0;border-radius:10px;padding:14px;}
.op-title{font-size:11px;font-weight:700;color:#667085;margin-bottom:10px;}
.fase1-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;}
.fase1-card{background:#FFFFFF;border:1px solid #a371f722;border-left:4px solid #7F56D9;border-radius:10px;padding:14px;box-shadow:0 8px 24px rgba(0,0,0,0.12);}
.f1-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;}
.f1-symbol{font-size:18px;font-weight:800;color:#1D2939;}
.pre-setup-badge{background:rgba(163,113,247,.15);color:#a371f7;border:1px solid #a371f7;border-radius:6px;padding:5px 9px;font-size:10.5px;font-weight:700;margin-bottom:6px;line-height:1.3;}
.fenix-banner{background:linear-gradient(135deg,rgba(255,155,77,.13),rgba(255,107,53,.07));border:1px solid #ff9b4d55;border-radius:12px;padding:14px 20px;margin-bottom:16px;font-size:13px;color:#ffd0a8;line-height:1.6;}
.fenix-banner strong{color:#ff9b4d;}
.fenix-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(265px,1fr));gap:14px;margin-bottom:30px;}
.fenix-card{background:#FFFFFF;border:1px solid #D0D5DD;border-radius:16px;padding:16px;border-left:4px solid #DC6803;box-shadow:0 8px 24px rgba(0,0,0,0.12);}
.fenix-card .fc-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;gap:10px;}
.fenix-card .fc-sym{font-size:22px;font-weight:900;color:#1D2939;letter-spacing:-.5px;}
.fenix-card .fc-price{font-size:13px;color:#1570EF;font-weight:700;text-align:right;}
.fenix-card .fc-trades{font-size:10px;color:#667085;margin-top:3px;}
.fenix-card .fc-score{font-size:11px;color:#DC6803;font-weight:700;text-align:right;margin-top:3px;}
.fenix-verdict{padding:8px 12px;border-radius:8px;text-align:center;font-weight:800;font-size:14px;margin-bottom:12px;}
.fenix-crit{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;}
.fenix-c{background:#F9FAFB;border:1px solid #EAECF0;border-radius:6px;padding:6px 8px;display:flex;justify-content:space-between;align-items:center;gap:6px;}
.fenix-c span.lbl{color:#475467;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.fenix-c .ck{font-size:13px;flex-shrink:0;}
.fenix-empty{background:#FFFFFF;border:1px solid #D0D5DD;border-radius:16px;padding:24px;text-align:center;color:#667085;font-size:14px;margin-bottom:30px;}
.fv2-banner{background:linear-gradient(135deg,rgba(21,112,239,.08),rgba(0,86,179,.04));border:1px solid rgba(21,112,239,.3);border-radius:12px;padding:14px 20px;margin-bottom:16px;font-size:13px;color:#475467;line-height:1.6;}
.fv2-banner strong{color:#1570EF;}
.fv2-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-bottom:30px;}
.fv2-card{background:#FFFFFF;border:1px solid #D0D5DD;border-radius:16px;padding:16px;border-left:4px solid #1570EF;box-shadow:0 8px 24px rgba(0,0,0,0.12);}
.fv2-card .fc-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;gap:10px;}
.fv2-card .fc-sym{font-size:22px;font-weight:900;color:#1D2939;letter-spacing:-.5px;}
.fv2-card .fc-price{font-size:13px;color:#1570EF;font-weight:700;text-align:right;}
.fv2-card .fc-trades{font-size:10px;color:#667085;margin-top:3px;}
.fv2-score{font-size:11px;color:#1570EF;font-weight:700;text-align:right;margin-top:3px;}
.fv2-badge{margin-top:6px;padding:4px 8px;border-radius:6px;font-size:10.5px;font-weight:700;text-align:center;background:rgba(3,152,85,.08);color:#039855;border:1px solid rgba(3,152,85,.25);}
.fv2-empty{background:#FFFFFF;border:1px solid #D0D5DD;border-radius:16px;padding:24px;text-align:center;color:#667085;font-size:14px;margin-bottom:30px;}
.dash-nav{display:flex;gap:4px;margin-bottom:24px;border-bottom:1px solid #EAECF0;padding-bottom:0;}
.dash-tab{background:none;border:none;border-bottom:2px solid transparent;padding:10px 18px;font-size:13px;font-weight:600;color:#667085;cursor:pointer;transition:all .15s;margin-bottom:-1px;}
.dash-tab.active{color:#344054;border-bottom-color:#1570EF;}
.dash-tab:hover:not(.active){color:#475467;}
.live-bar{display:flex;align-items:center;gap:6px;padding:5px 10px;background:#F0FDF4;border:1px solid #D1FADF;border-radius:6px;margin-bottom:10px;flex-wrap:wrap;}
.lm-tag{background:#039855;color:#fff;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:900;letter-spacing:.5px;}
.lm-item{font-size:11px;color:#667085;font-family:monospace;transition:color .3s;}
.lm-sep{color:#D0D5DD;font-size:11px;}
@media(max-width:768px){
    .veredito-grid{grid-template-columns:1fr;}
    .fenix-grid{grid-template-columns:1fr;}
    .macro-stats{gap:14px;}
    .verdict-text{font-size:22px;}
}
"""

# ── PROCESS DATA (para web app) ───────────────────────────────────────────────

def process_data(data):
    """Processa JSON do painel e retorna dict com resultados + HTML sections."""
    ts        = data.get("timestamp", datetime.now(timezone.utc).isoformat())
    exchange  = data.get("exchange", "binanceusdm")
    all_coins = data.get("data", {})
    btc = all_coins.get("BTCUSDT", {})
    macro = calc_macro(btc, all_coins)
    encryptos = build_encryptos_section(data, btc)

    scored_list = []
    for sym, coin in all_coins.items():
        if sym == "BTCUSDT":
            continue
        scored_list.append(score_coin(sym, coin, btc))

    top5 = sorted(scored_list, key=lambda x: x["score"], reverse=True)[:5]

    fenix_list = []
    for sym, coin in all_coins.items():
        if sym == "BTCUSDT":
            continue
        f = check_fenix(sym, coin, macro)
        if f:
            fenix_list.append(f)
    fenix_list = sorted(fenix_list, key=lambda x: x["score"], reverse=True)[:5]

    fase1_list = []
    for sym, coin in all_coins.items():
        if sym == "BTCUSDT":
            continue
        f = calc_fase1(sym, coin)
        if f:
            fase1_list.append(f)
    fase1_list = sorted(fase1_list, key=lambda x: x["score"], reverse=True)[:10]

    fenix_v2_list = []
    for sym, coin in all_coins.items():
        if sym == "BTCUSDT":
            continue
        f = check_fenix_v2(sym, coin, macro, btc)
        if f:
            fenix_v2_list.append(f)
    fenix_v2_list = sorted(fenix_v2_list, key=lambda x: (x["score"], x["jacare"]), reverse=True)[:5]

    rsi_color = "#D92D20" if macro["rsi_btc"] < 45 else ("#DC6803" if macro["rsi_btc"] < 55 else "#039855")

    macro_hostile_block = ""
    if macro["hostile"]:
        macro_hostile_block = """<div style="background:#FEE4E2;border:2px solid #D92D20;border-radius:12px;padding:16px 22px;margin-bottom:16px;text-align:center;">
            <div style="font-size:18px;font-weight:900;color:#D92D20;letter-spacing:1px;">🔴 MACRO HOSTIL — Não operar pelo MODO FÊNIX agora</div>
            <div style="font-size:13px;color:#912018;margin-top:6px;opacity:.85;">O ambiente de mercado está desfavorável. Aguarde a macro normalizar antes de entrar.</div>
        </div>"""

    macro_hostile_v2_block = ""
    if macro["hostile"]:
        macro_hostile_v2_block = """<div style="background:#FEE4E2;border:2px solid #D92D20;border-radius:12px;padding:16px 22px;margin-bottom:16px;text-align:center;">
            <div style="font-size:18px;font-weight:900;color:#D92D20;letter-spacing:1px;">🔴 MACRO HOSTIL — Não operar pelo PHOENIX V2 agora</div>
            <div style="font-size:13px;color:#912018;margin-top:6px;opacity:.85;">Aguarde BTC estabilizar antes de usar os filtros V2.</div>
        </div>"""

    fenix_cards_html = "".join(html_fenix_card(f) for f in fenix_list)
    if not fenix_list:
        fenix_cards_html = '<div class="fenix-empty">Nenhuma moeda passou nos critérios mínimos do Modo Fênix.</div>'

    fenix_v2_cards_html = "".join(html_fenix_v2_card(f) for f in fenix_v2_list)
    if not fenix_v2_list:
        fenix_v2_cards_html = '<div class="fv2-empty">Nenhuma moeda passou nos critérios do Phoenix V2. (OI ≥ $10M + 1M trades/dia + score ≥ 3/4)</div>'

    veredito_cards_html = "".join(html_veredito_card(s, btc, macro) for s in top5)
    if not top5:
        veredito_cards_html = '<p style="color:#667085;">Sem moedas para análise.</p>'

    fase1_cards_html = "".join(html_fase1_card(f) for f in fase1_list)
    if not fase1_list:
        fase1_cards_html = '<p style="color:#667085;">Nenhuma moeda com acumulação detectada.</p>'

    return {
        "timestamp":   ts,
        "exchange":    exchange,
        "coin_count":  len(all_coins),
        "macro":       macro,
        "rsi_color":   rsi_color,
        "top_coins":   [s["base"] for s in top5],
        "html": {
            "macro_banner":          html_macro_banner(macro, rsi_color, len(all_coins)),
            "macro_hostile_block":   macro_hostile_block,
            "macro_hostile_v2_block": macro_hostile_v2_block,
            "fenix_cards":           fenix_cards_html,
            "fenix_v2_cards":        fenix_v2_cards_html,
            "encryptos_macro":        encryptos["macro_html"],
            "encryptos_cards":        encryptos["cards_html"],
            "encryptos_radar":        encryptos["radar_html"],
            "encryptos_risk":         encryptos["risk_html"],
            "veredito_cards":        veredito_cards_html,
            "fase1_cards":           fase1_cards_html,
        }
    }

# ── GENERATE HTML (para CLI) ──────────────────────────────────────────────────

def generate_html(data):
    """Gera HTML completo a partir dos dados (uso pelo CLI gerar_dashboard.py)."""
    r = process_data(data)
    ts       = r["timestamp"]
    exchange = r["exchange"]
    total    = r["coin_count"]
    macro    = r["macro"]
    h        = r["html"]

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>BANCADA PHOENIX — DASHBOARD UNIFICADO</title>
<style>{CSS}</style>
</head>
<body>
<div class="header">
    <div class="header-title">🦅 BANCADA PHOENIX — DASHBOARD UNIFICADO</div>
    <div class="header-meta">
        <span>📅 {ts}</span>
        <span>🪙 {total} moedas</span>
        <span>📡 {exchange}</span>
    </div>
</div>
<div class="container">

{h["macro_banner"]}

<div class="section-header">
    <div class="section-title" style="color:#ff9b4d;">⚡ MODO FÊNIX</div>
    <div class="section-line"></div>
    <span style="font-size:12px;color:#667085;white-space:nowrap;">Top 5 ao vivo · 4 critérios do método</span>
</div>
<div class="fenix-banner">
    <strong>Critérios:</strong>
    EXP BTC 1m &gt; 3 · Trades 1m crescendo · RSI 1m entre 50–70 · Range Level ≥ 3
    <br><span style="opacity:.75;font-size:11.5px;">Filtro: trades_1d &gt; 30k · 📌 Range usa 15m</span>
</div>
{h["macro_hostile_block"]}
<div class="fenix-grid">{h["fenix_cards"]}</div>

<div class="section-header">
    <div class="section-title" style="color:#00b4d8;">🔥 PHOENIX V2</div>
    <div class="section-line"></div>
    <span style="font-size:12px;color:#667085;white-space:nowrap;">Top 5 · filtros refinados Encryptos</span>
</div>
<div class="fv2-banner">
    <strong>Critérios V2:</strong>
    C1 EXP 15m ≥ 2 + EXP 1m ≥ 1 (⚡ bônus se EXP 5m ≥ 2) · C2 Trades 5m ≥ 150 · C3 RSI 15m ≥ 55 ou Alt &gt; BTC · C4 Range 30m+1h ≥ 3
    <br><span style="opacity:.75;font-size:11.5px;">Filtro: OI ≥ $5M · trades_1d ≥ 300k · score ≥ 3/4 · 🐊 Jacaré V2: OI↑ ≥1% + LSR↓ ≤-1 · Squeeze Real: LSR ≤ 1.0 · ⚡ BTC Reset: RSI 1h &lt; 35</span>
</div>
{h["macro_hostile_v2_block"]}
<div class="fv2-grid">{h["fenix_v2_cards"]}</div>

<div class="section-header">
    <div class="section-title" style="color:#c9a7ff;">IA ENCRYPTOS/PHOENIX</div>
    <div class="section-line"></div>
    <span style="font-size:12px;color:#667085;white-space:nowrap;">Setups A-D + risco</span>
</div>
<div class="fv2-banner">
    <strong>Metodo IA:</strong>
    Filtro OI &gt;= $10M + trades 1D &gt;= 150k + blacklist. Setups: Reset, Pre-Ignicao, Caca a Liquidez e Pullback.
</div>
{h["encryptos_macro"]}
<div class="fv2-grid">{h["encryptos_cards"]}</div>
{h["encryptos_radar"]}
{h["encryptos_risk"]}

<div class="section-header">
    <div class="section-title" style="color:#039855;">🎯 VEREDITOS DE ENTRADA</div>
    <div class="section-line"></div>
</div>
<div class="veredito-grid">{h["veredito_cards"]}</div>

<div class="section-header">
    <div class="section-title" style="color:#a371f7;">🚨 RADAR FASE 1 (PRÉ-EXPLOSÃO)</div>
    <div class="section-line"></div>
</div>
<p style="color:#667085;font-size:13px;margin-bottom:14px;">Setup ANTES da explosão — vigiar para entrada antecipada</p>
<div class="fase1-grid">{h["fase1_cards"]}</div>

</div>
</body>
</html>"""
