#!/usr/bin/env python3
"""
BANCADA PHOENIX — Web App
Flask + SQLite. Acesse: http://localhost:5050
"""

import json
import logging
import os
import sqlite3
import threading
import time

from flask import Flask, jsonify, render_template, request

import binance_feed
from eassets_scraper import EassetsScrapeError, scrape_eassets_json
from engine import process_data

log = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(__file__)
app = Flask(__name__)
_services_started = False
_services_lock = threading.Lock()


def load_dotenv(path=None):
    path = path or os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_dotenv()

DATA_DIR = os.getenv("DATA_DIR")
DB = os.getenv(
    "DASHBOARD_DB",
    os.path.join(DATA_DIR, "dashboard.db") if DATA_DIR else os.path.join(BASE_DIR, "dashboard.db"),
)
PORT = int(os.getenv("PORT", "5050"))
AUTO_RECALC_INTERVAL = 60  # segundos
EASSETS_INTERVAL = int(os.getenv("EASSETS_INTERVAL_SECONDS", "1800"))
EASSETS_AUTO_ENABLED = os.getenv("EASSETS_AUTO_ENABLED", "1").lower() not in {"0", "false", "no"}
EASSETS_HEADLESS = os.getenv("EASSETS_HEADLESS", "1").lower() not in {"0", "false", "no"}
EASSETS_TIMEOUT_MS = int(os.getenv("EASSETS_TIMEOUT_MS", "120000"))

_eassets_lock = threading.Lock()
_eassets_state = {
    "running": False,
    "last_started_at": None,
    "last_finished_at": None,
    "last_ok": None,
    "last_error": None,
    "last_snapshot_id": None,
    "last_coin_count": None,
}


def get_db():
    db_dir = os.path.dirname(DB)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            data_ts      TEXT,
            exchange     TEXT,
            coin_count   INTEGER,
            macro        TEXT,
            raw_json     TEXT    NOT NULL,
            results_json TEXT    NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auto_snapshots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            base_snap_id INTEGER NOT NULL,
            macro        TEXT,
            coin_count   INTEGER,
            top_coins    TEXT,
            results_json TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── AUTO RECÁLCULO ────────────────────────────────────────────────────────────

def save_snapshot(data, raw=None):
    """Processa e salva um snapshot bruto no SQLite."""
    raw = raw if raw is not None else json.dumps(data, ensure_ascii=False)
    results = process_data(data)
    binance_feed.set_tracked(list(data.get("data", {}).keys()))

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO snapshots (data_ts, exchange, coin_count, macro, raw_json, results_json) VALUES (?,?,?,?,?,?)",
        (
            results["timestamp"],
            results["exchange"],
            results["coin_count"],
            results["macro"]["status"],
            raw,
            json.dumps(results, ensure_ascii=False),
        ),
    )
    snap_id = cur.lastrowid
    conn.commit()
    conn.close()

    results["snapshot_id"] = snap_id
    return results


def _eassets_credentials_ready():
    return bool(os.getenv("EASSETS_EMAIL") and os.getenv("EASSETS_PASSWORD"))


