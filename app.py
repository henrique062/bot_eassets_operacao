# -*- coding: utf-8 -*-
"""
App Flask do painel PHOENIX MEMBROS.

    python app.py            # sobe em http://127.0.0.1:5000

Fluxo:
  - Botão "＋ IMPORTAR JSON" abre modal -> cola o JSON (ou envia arquivo) ->
    "Processar" -> salva snapshot completo no SQLite e abre o painel daquele dia.
  - Seletor de snapshots para revisitar dias anteriores.
  - Clique numa moeda -> histórico dela em todos os snapshots.
  - "Topo recorrente" -> moedas que mais apareceram no TOP 10 (estudo de padrões).
"""
import json
import datetime as dt

from flask import Flask, request, redirect, url_for, flash, render_template_string, abort, get_flashed_messages

import gerar_painel as core
import db

app = Flask(__name__)
app.secret_key = "phoenix-local"


@app.template_filter("brt")
def _brt_filter(ts):
    """Filtro Jinja: timestamp UTC -> string GMT-3 (BRT)."""
    return core.to_brt(ts)

# ---------------------------------------------------------------------------
# Componentes de navegação (injetados no topo do painel via core.render_html)
# ---------------------------------------------------------------------------

def build_nav(current_sid=None):
    snaps = db.list_snapshots()
    opts = []
    for s in snaps:
        sel = " selected" if s["id"] == current_sid else ""
        label = core.to_brt(s["timestamp"])
        opts.append(f'<option value="{s["id"]}"{sel}>{label} · {s["symbols"]} ativos</option>')
    selector = ""
    if opts:
        selector = (
            '<select onchange="if(this.value)location.href=\'/snapshot/\'+this.value">'
            + "".join(opts) + "</select>"
        )
    flashes = "".join(f'<div class="flash">{m}</div>' for m in get_flashed_messages())
    return f"""
  {flashes}
  <div class="nav">
    <button class="navbtn primary" onclick="document.getElementById('imp').classList.add('open')">＋ IMPORTAR JSON</button>
    {selector}
    <a href="/setup">✓ SETUP DE OURO</a>
    <a href="/radar">📡 RADAR ACUMULAÇÃO</a>
    <a href="/analises">🧠 ANÁLISES IA</a>
    <a href="/topo">★ TOPO RECORRENTE</a>
    <a href="/snapshots">🗂 SNAPSHOTS</a>
    <span class="spacer"></span>
    <a href="/">⟳ ÚLTIMO</a>
  </div>

  <div class="modal" id="imp">
    <div class="modal-box">
      <h3>IMPORTAR SNAPSHOT</h3>
      <p>Cole o conteúdo do JSON (eassets-panel) ou selecione o arquivo. Ao processar,
         todos os dados são salvos no banco para histórico e comparação.</p>
      <form method="post" action="/ingest" enctype="multipart/form-data" onsubmit="return prep()">
        <textarea id="jtext" name="json_text" placeholder='{{ "timestamp": "...", "data": {{ ... }} }}'></textarea>
        <input type="file" id="jfile" name="json_file" accept=".json,application/json">
        <div class="modal-actions">
          <button type="button" onclick="document.getElementById('imp').classList.remove('open')">Cancelar</button>
          <button type="submit" class="go">PROCESSAR</button>
        </div>
      </form>
    </div>
  </div>
  <script>
    function prep() {{
      var f = document.getElementById('jfile');
      // se há arquivo, deixa o multipart cuidar; senão exige texto
      if ((!f.files || !f.files.length) && !document.getElementById('jtext').value.trim()) {{
        alert('Cole o JSON ou selecione um arquivo.');
        return false;
      }}
      return true;
    }}
  </script>"""


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    sid = db.latest_snapshot_id()
    if not sid:
        return render_template_string(EMPTY_PAGE, nav=build_nav())
    return view_snapshot(sid)


@app.route("/snapshot/<int:sid>")
def snapshot(sid):
    return view_snapshot(sid)


def view_snapshot(sid):
    meta, data = db.get_snapshot(sid)
    if not meta:
        abort(404)
    rows = core.build_rows(data)
    btc = data.get("BTCUSDT")
    return core.render_html(meta, rows, btc=btc, nav=build_nav(sid), asset_link=True)


