# -*- coding: utf-8 -*-
"""
Camada SQLite do painel PHOENIX.

Guarda CADA snapshot importado e, por moeda, TODOS os campos brutos do JSON
(coluna raw_json) + colunas indexadas para consulta rápida (score, setup, EXP,
OI, LSR, RSI...). Nada do JSON é descartado.

Objetivo: histórico das moedas do topo, comparação entre dias e estudo de
padrões que antecedem boas operações.
"""
import os
import json
import sqlite3
import datetime as dt

import gerar_painel as core

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phoenix.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT UNIQUE,          -- timestamp do scan (do JSON)
    exchange    TEXT,
    setup       TEXT,
    mode        TEXT,
    symbols     INTEGER,
    ingested_at TEXT,                 -- quando foi importado para o banco
    source      TEXT,                 -- nome do arquivo / origem
    btc_reset   INTEGER               -- 1 = BTC em reset/janela aberta no snapshot
);
CREATE TABLE IF NOT EXISTS metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    symbol          TEXT,
    rank            INTEGER,
    score           INTEGER,
    setup           TEXT,
    price           REAL,
    price_change_1d REAL,
    exp_1d          REAL,
    exp_4h          REAL,
    exp_1h          REAL,
    oi_trend        REAL,
    lsr             REAL,
    lsr_trend       REAL,
    rsi_4h          REAL,
    oi_usd          REAL,
    trades_min      REAL,
    range_4h        REAL,
    range_1d        REAL,
    trades_1d       REAL,              -- nº de trades no diário
    toi             REAL,              -- trades:1D por $1M de OI (intensidade SM)
    setup_score     INTEGER,           -- 0-7 critérios do Setup de Ouro atendidos
    setup_grade     TEXT,              -- 'SETUP DE OURO' | 'PARCIAL' | ''
    raw_json        TEXT               -- dict bruto completo da moeda
);
CREATE INDEX IF NOT EXISTS idx_metrics_snap ON metrics(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_metrics_sym  ON metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_metrics_rank ON metrics(snapshot_id, rank);
CREATE TABLE IF NOT EXISTS analises (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id   INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    created_at    TEXT,
    source        TEXT,                  -- origem (ex.: 'skill-chat')
    janela_aberta INTEGER,               -- 1/0 gate do BTC
    resumo        TEXT,                  -- leitura do BTC
    result_json   TEXT                   -- lista ranqueada completa (JSON)
);
CREATE INDEX IF NOT EXISTS idx_analises_snap ON analises(snapshot_id);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    _migrate()


def _migrate():
    """Adiciona colunas novas em bancos antigos e faz backfill a partir do raw_json."""
    with get_conn() as conn:
        mcols = {r["name"] for r in conn.execute("PRAGMA table_info(metrics)")}
        scols = {r["name"] for r in conn.execute("PRAGMA table_info(snapshots)")}

        if "btc_reset" not in scols:
            conn.execute("ALTER TABLE snapshots ADD COLUMN btc_reset INTEGER")

        added = []
        for col, typ in (("trades_1d", "REAL"), ("toi", "REAL"),
                         ("setup_score", "INTEGER"), ("setup_grade", "TEXT")):
            if col not in mcols:
                conn.execute(f"ALTER TABLE metrics ADD COLUMN {col} {typ}")
                added.append(col)

        if not added and "btc_reset" in scols:
            return

        # backfill por snapshot (precisa do BTC daquele snapshot para o gate macro)
        for snap in conn.execute("SELECT id FROM snapshots").fetchall():
            sid = snap["id"]
            rows = conn.execute(
                "SELECT id, symbol, raw_json FROM metrics WHERE snapshot_id = ?", (sid,)
            ).fetchall()
            data = {r["symbol"]: json.loads(r["raw_json"]) for r in rows}
            macro = core.btc_macro(data.get("BTCUSDT"))
            conn.execute("UPDATE snapshots SET btc_reset = ? WHERE id = ?",
                         (1 if macro["reset"] else 0, sid))
            for r in rows:
                e = data[r["symbol"]]
                chk = core.entry_checklist(e)
                grade, _, escore = core.setup_grade(chk, macro["safe"])
                conn.execute(
                    """UPDATE metrics SET trades_1d = ?, toi = ?, setup_score = ?, setup_grade = ?
                       WHERE id = ?""",
                    (_f(e, "trades:1D"), core.trades_oi(e), escore, grade, r["id"]),
                )


def _f(e, key):
    v = e.get(key)
    return v if isinstance(v, (int, float)) else None


def ingest(doc, source="upload", replace=True):
    """Importa um documento JSON (já carregado). Retorna (snapshot_id, n, status).

    status: 'inserted' | 'replaced' | 'skipped'
    """
    init_db()
    data = doc.get("data", {})
    ts = doc.get("timestamp", "")
    rows = core.build_rows(data)               # calcula score/setup/rank ordenado
    macro = core.btc_macro(data.get("BTCUSDT"))

    with get_conn() as conn:
        cur = conn.execute("SELECT id FROM snapshots WHERE timestamp = ?", (ts,))
        existing = cur.fetchone()
        if existing:
            if not replace:
                return existing["id"], 0, "skipped"
            conn.execute("DELETE FROM snapshots WHERE id = ?", (existing["id"],))
            status = "replaced"
        else:
            status = "inserted"

        cur = conn.execute(
            """INSERT INTO snapshots(timestamp, exchange, setup, mode, symbols, ingested_at, source, btc_reset)
               VALUES(?,?,?,?,?,?,?,?)""",
            (ts, doc.get("exchange"), doc.get("setup"), doc.get("mode"),
             doc.get("symbols", len(data)), dt.datetime.utcnow().isoformat() + "Z", source,
             1 if macro["reset"] else 0),
        )
        sid = cur.lastrowid

        payload = []
        for rank, r in enumerate(rows, 1):
            sym = r["symbol"]
            e = data[sym]
            payload.append((
                sid, sym, rank, r["score"], r["badge"],
                _f(e, "price"), _f(e, "price_change:1D"),
                _f(e, "exp_btc:1D"), _f(e, "exp_btc:4h"), _f(e, "exp_btc:1h"),
                _f(e, "oi_trend:5m"), _f(e, "lsr:5m"), _f(e, "lsr_trend:5m"),
                _f(e, "rsi:4h"), _f(e, "oi:5m"), _f(e, "trades_minute:5m"),
                _f(e, "range_level:4h"), _f(e, "range_level:1D"),
                _f(e, "trades:1D"), core.trades_oi(e),
                r.get("entry_score"), r.get("entry_grade"),
                json.dumps(e, ensure_ascii=False),
            ))
        conn.executemany(
            """INSERT INTO metrics(
                snapshot_id, symbol, rank, score, setup, price, price_change_1d,
                exp_1d, exp_4h, exp_1h, oi_trend, lsr, lsr_trend, rsi_4h, oi_usd,
                trades_min, range_4h, range_1d, trades_1d, toi, setup_score, setup_grade, raw_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            payload,
        )
    return sid, len(rows), status


def list_snapshots():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM snapshots ORDER BY timestamp DESC").fetchall()]


def latest_snapshot_id():
    with get_conn() as conn:
        r = conn.execute("SELECT id FROM snapshots ORDER BY timestamp DESC LIMIT 1").fetchone()
        return r["id"] if r else None


def get_snapshot(sid):
    """Retorna (meta_dict, data_dict) — data reconstruído do raw_json para render."""
    with get_conn() as conn:
        snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (sid,)).fetchone()
        if not snap:
            return None, None
        rows = conn.execute(
            "SELECT symbol, raw_json FROM metrics WHERE snapshot_id = ? ORDER BY rank", (sid,)
        ).fetchall()
    data = {r["symbol"]: json.loads(r["raw_json"]) for r in rows}
    meta = dict(snap)
    return meta, data


def symbol_history(symbol):
    """Série temporal de uma moeda em todos os snapshots (mais recente primeiro)."""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT s.timestamp, s.id AS snapshot_id, m.rank, m.score, m.setup,
                      m.price, m.price_change_1d, m.exp_1d, m.exp_4h, m.exp_1h,
                      m.oi_trend, m.lsr, m.lsr_trend, m.rsi_4h, m.oi_usd, m.trades_min,
                      m.trades_1d, m.toi, m.setup_score
               FROM metrics m JOIN snapshots s ON s.id = m.snapshot_id
               WHERE m.symbol = ?
               ORDER BY s.timestamp DESC""", (symbol,)).fetchall()]