def latest_snapshot_meta():
    conn = get_db()
    row = conn.execute(
        "SELECT id, imported_at, data_ts, exchange, coin_count, macro, length(raw_json) AS raw_len "
        "FROM snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _do_eassets_import(trigger="manual"):
    if not _eassets_lock.acquire(blocking=False):
        raise EassetsScrapeError("Captura eAssets ja esta em andamento.")

    _eassets_state.update({
        "running": True,
        "last_started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_error": None,
    })

    try:
        data, raw = scrape_eassets_json(
            headless=EASSETS_HEADLESS,
            timeout_ms=EASSETS_TIMEOUT_MS,
        )
        results = save_snapshot(data, raw=raw)
        _eassets_state.update({
            "running": False,
            "last_finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_ok": True,
            "last_error": None,
            "last_snapshot_id": results["snapshot_id"],
            "last_coin_count": results["coin_count"],
        })
        log.info(
            "[eassets] snapshot salvo trigger=%s id=%s moedas=%s",
            trigger,
            results["snapshot_id"],
            results["coin_count"],
        )
        return results
    except Exception as exc:
        _eassets_state.update({
            "running": False,
            "last_finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_ok": False,
            "last_error": str(exc),
        })
        raise
    finally:
        _eassets_lock.release()


def _eassets_loop():
    if not EASSETS_AUTO_ENABLED:
        log.info("[eassets] auto desativado por EASSETS_AUTO_ENABLED")
        return

    time.sleep(15)
    while True:
        try:
            if _eassets_credentials_ready():
                _do_eassets_import(trigger="auto")
            else:
                _eassets_state.update({
                    "last_ok": False,
                    "last_error": "Credenciais ausentes: configure EASSETS_EMAIL e EASSETS_PASSWORD.",
                })
                log.warning("[eassets] credenciais ausentes; auto aguardando ambiente")
        except Exception as e:
            log.warning(f"[eassets] erro na captura automatica: {e}")
        time.sleep(EASSETS_INTERVAL)


def start_background_services():
    global _services_started
    with _services_lock:
        if _services_started:
            return
        init_db()
        binance_feed.start()
        threading.Thread(target=_auto_recalc_loop, daemon=True, name="ph-recalc").start()
        threading.Thread(target=_eassets_loop, daemon=True, name="ph-eassets").start()
        _services_started = True
        log.info("[app] background services started")


def _do_recalc():
    """Carrega último raw_json, sobrepõe live Binance, recalcula, salva."""
    conn = get_db()
    row  = conn.execute(
        "SELECT id, raw_json FROM snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        return

    base_id  = row["id"]
    raw_data = json.loads(row["raw_json"])
    coins    = raw_data.get("data", {})

    # Sobrepõe valores live em cada moeda
    merged_coins = {
        sym: binance_feed.merge_into_coin(sym, coin)
        for sym, coin in coins.items()
    }
    merged_data = dict(raw_data)
    merged_data["data"] = merged_coins

    results = process_data(merged_data)

    conn = get_db()
    conn.execute(
        "INSERT INTO auto_snapshots (base_snap_id, macro, coin_count, top_coins, results_json) "
        "VALUES (?,?,?,?,?)",
        (
            base_id,
            results["macro"]["status"],
            results["coin_count"],
            json.dumps(results["top_coins"]),
            json.dumps(results, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    log.info(f"[auto] recalc salvo — macro={results['macro']['status']} top={results['top_coins']}")


def _auto_recalc_loop():
    # Aguarda o feed ter dados antes do primeiro ciclo
    time.sleep(10)
    while True:
        try:
            if binance_feed.is_live():
                _do_recalc()
        except Exception as e:
            log.warning(f"[auto] erro no recalc: {e}")
        time.sleep(AUTO_RECALC_INTERVAL)


# ── ROTAS ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/import", methods=["POST"])
def api_import():
    try:
        ct = request.content_type or ""
        if "multipart" in ct:
            f = request.files.get("file")
            if not f:
                return jsonify({"error": "Arquivo não enviado"}), 400
            raw  = f.read().decode("utf-8")
            data = json.loads(raw)
        else:
            data = request.get_json(force=True)
            if data is None:
                return jsonify({"error": "JSON inválido"}), 400
            raw = json.dumps(data)

        results = save_snapshot(data, raw=raw)
        return jsonify({"ok": True, "data": results})

    except json.JSONDecodeError as e:
        return jsonify({"error": f"JSON inválido: {e}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/eassets/import", methods=["POST"])
def api_eassets_import():
    try:
        results = _do_eassets_import(trigger="manual")
        return jsonify({"ok": True, "data": results, "status": dict(_eassets_state)})
    except EassetsScrapeError as e:
        return jsonify({"ok": False, "error": str(e), "status": dict(_eassets_state)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "status": dict(_eassets_state)}), 500


@app.route("/api/eassets/status")
def api_eassets_status():
    return jsonify({
        **_eassets_state,
        "auto_enabled": EASSETS_AUTO_ENABLED,
        "interval_seconds": EASSETS_INTERVAL,
        "credentials_ready": _eassets_credentials_ready(),
        "latest_snapshot": latest_snapshot_meta(),
    })


@app.route("/api/snapshots")
def api_snapshots():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, imported_at, data_ts, exchange, coin_count, macro "
        "FROM snapshots ORDER BY id DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/snapshot/<int:sid>")
def api_snapshot(sid):
    conn = get_db()
    row  = conn.execute("SELECT raw_json, results_json FROM snapshots WHERE id=?", (sid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    results = json.loads(row["results_json"])
    if "encryptos_radar" not in results.get("html", {}):
        results = process_data(json.loads(row["raw_json"]))
        results["snapshot_id"] = sid
    return jsonify(results)


@app.route("/api/snapshot/<int:sid>", methods=["DELETE"])
def api_delete_snapshot(sid):
    conn = get_db()
    conn.execute("DELETE FROM snapshots WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/latest")
def api_latest():
    conn = get_db()
    # Prefere auto_snapshot mais recente se existir
    row = conn.execute(
        "SELECT results_json FROM auto_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT results_json FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        conn.close()
        return jsonify(None)

    results = json.loads(row["results_json"])
    if "encryptos_radar" not in results.get("html", {}):
        raw_row = conn.execute(
            "SELECT id, raw_json FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if raw_row:
            results = process_data(json.loads(raw_row["raw_json"]))
            results["snapshot_id"] = raw_row["id"]
    conn.close()
    return jsonify(results)


@app.route("/api/live")
def api_live():
    return jsonify({
        "data":    binance_feed.get_all(),
        "is_live": binance_feed.is_live(),
    })


@app.route("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "db": DB,
        "binance_live": binance_feed.is_live(),
        "eassets_credentials_ready": _eassets_credentials_ready(),
    })


@app.route("/api/auto-snapshots")
def api_auto_snapshots():
    """Lista histórico de auto-recálculos para análise de padrões."""
    limit  = min(int(request.args.get("limit", 200)), 1000)
    conn   = get_db()
    rows   = conn.execute(
        "SELECT id, created_at, base_snap_id, macro, coin_count, top_coins "
        "FROM auto_snapshots ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/auto-snapshots/<int:sid>")
def api_auto_snapshot(sid):
    conn = get_db()
    row  = conn.execute(
        "SELECT results_json FROM auto_snapshots WHERE id=?", (sid,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(json.loads(row["results_json"]))


@app.route("/api/auto-snapshots/stats")
def api_auto_stats():
    """Estatísticas simples sobre os auto-recálculos (para análise de padrões)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT created_at, macro, top_coins FROM auto_snapshots ORDER BY id DESC LIMIT 500"
    ).fetchall()
    conn.close()

    macro_count = {}
    top_freq    = {}
    for r in rows:
        macro_count[r["macro"]] = macro_count.get(r["macro"], 0) + 1
        try:
            for coin in json.loads(r["top_coins"] or "[]"):
                top_freq[coin] = top_freq.get(coin, 0) + 1
        except Exception:
            pass

    top_sorted = sorted(top_freq.items(), key=lambda x: x[1], reverse=True)[:20]
    return jsonify({
        "total_recalcs": len(rows),
        "macro_distribution": macro_count,
        "top_coins_frequency": dict(top_sorted),
    })


if __name__ == "__main__":
    start_background_services()
    print(f"🦅 BANCADA PHOENIX — http://localhost:{PORT}")
    app.run(debug=False, host="0.0.0.0", port=PORT, use_reloader=False)