@app.route("/ingest", methods=["POST"])
def ingest():
    raw = ""
    source = "colado"
    f = request.files.get("json_file")
    if f and f.filename:
        raw = f.read().decode("utf-8", errors="replace")
        source = f.filename
    elif request.form.get("json_text", "").strip():
        raw = request.form["json_text"]
    if not raw.strip():
        flash("Nenhum JSON recebido.")
        return redirect(url_for("index"))
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        flash(f"JSON inválido: {exc}")
        return redirect(url_for("index"))
    if "data" not in doc or not isinstance(doc["data"], dict):
        flash("JSON sem a chave 'data' com as moedas.")
        return redirect(url_for("index"))
    sid, n, status = db.ingest(doc, source=source)
    msg = {"inserted": "importado", "replaced": "atualizado", "skipped": "já existia"}[status]
    flash(f"Snapshot {msg}: {n} moedas salvas.")
    return redirect(url_for("snapshot", sid=sid))


@app.route("/historico/<symbol>")
def historico(symbol):
    hist = db.symbol_history(symbol)
    if not hist:
        abort(404)
    asset = symbol.replace("USDT", "")
    return render_template_string(
        HISTORY_PAGE, nav=build_nav(), asset=asset, symbol=symbol,
        hist=hist, svg=_sparkline(hist), fnum=core.fmt_num, fprice=core.fmt_price,
        fusd=core.fmt_usd, cls_pn=core.cls_pn, fcomp=core.fmt_compact, toicls=core.toi_cls,
    )


@app.route("/setup")
def setup():
    macro, rows = db.setup_radar(limit=60)
    return render_template_string(
        SETUP_PAGE, nav=build_nav(), macro=macro, rows=rows,
        fnum=core.fmt_num, fusd=core.fmt_usd, cls_pn=core.cls_pn,
    )


@app.route("/radar")
def radar():
    rows = db.radar_acumulacao(top_n=30, limit=50)
    return render_template_string(
        RADAR_PAGE, nav=build_nav(), rows=rows,
        fnum=core.fmt_num, fusd=core.fmt_usd, fcomp=core.fmt_compact,
        cls_pn=core.cls_pn, toicls=core.toi_cls,
    )


@app.route("/topo")
def topo():
    rows = db.top_appearances(top_n=10, limit=50)
    return render_template_string(TOPO_PAGE, nav=build_nav(), rows=rows)


@app.route("/analises")
def analises():
    items = db.list_analises()
    return render_template_string(ANALISES_PAGE, nav=build_nav(), items=items)


@app.route("/analise/<int:aid>")
def analise(aid):
    a = db.get_analise(aid)
    if not a:
        abort(404)
    return render_template_string(ANALISE_PAGE, nav=build_nav(), a=a, R=a["result"])


@app.route("/snapshots")
def snapshots():
    snaps = db.list_snapshots()
    return render_template_string(SNAPS_PAGE, nav=build_nav(), snaps=snaps, st=db.stats())


def _sparkline(hist, w=560, h=120):
    """SVG simples de score (0-100) ao longo do tempo (cronológico)."""
    pts = [h["score"] for h in reversed(hist) if h["score"] is not None]
    if len(pts) < 2:
        return ""
    n = len(pts)
    dx = w / (n - 1)
    coords = [f"{i*dx:.1f},{h - (v/100.0)*h:.1f}" for i, v in enumerate(pts)]
    poly = " ".join(coords)
    dots = "".join(f'<circle cx="{i*dx:.1f}" cy="{h-(v/100.0)*h:.1f}" r="2.5" fill="#ff4b3e"/>'
                   for i, v in enumerate(pts))
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" preserveAspectRatio="none">'
            f'<polyline points="{poly}" fill="none" stroke="#ff4b3e" stroke-width="2"/>'
            f'{dots}</svg>')


# ---------------------------------------------------------------------------
# Templates das páginas secundárias (tema escuro consistente)
# ---------------------------------------------------------------------------