def radar_acumulacao(top_n=30, limit=40):
    """Radar de intenção (TRADES 1D).

    Combina duas leituras do conceito Phoenix:
      - T/OI do snapshot mais recente (interesse desproporcional ao capital);
      - persistência: em quantos snapshots a moeda ficou no TOP N de T/OI
        (vários dias = acumulação em andamento, SM não sai do ativo).
    """
    init_db()
    with get_conn() as conn:
        latest = conn.execute(
            "SELECT id FROM snapshots ORDER BY timestamp DESC LIMIT 1").fetchone()
        if not latest:
            return []
        lid = latest["id"]
        # persistência: dias no TOP N de T/OI ao longo de todos os snapshots
        persist = {r["symbol"]: r["dias"] for r in conn.execute(
            """SELECT symbol, COUNT(*) AS dias FROM (
                   SELECT symbol,
                          RANK() OVER (PARTITION BY snapshot_id ORDER BY toi DESC) AS rk
                   FROM metrics WHERE toi IS NOT NULL
               ) WHERE rk <= ? GROUP BY symbol""", (top_n,)).fetchall()}
        total = conn.execute("SELECT COUNT(*) c FROM snapshots").fetchone()["c"]
        rows = conn.execute(
            """SELECT symbol, toi, oi_usd, trades_1d, rank, score, setup, price_change_1d
               FROM metrics WHERE snapshot_id = ? AND toi IS NOT NULL
               ORDER BY toi DESC LIMIT ?""", (lid, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["dias_top"] = persist.get(r["symbol"], 0)
        d["total_snaps"] = total
        out.append(d)
    return out


def top_appearances(top_n=10, limit=40):
    """Moedas que mais apareceram no TOP N ao longo do histórico (recorrência)."""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT symbol,
                      COUNT(*)            AS aparicoes,
                      MIN(rank)           AS melhor_rank,
                      ROUND(AVG(rank),1)  AS rank_medio,
                      MAX(score)          AS score_max,
                      ROUND(AVG(score),1) AS score_medio
               FROM metrics
               WHERE rank <= ?
               GROUP BY symbol
               ORDER BY aparicoes DESC, score_medio DESC
               LIMIT ?""", (top_n, limit)).fetchall()]


def setup_radar(limit=40):
    """Ranking de entrada (Setup de Ouro) do último snapshot + persistência.

    Retorna (macro, rows). macro = estado do BTC no snapshot. Cada row traz os
    7 critérios recomputados do raw_json, trap, e dias_ouro (em quantos snapshots
    a moeda já marcou SETUP DE OURO).
    """
    init_db()
    with get_conn() as conn:
        latest = conn.execute(
            "SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT 1").fetchone()
        if not latest:
            return None, []
        lid = latest["id"]
        ouro = {r["symbol"]: r["dias"] for r in conn.execute(
            """SELECT symbol, COUNT(*) AS dias FROM metrics
               WHERE setup_grade = 'SETUP DE OURO' GROUP BY symbol""").fetchall()}
        rows = conn.execute(
            """SELECT symbol, rank, score, setup_score, setup_grade, raw_json
               FROM metrics WHERE snapshot_id = ?
               ORDER BY setup_score DESC, score DESC LIMIT ?""", (lid, limit)).fetchall()
    macro = core.btc_macro(json.loads(
        next((r["raw_json"] for r in rows if r["symbol"] == "BTCUSDT"), "null")) or None)
    # se BTC não está entre os top do ranking, busca direto
    if macro["state"] == "—":
        with get_conn() as conn:
            b = conn.execute(
                "SELECT raw_json FROM metrics WHERE snapshot_id=? AND symbol='BTCUSDT'",
                (lid,)).fetchone()
            if b:
                macro = core.btc_macro(json.loads(b["raw_json"]))
    out = []
    for r in rows:
        if r["symbol"] == "BTCUSDT":
            continue
        e = json.loads(r["raw_json"])
        chk = core.entry_checklist(e)
        out.append({
            "symbol": r["symbol"], "rank": r["rank"], "score": r["score"],
            "setup_score": r["setup_score"], "setup_grade": r["setup_grade"],
            "chk": chk, "trap": core.is_trap(e),
            "price_change_1d": _f(e, "price_change:1D"),
            "lsr": _f(e, "lsr:5m"), "oi_trend": _f(e, "oi_trend:5m"),
            "trades_min": _f(e, "trades_minute:5m"), "fr": _f(e, "fr"),
            "dias_ouro": ouro.get(r["symbol"], 0),
        })
    return macro, out


def save_analise(snapshot_id, data, source="skill-chat"):
    """Salva uma análise (lista ranqueada) da metodologia para um snapshot."""
    init_db()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO analises(snapshot_id, created_at, source, janela_aberta, resumo, result_json)
               VALUES(?,?,?,?,?,?)""",
            (snapshot_id, dt.datetime.utcnow().isoformat() + "Z", source,
             1 if data.get("janela_aberta") else 0, data.get("resumo_btc", ""),
             json.dumps(data, ensure_ascii=False)),
        )


def list_analises():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT a.id, a.snapshot_id, a.created_at, a.source, a.janela_aberta, a.resumo,
                      s.timestamp AS snap_ts
               FROM analises a JOIN snapshots s ON s.id = a.snapshot_id
               ORDER BY a.created_at DESC""").fetchall()]


def get_analise(aid):
    with get_conn() as conn:
        r = conn.execute(
            "SELECT a.*, s.timestamp AS snap_ts FROM analises a "
            "JOIN snapshots s ON s.id = a.snapshot_id WHERE a.id = ?", (aid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["result"] = json.loads(d.pop("result_json"))
    return d


def stats():
    with get_conn() as conn:
        ns = conn.execute("SELECT COUNT(*) c FROM snapshots").fetchone()["c"]
        nm = conn.execute("SELECT COUNT(*) c FROM metrics").fetchone()["c"]
        return {"snapshots": ns, "metrics": nm}