BASE_CSS = """
  :root{--bg:#07090c;--panel:#0d1117;--line:#1c242e;--txt:#c9d4df;--muted:#5e6b78;
    --pos:#27d796;--neg:#ff5470;--gold:#e8b84b;--cyan:#46c9e0;--accent:#ff4b3e;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--txt);font-family:"Segoe UI",Roboto,Arial,sans-serif;font-size:13px;}
  .wrap{max-width:1100px;margin:0 auto;padding:16px;}
  h1{font-size:20px;letter-spacing:2px;margin:6px 0 2px;}
  h1 b{color:var(--accent);}
  .sub{color:var(--muted);font-size:11px;margin-bottom:14px;}
  .nav{display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap;}
  .nav a,.nav button.navbtn{background:#11161d;color:var(--txt);border:1px solid var(--line);
    border-radius:6px;padding:7px 14px;font-size:11px;cursor:pointer;letter-spacing:.5px;
    font-weight:600;text-decoration:none;transition:.15s;}
  .nav a:hover,.nav button.navbtn:hover{border-color:var(--accent);color:#fff;}
  .nav .primary{background:var(--accent);border-color:var(--accent);color:#fff;}
  .nav select{background:#11161d;color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:7px 10px;font-size:11px;}
  .nav .spacer{margin-left:auto;}
  table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;}
  th{font-size:9px;letter-spacing:.5px;color:var(--muted);text-transform:uppercase;text-align:right;padding:10px 8px;border-bottom:1px solid var(--line);}
  th.l{text-align:left;}
  td{padding:9px 8px;text-align:right;border-bottom:1px solid #131922;font-variant-numeric:tabular-nums;white-space:nowrap;}
  td.l{text-align:left;}
  tr:hover{background:#0f151d;}
  a.lnk{color:#fff;text-decoration:none;border-bottom:1px dotted #3a4654;}
  a.lnk:hover{color:var(--accent);}
  .pos{color:var(--pos);}.neg{color:var(--neg);}.muted{color:var(--muted);}.rsi{color:var(--gold);}.oi{color:var(--cyan);}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:14px;}
  .flash{background:rgba(255,75,62,.12);border:1px solid rgba(255,75,62,.4);color:#ffb4ac;
    padding:8px 12px;border-radius:6px;font-size:12px;margin-bottom:12px;}
  /* modal (reaproveitado) */
  .modal{position:fixed;inset:0;background:rgba(0,0,0,.7);display:none;align-items:center;justify-content:center;z-index:50;}
  .modal.open{display:flex;}
  .modal-box{background:var(--panel);border:1px solid var(--line);border-radius:10px;width:min(640px,92vw);padding:20px;}
  .modal-box h3{margin:0 0 4px;font-size:15px;color:#fff;}
  .modal-box p{margin:0 0 12px;font-size:11px;color:var(--muted);}
  .modal-box textarea{width:100%;height:180px;background:#0a0e13;color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:10px;font-family:monospace;font-size:11px;}
  .modal-box input[type=file]{font-size:11px;color:var(--muted);margin:10px 0;}
  .modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:12px;}
  .modal-actions button{padding:8px 16px;border-radius:6px;font-size:12px;cursor:pointer;border:1px solid var(--line);background:#11161d;color:var(--txt);font-weight:600;}
  .modal-actions .go{background:var(--accent);border-color:var(--accent);color:#fff;}
"""

FLASH = """{% with msgs = get_flashed_messages() %}{% if msgs %}{% for m in msgs %}<div class="flash">{{ m }}</div>{% endfor %}{% endif %}{% endwith %}"""

EMPTY_PAGE = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PHOENIX MEMBROS</title>
<style>""" + BASE_CSS + """</style></head><body><div class="wrap">
<h1>PHOENIX <b>MEMBROS</b></h1><div class="sub">Metodologia Encryptos · banco local SQLite</div>
""" + FLASH + """{{ nav|safe }}
<div class="panel"><b>Nenhum snapshot ainda.</b><br><br>
Clique em <b>＋ IMPORTAR JSON</b>, cole um arquivo <code>eassets-panel-*.json</code> e processe.
O painel completo (score, setup, top 10, cards e BTC) aparece após salvar.</div>
</div></body></html>"""

HISTORY_PAGE = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ asset }} · Histórico</title>
<style>""" + BASE_CSS + """</style></head><body><div class="wrap">
<h1>{{ asset }} <b>· HISTÓRICO</b></h1>
<div class="sub">{{ symbol }} · {{ hist|length }} registros · score ao longo do tempo</div>
""" + FLASH + """{{ nav|safe }}
{% if svg %}<div class="panel"><div class="sub">SCORE (cronológico, 0-100)</div>{{ svg|safe }}</div>{% endif %}
<table>
<thead><tr><th class="l">DATA</th><th>RANK</th><th>SCORE</th><th class="l">SETUP</th><th>PREÇO</th><th>1D %</th>
<th>T/OI</th><th>EXP 1D</th><th>EXP 4H</th><th>EXP 1H</th><th>OI TREND</th><th>LSR</th><th>LSR TREND</th><th>RSI 4H</th><th>OI USD</th></tr></thead>
<tbody>
{% for h in hist %}
<tr>
<td class="l"><a class="lnk" href="/snapshot/{{ h.snapshot_id }}">{{ h.timestamp | brt }}</a></td>
<td>{{ h.rank }}</td><td><b>{{ h.score }}</b></td><td class="l muted">{{ h.setup }}</td>
<td>{{ fprice(h.price) }}</td>
<td class="{{ cls_pn(h.price_change_1d) }}">{{ fnum(h.price_change_1d,2,True) }}%</td>
<td class="{{ toicls(h.toi) }}">{{ fcomp(h.toi) }}</td>
<td class="{{ cls_pn(h.exp_1d) }}">{{ fnum(h.exp_1d,2,True) }}</td>
<td class="{{ cls_pn(h.exp_4h) }}">{{ fnum(h.exp_4h,2,True) }}</td>
<td class="{{ cls_pn(h.exp_1h) }}">{{ fnum(h.exp_1h,2,True) }}</td>
<td class="{{ cls_pn(h.oi_trend) }}">{{ fnum(h.oi_trend,2,True) }}</td>
<td class="muted">{{ fnum(h.lsr,3) }}</td>
<td class="{{ cls_pn(h.lsr_trend) }}">{{ fnum(h.lsr_trend,2,True) }}</td>
<td class="rsi">{{ fnum(h.rsi_4h,2) }}</td>
<td class="oi">{{ fusd(h.oi_usd) }}</td>
</tr>
{% endfor %}
</tbody></table>
</div></body></html>"""

TOPO_PAGE = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Topo Recorrente</title>
<style>""" + BASE_CSS + """</style></head><body><div class="wrap">
<h1>TOPO <b>RECORRENTE</b></h1>
<div class="sub">Moedas que mais apareceram no TOP 10 — recorrência indica força estrutural persistente</div>
""" + FLASH + """{{ nav|safe }}
<table>
<thead><tr><th class="l">#</th><th class="l">ATIVO</th><th>APARIÇÕES NO TOP 10</th><th>MELHOR RANK</th>
<th>RANK MÉDIO</th><th>SCORE MÁX</th><th>SCORE MÉDIO</th></tr></thead>
<tbody>
{% for r in rows %}
<tr><td class="muted">{{ loop.index }}</td>
<td class="l"><a class="lnk" href="/historico/{{ r.symbol }}">{{ r.symbol.replace('USDT','') }}</a></td>
<td><b>{{ r.aparicoes }}</b></td><td>{{ r.melhor_rank }}</td><td>{{ r.rank_medio }}</td>
<td>{{ r.score_max }}</td><td>{{ r.score_medio }}</td></tr>
{% endfor %}
</tbody></table>
{% if not rows %}<div class="panel muted">Sem dados ainda. Importe snapshots primeiro.</div>{% endif %}
</div></body></html>"""

SETUP_PAGE = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Setup de Ouro</title>
<style>""" + BASE_CSS + """
  .macro{display:flex;align-items:center;gap:14px;padding:12px 16px;border-radius:8px;margin-bottom:14px;flex-wrap:wrap;font-size:13px;}
  .macro.ok{background:rgba(39,215,150,.10);border:1px solid rgba(39,215,150,.4);}
  .macro.warn{background:rgba(232,184,75,.10);border:1px solid rgba(232,184,75,.4);}
  .macro .st{font-weight:800;letter-spacing:1px;}
  .macro.ok .st{color:var(--pos);} .macro.warn .st{color:var(--gold);}
  .macro .rsi{color:var(--muted);} .macro .msg{color:var(--txt);}
  .y{color:var(--pos);font-weight:700;} .x{color:#3a4654;}
  .grade{font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;}
  .g-ouro{background:rgba(39,215,150,.14);color:var(--pos);border:1px solid rgba(39,215,150,.45);}
  .g-parcial{background:rgba(232,184,75,.12);color:var(--gold);border:1px solid rgba(232,184,75,.4);}
  .g-none{color:var(--muted);}
  .trap{background:rgba(255,84,112,.14);color:var(--neg);border:1px solid rgba(255,84,112,.4);font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;}
  th.c,td.c{text-align:center;}
  .tag{display:inline-block;font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;background:rgba(39,215,150,.14);color:var(--pos);border:1px solid rgba(39,215,150,.4);}
  .note{font-size:11px;color:var(--muted);line-height:1.6;}
</style></head><body><div class="wrap">
<h1>SETUP <b>DE OURO</b></h1>
<div class="sub">Checklist de entrada Encryptos · confluência força + financiamento + acumulação, com gate do BTC</div>
""" + FLASH + """{{ nav|safe }}
{% if macro %}
<div class="macro {{ 'ok' if macro.safe else 'warn' }}">
  <span class="st">BTC {{ macro.state }}</span>
  <span class="rsi">RSI 30m {{ fnum(macro.rsi_30m,1) }} · 1h {{ fnum(macro.rsi_1h,1) }} · 5m {{ fnum(macro.rsi_5m,1) }}</span>
  <span class="msg">{{ 'Janela ABERTA — buscar Setup de Ouro' if macro.safe else 'Sem reset — diretiva: NEUTRALIDADE (aguardar)' }}</span>
</div>
{% endif %}
<div class="panel note">
<b>Critérios (★ = núcleo):</b>
<b class="y">EXP★</b> força relativa vs BTC verde em 5m/15m/1h ·
<b class="y">TPM★</b> trades acelerando (≥800 ou salto relativo) ·
<b class="y">LSR</b> &lt;1 ou caindo (shorts presos) ·
<b class="y">OI</b> subindo (dinheiro novo) ·
<b class="y">RSI</b> quente sem exaustão (1h≥50, 4h&lt;70) ·
<b class="y">ACUM</b> range comprimido ·
<b class="y">FUND</b> funding negativo.
Setup de Ouro = BTC em janela + EXP + TPM + ≥5/7.
</div>
<table>
<thead><tr><th class="l">#</th><th class="l">ATIVO</th><th class="l">GRAU</th><th>✓/7</th><th>DIAS OURO</th>
<th class="c">EXP</th><th class="c">TPM</th><th class="c">LSR</th><th class="c">OI</th><th class="c">RSI</th><th class="c">ACUM</th><th class="c">FUND</th>
<th>RANK</th><th>SCORE</th><th>1D %</th><th>LSR</th><th>OI TR</th></tr></thead>
<tbody>
{% for r in rows %}
<tr>
<td class="muted">{{ loop.index }}</td>
<td class="l"><a class="lnk" href="/historico/{{ r.symbol }}">{{ r.symbol.replace('USDT','') }}</a>{% if r.trap %} <span class="trap">ARMADILHA</span>{% endif %}</td>
<td class="l">{% if r.setup_grade %}<span class="grade {{ 'g-ouro' if r.setup_grade=='SETUP DE OURO' else 'g-parcial' }}">{{ r.setup_grade }}</span>{% else %}<span class="muted">—</span>{% endif %}</td>
<td><b>{{ r.setup_score }}/7</b></td>
<td>{% if r.dias_ouro > 0 %}<span class="tag">{{ r.dias_ouro }}</span>{% else %}<span class="muted">0</span>{% endif %}</td>
<td class="c">{{ '<span class=y>✓</span>'|safe if r.chk.exp_pos else '<span class=x>·</span>'|safe }}</td>
<td class="c">{{ '<span class=y>✓</span>'|safe if r.chk.tpm_hot else '<span class=x>·</span>'|safe }}</td>
<td class="c">{{ '<span class=y>✓</span>'|safe if r.chk.lsr_fuel else '<span class=x>·</span>'|safe }}</td>
<td class="c">{{ '<span class=y>✓</span>'|safe if r.chk.oi_in else '<span class=x>·</span>'|safe }}</td>
<td class="c">{{ '<span class=y>✓</span>'|safe if r.chk.rsi_runway else '<span class=x>·</span>'|safe }}</td>
<td class="c">{{ '<span class=y>✓</span>'|safe if r.chk.accumulation else '<span class=x>·</span>'|safe }}</td>
<td class="c">{{ '<span class=y>✓</span>'|safe if r.chk.funding_neg else '<span class=x>·</span>'|safe }}</td>
<td class="muted">{{ r.rank }}</td><td><b>{{ r.score }}</b></td>
<td class="{{ cls_pn(r.price_change_1d) }}">{{ fnum(r.price_change_1d,2,True) }}%</td>
<td class="muted">{{ fnum(r.lsr,3) }}</td>
<td class="{{ cls_pn(r.oi_trend) }}">{{ fnum(r.oi_trend,2,True) }}</td>
</tr>
{% endfor %}
</tbody></table>
{% if not rows %}<div class="panel muted">Sem dados. Importe snapshots primeiro.</div>{% endif %}
</div></body></html>"""

RADAR_PAGE = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Radar de Acumulação</title>
<style>""" + BASE_CSS + """
  .toi-hi{color:#c77dff;font-weight:700;} .toi-mid{color:#9d8bd8;}
  .tag{display:inline-block;font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;
    background:rgba(199,125,255,.14);color:#c77dff;border:1px solid rgba(199,125,255,.4);}
  .note{font-size:11px;color:var(--muted);line-height:1.6;}
</style></head><body><div class="wrap">
<h1>RADAR <b>DE ACUMULAÇÃO</b></h1>
<div class="sub">TRADES 1D ÷ OI = intensidade de robôs/SM por capital · radar de intenção (antes do preço explodir)</div>
""" + FLASH + """{{ nav|safe }}
<div class="panel note">
<b>Como ler:</b> <span class="toi-hi">T/OI alto</span> = moeda com OI baixo recebendo trades demais → SM trabalhando o ativo de forma focada, algo sendo preparado.
<b>DIAS NO TOP</b> = em quantos snapshots a moeda ficou entre as 30 maiores em T/OI. Persistência (vários dias) = acumulação em andamento — quando o padrão quebra pra cima, vem o movimento maior.
</div>
<table>
<thead><tr><th class="l">#</th><th class="l">ATIVO</th><th>T/OI</th><th>OI USD</th><th>TRADES 1D</th>
<th>DIAS NO TOP</th><th>RANK PAINEL</th><th>SCORE</th><th class="l">SETUP</th><th>1D %</th></tr></thead>
<tbody>
{% for r in rows %}
<tr><td class="muted">{{ loop.index }}</td>
<td class="l"><a class="lnk" href="/historico/{{ r.symbol }}">{{ r.symbol.replace('USDT','') }}</a></td>
<td class="{{ toicls(r.toi) }}">{{ fcomp(r.toi) }}</td>
<td class="oi">{{ fusd(r.oi_usd) }}</td>
<td class="muted">{{ fcomp(r.trades_1d) }}</td>
<td>{% if r.dias_top > 1 %}<span class="tag">{{ r.dias_top }}/{{ r.total_snaps }} dias</span>{% else %}<span class="muted">{{ r.dias_top }}/{{ r.total_snaps }}</span>{% endif %}</td>
<td class="muted">{{ r.rank }}</td><td><b>{{ r.score }}</b></td>
<td class="l muted">{{ r.setup }}</td>
<td class="{{ cls_pn(r.price_change_1d) }}">{{ fnum(r.price_change_1d,2,True) }}%</td></tr>
{% endfor %}
</tbody></table>
{% if not rows %}<div class="panel muted">Sem dados ainda. Importe snapshots primeiro.</div>{% endif %}
</div></body></html>"""

VD_CSS = """
  .vd{font-size:9px;font-weight:800;padding:3px 8px;border-radius:4px;letter-spacing:.5px;}
  .vd-COMPRAR{background:rgba(39,215,150,.16);color:var(--pos);border:1px solid rgba(39,215,150,.5);}
  .vd-OBSERVAR{background:rgba(232,184,75,.14);color:var(--gold);border:1px solid rgba(232,184,75,.45);}
  .vd-EVITAR{background:rgba(255,84,112,.14);color:var(--neg);border:1px solid rgba(255,84,112,.45);}
  .jan{font-weight:700;font-size:10px;padding:2px 7px;border-radius:4px;}
  .jan.ok{background:rgba(39,215,150,.14);color:var(--pos);border:1px solid rgba(39,215,150,.4);}
  .jan.no{background:rgba(232,184,75,.12);color:var(--gold);border:1px solid rgba(232,184,75,.4);}
  .razao{color:#8b97a4;font-size:11px;line-height:1.5;white-space:normal;}
"""

ANALISES_PAGE = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Análises IA</title>
<style>""" + BASE_CSS + VD_CSS + """</style></head><body><div class="wrap">
<h1>ANÁLISES <b>SALVAS</b></h1>
<div class="sub">Análises da metodologia Encryptos feitas no chat e gravadas no banco</div>
""" + FLASH + """{{ nav|safe }}
<table>
<thead><tr><th class="l">QUANDO</th><th class="l">SNAPSHOT (SCAN)</th><th class="l">JANELA</th>
<th class="l">RESUMO BTC</th><th class="l">ORIGEM</th></tr></thead>
<tbody>
{% for it in items %}
<tr>
<td class="l"><a class="lnk" href="/analise/{{ it.id }}">{{ it.created_at | brt }}</a></td>
<td class="l muted">{{ it.snap_ts | brt }}</td>
<td class="l"><span class="jan {{ 'ok' if it.janela_aberta else 'no' }}">{{ 'ABERTA' if it.janela_aberta else 'FECHADA' }}</span></td>
<td class="l muted" style="white-space:normal;max-width:520px">{{ it.resumo[:140] }}</td>
<td class="l muted">{{ it.source }}</td>
</tr>
{% endfor %}
</tbody></table>
{% if not items %}<div class="panel muted">Nenhuma análise salva. Use a skill <b>analise-encryptos</b> no chat e ela grava aqui via <code>salvar_analise.py</code>.</div>{% endif %}
</div></body></html>"""

ANALISE_PAGE = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Análise IA</title>
<style>""" + BASE_CSS + VD_CSS + """
  .resumo{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:14px;}
</style></head><body><div class="wrap">
<h1>ANÁLISE <b>IA</b></h1>
<div class="sub">Feita em {{ a.created_at | brt }} · scan {{ a.snap_ts | brt }} · origem {{ a.source }}</div>
""" + FLASH + """{{ nav|safe }}
<div class="resumo">
  <span class="jan {{ 'ok' if a.janela_aberta else 'no' }}">{{ 'JANELA ABERTA' if a.janela_aberta else 'JANELA FECHADA' }}</span>
  <span style="margin-left:10px">{{ R.resumo_btc }}</span>
</div>
<table>
<thead><tr><th class="l">#</th><th class="l">ATIVO</th><th class="l">VEREDITO</th><th>CONF</th>
<th class="l">FASE</th><th class="l">RAZÃO</th></tr></thead>
<tbody>
{% for x in R.ativos %}
<tr>
<td class="muted">{{ loop.index }}</td>
<td class="l"><a class="lnk" href="/historico/{{ x.symbol }}">{{ x.symbol.replace('USDT','') }}</a></td>
<td class="l"><span class="vd vd-{{ x.veredito }}">{{ x.veredito }}</span></td>
<td>{{ x.confianca }}</td>
<td class="l muted">{{ x.fase }}</td>
<td class="l razao">{{ x.razao }}</td>
</tr>
{% endfor %}
</tbody></table>
</div></body></html>"""

SNAPS_PAGE = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Snapshots</title>
<style>""" + BASE_CSS + """</style></head><body><div class="wrap">
<h1>SNAPSHOTS <b>SALVOS</b></h1>
<div class="sub">{{ st.snapshots }} snapshots · {{ st.metrics }} linhas de métricas no banco</div>
""" + FLASH + """{{ nav|safe }}
<table>
<thead><tr><th class="l">DATA DO SCAN</th><th>ATIVOS</th><th class="l">SETUP</th><th class="l">EXCHANGE</th>
<th class="l">IMPORTADO EM</th><th class="l">ORIGEM</th></tr></thead>
<tbody>
{% for s in snaps %}
<tr><td class="l"><a class="lnk" href="/snapshot/{{ s.id }}">{{ s.timestamp | brt }}</a></td>
<td>{{ s.symbols }}</td><td class="l muted">{{ s.setup }}</td><td class="l muted">{{ s.exchange }}</td>
<td class="l muted">{{ s.ingested_at | brt }}</td>
<td class="l muted">{{ s.source }}</td></tr>
{% endfor %}
</tbody></table>
{% if not snaps %}<div class="panel muted">Nenhum snapshot. Use ＋ IMPORTAR JSON.</div>{% endif %}
</div></body></html>"""


if __name__ == "__main__":
    db.init_db()
    print("PHOENIX painel em http://127.0.0.1:5000  (Ctrl+C para parar)")
    app.run(host="127.0.0.1", port=5000, debug=False)
