"""
Serviço de IA para otimização das configurações de score no Diagnóstico.
"""

import json
import os
import re
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx

import binance_service
import bybit_service
import database as db
from scoring import enrich_with_score
from scoring_counter_trend import enrich_with_score_counter_trend


# Comentário de controle: defaults e descrições usados para fallback/sanitização.
DEFAULT_HARVESTING_SETTINGS = {
    "thresholds": {"forte": 82, "moderado": 70, "fraco": 50},
    "limits": {"max_volatility": 25, "min_volume": 2_000_000},
    "weights": {"apy": 20, "vol": 30, "int": 10, "consistency": 25, "momentum": 15},
}

DEFAULT_COUNTER_SETTINGS = {
    "thresholds": {"forte": 80, "moderado": 65, "fraco": 45},
    "limits": {"min_volume": 2_000_000, "min_funding_rate_pct": 0.10},
    "weights": {"extremity": 30, "persistence": 35, "volume": 15, "volatility_bonus": 20},
}

SETTING_KEY_MAP = {
    "harvesting": {
        "thresholds": "score_thresholds",
        "limits": "score_limits",
        "weights": "score_weights",
    },
    "counter_trend": {
        "thresholds": "score_thresholds_counter",
        "limits": "score_limits_counter",
        "weights": "score_weights_counter",
    },
}

SETTING_DESCRIPTIONS = {
    "score_thresholds": "Thresholds de confiança do score para coleta de funding.",
    "score_limits": "Vetos de risco do score para coleta de funding.",
    "score_weights": "Pesos dos componentes do score de coleta: APY, volume, intervalo, consistência e momentum.",
    "score_thresholds_counter": "Thresholds de confiança do score no modo counter-trend.",
    "score_limits_counter": "Vetos de risco do counter-trend: liquidez mínima e funding mínimo.",
    "score_weights_counter": "Pesos do counter-trend: extremidade, persistência, volume e bônus de volatilidade.",
}

RANGES = {
    "thresholds": {
        "forte": (0, 100),
        "moderado": (0, 100),
        "fraco": (0, 100),
    },
    "harvesting_limits": {
        "max_volatility": (0, 100),
        "min_volume": (0, 10_000_000_000),
    },
    "counter_limits": {
        "min_volume": (0, 10_000_000_000),
        "min_funding_rate_pct": (0, 5),
    },
    "harvesting_weights": {
        "apy": (0, 100),
        "vol": (0, 100),
        "int": (0, 100),
        "consistency": (0, 100),
        "momentum": (0, 100),
    },
    "counter_weights": {
        "extremity": (0, 100),
        "persistence": (0, 100),
        "volume": (0, 100),
        "volatility_bonus": (0, 100),
    },
}

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

EXCHANGES = {
    "binance": binance_service,
    "bybit": bybit_service,
}


# Comentário de controle: utilitários de normalização/validação numérica.
def _clamp(value, min_val, max_val):
    try:
        num = float(value)
    except Exception:
        num = float(min_val)
    if num < min_val:
        return float(min_val)
    if num > max_val:
        return float(max_val)
    return num


def _normalize_mode(mode: str) -> str:
    raw = str(mode or "harvesting").strip().lower()
    if raw not in {"harvesting", "counter_trend"}:
        raise ValueError("mode inválido. Use 'harvesting' ou 'counter_trend'.")
    return raw


def _normalize_window_days(window_days) -> int:
    # Comentário de controle: requisito funcional fixo de 7 dias.
    return 7


def _ensure_threshold_order(thresholds: dict) -> dict:
    forte = float(thresholds.get("forte", 75))
    moderado = float(thresholds.get("moderado", 50))
    fraco = float(thresholds.get("fraco", 30))
    ordered = sorted([forte, moderado, fraco], reverse=True)
    return {"forte": ordered[0], "moderado": ordered[1], "fraco": ordered[2]}


def _extract_json_from_ai(raw_text: str) -> dict | None:
    if not raw_text or not raw_text.strip():
        return None
    # Comentário de controle: fallback robusto para respostas com/sem ```json```.
    block = re.search(r"```json\s*\n?(.*?)\n?\s*```", raw_text, re.DOTALL)
    if block:
        try:
            return json.loads(block.group(1).strip())
        except json.JSONDecodeError:
            pass

    generic_block = re.search(r"```\s*\n?(.*?)\n?\s*```", raw_text, re.DOTALL)
    if generic_block:
        try:
            return json.loads(generic_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    obj_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        return None


def _mode_defaults(mode: str) -> dict:
    if mode == "counter_trend":
        return json.loads(json.dumps(DEFAULT_COUNTER_SETTINGS))
    return json.loads(json.dumps(DEFAULT_HARVESTING_SETTINGS))


async def _load_mode_settings_from_db(mode: str) -> dict:
    defaults = _mode_defaults(mode)
    key_map = SETTING_KEY_MAP[mode]
    rows = await db.fetch(
        """
        SELECT key, value
        FROM system_settings
        WHERE key = ANY($1::text[])
        """,
        [key_map["thresholds"], key_map["limits"], key_map["weights"]],
    )
    parsed = json.loads(json.dumps(defaults))
    for r in rows:
        key = r["key"]
        value = r["value"]
        value = json.loads(value) if isinstance(value, str) else value
        if key == key_map["thresholds"]:
            parsed["thresholds"] = value or parsed["thresholds"]
        elif key == key_map["limits"]:
            parsed["limits"] = value or parsed["limits"]
        elif key == key_map["weights"]:
            parsed["weights"] = value or parsed["weights"]
    return _sanitize_settings(mode, parsed, defaults)


def _sanitize_settings(mode: str, candidate: dict, fallback: dict) -> dict:
    source = candidate or {}
    out = json.loads(json.dumps(fallback))
    # Comentário de controle: tolera blocos serializados como string JSON em dados legados.
    def _ensure_obj(value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    # Comentário de controle: thresholds sempre ordenados e clampados.
    thresholds = _ensure_obj(source.get("thresholds"))
    out["thresholds"]["forte"] = _clamp(thresholds.get("forte", out["thresholds"]["forte"]), *RANGES["thresholds"]["forte"])
    out["thresholds"]["moderado"] = _clamp(thresholds.get("moderado", out["thresholds"]["moderado"]), *RANGES["thresholds"]["moderado"])
    out["thresholds"]["fraco"] = _clamp(thresholds.get("fraco", out["thresholds"]["fraco"]), *RANGES["thresholds"]["fraco"])
    out["thresholds"] = _ensure_threshold_order(out["thresholds"])

    limits = _ensure_obj(source.get("limits"))
    if mode == "counter_trend":
        out["limits"]["min_volume"] = _clamp(limits.get("min_volume", out["limits"]["min_volume"]), *RANGES["counter_limits"]["min_volume"])
        out["limits"]["min_funding_rate_pct"] = _clamp(
            limits.get("min_funding_rate_pct", out["limits"]["min_funding_rate_pct"]),
            *RANGES["counter_limits"]["min_funding_rate_pct"],
        )
    else:
        out["limits"]["max_volatility"] = _clamp(
            limits.get("max_volatility", out["limits"]["max_volatility"]),
            *RANGES["harvesting_limits"]["max_volatility"],
        )
        out["limits"]["min_volume"] = _clamp(
            limits.get("min_volume", out["limits"]["min_volume"]),
            *RANGES["harvesting_limits"]["min_volume"],
        )

    weights = _ensure_obj(source.get("weights"))
    if mode == "counter_trend":
        for key, rng in RANGES["counter_weights"].items():
            out["weights"][key] = _clamp(weights.get(key, out["weights"][key]), *rng)
    else:
        for key, rng in RANGES["harvesting_weights"].items():
            out["weights"][key] = _clamp(weights.get(key, out["weights"][key]), *rng)

    return out


def _infer_mode_from_breakdown(raw_breakdown) -> str | None:
    if raw_breakdown is None:
        return None
    breakdown = raw_breakdown
    if isinstance(breakdown, str):
        try:
            breakdown = json.loads(breakdown)
        except Exception:
            return None
    if not isinstance(breakdown, dict):
        return None
    keys = {str(k).lower() for k in breakdown.keys()}
    if {"extremity", "persistence", "volatility_bonus"} & keys:
        return "counter_trend"
    if {"apy", "consistency", "momentum", "interval"} & keys:
        return "harvesting"
    return None


async def _load_trades_for_mode(user_id: int, exchange: str, mode: str, window_days: int):
    # Comentário de controle: query restrita ao usuário/exchange e janela exigida.
    rows = await db.fetch(
        """
        SELECT
            rt.id,
            rt.config_id,
            rt.symbol,
            rt.exchange,
            rt.direction,
            rt.total_pnl,
            rt.total_pnl_pct,
            rt.funding_pnl,
            rt.price_pnl,
            rt.fee_cost,
            rt.entry_score,
            rt.entry_score_breakdown,
            rt.created_at,
            rc.operation_mode,
            rc.session_name
        FROM real_trades rt
        JOIN real_config rc ON rc.id = rt.config_id
        WHERE rc.user_id = $1
          AND rt.exchange = $2
          AND rt.created_at >= NOW() - ($3::int * INTERVAL '1 day')
        ORDER BY rt.created_at DESC
        """,
        user_id,
        exchange,
        window_days,
    )

    filtered = []
    ignored_without_breakdown = 0
    ignored_other_mode = 0
    for r in rows:
        inferred = _infer_mode_from_breakdown(r["entry_score_breakdown"])
        if inferred is None:
            ignored_without_breakdown += 1
            continue
        if inferred != mode:
            ignored_other_mode += 1
            continue
        filtered.append(
            {
                "id": r["id"],
                "configId": r["config_id"],
                "symbol": r["symbol"],
                "exchange": r["exchange"],
                "direction": r["direction"],
                "totalPnl": float(r["total_pnl"] or 0),
                "totalPnlPct": float(r["total_pnl_pct"] or 0),
                "fundingPnl": float(r["funding_pnl"] or 0),
                "pricePnl": float(r["price_pnl"] or 0),
                "feeCost": float(r["fee_cost"] or 0),
                "entryScore": float(r["entry_score"] or 0) if r["entry_score"] is not None else None,
                "entryScoreBreakdown": json.loads(r["entry_score_breakdown"]) if isinstance(r["entry_score_breakdown"], str) else r["entry_score_breakdown"],
                "createdAt": r["created_at"],
                "operationMode": r["operation_mode"],
                "sessionName": r["session_name"],
            }
        )

    return {
        "rowsAll": len(rows),
        "rowsMode": filtered,
        "ignoredWithoutBreakdown": ignored_without_breakdown,
        "ignoredOtherMode": ignored_other_mode,
    }


async def _load_snapshots(exchange: str, symbols: list[str], start_dt: datetime, end_dt: datetime):
    if not symbols:
        return {}
    rows = await db.fetch(
        """
        SELECT
            symbol,
            funding_rate,
            funding_rate_pct,
            volume_24h,
            price_24h_pcnt,
            funding_interval,
            captured_at
        FROM funding_rate_snapshots
        WHERE exchange = $1
          AND symbol = ANY($2::text[])
          AND captured_at >= $3
          AND captured_at <= $4
        ORDER BY symbol ASC, captured_at ASC
        """,
        exchange,
        symbols,
        start_dt,
        end_dt,
    )

    grouped = {}
    for r in rows:
        sym = r["symbol"]
        if sym not in grouped:
            grouped[sym] = {"times": [], "rows": []}
        grouped[sym]["times"].append(r["captured_at"])
        grouped[sym]["rows"].append(
            {
                "symbol": sym,
                "funding_rate": float(r["funding_rate"] or 0),
                "funding_rate_pct": float(r["funding_rate_pct"] or 0),
                "volume_24h": float(r["volume_24h"] or 0),
                "price_24h_pcnt": float(r["price_24h_pcnt"] or 0),
                "funding_interval": int(r["funding_interval"] or 8),
                "captured_at": r["captured_at"],
            }
        )
    return grouped


def _pick_snapshot(index_bucket: dict, trade_time: datetime):
    if not index_bucket:
        return None, []
    times = index_bucket["times"]
    rows = index_bucket["rows"]
    pos = bisect_right(times, trade_time) - 1
    if pos < 0:
        return rows[0], []
    current = rows[pos]
    history = rows[: pos + 1]
    return current, history


def _calc_consistency_score(history_rows: list[dict], current_rate: float) -> float:
    if current_rate == 0:
        return 5.0
    if not history_rows:
        return 5.0
    recent = history_rows[-15:]
    if len(recent) < 3:
        return 5.0
    same = sum(1 for r in recent if float(r["funding_rate"]) * current_rate > 0)
    ratio = same / len(recent)
    if ratio >= 0.9:
        return 15.0
    if ratio >= 0.7:
        return 10.0
    if ratio >= 0.5:
        return 5.0
    return 0.0


def _calc_momentum_score(history_rows: list[dict], current_rate: float) -> float:
    if current_rate == 0:
        return 0.0
    if not history_rows:
        return 0.0
    if len(history_rows) < 4:
        return 0.0

    rates = [abs(float(r["funding_rate"])) for r in history_rows[-16:]]
    if len(rates) < 4:
        return 0.0
    mid = len(rates) // 2
    older = rates[:mid]
    recent = rates[mid:]
    avg_older = sum(older) / len(older)
    avg_recent = sum(recent) / len(recent)
    current_abs = abs(current_rate)

    if avg_older <= 0:
        return 0.0
    if avg_recent > 0.0001 and current_abs < avg_recent * 0.50:
        return -15.0

    change = (avg_recent - avg_older) / avg_older
    if change >= 0.25:
        return 15.0
    if change >= 0.08:
        return 8.0
    if change >= -0.08:
        return 3.0
    if change >= -0.25:
        return -8.0
    return -15.0


def _calc_persistence_score(history_rows: list[dict], current_rate: float) -> float:
    if current_rate == 0:
        return 0.0
    if not history_rows:
        return 10.0
    recent = history_rows[-20:]
    if len(recent) < 3:
        return 10.0
    same = sum(1 for r in recent if float(r["funding_rate"]) * current_rate > 0)
    ratio = same / len(recent)
    if ratio >= 0.95:
        return 30.0
    if ratio >= 0.85:
        return 22.0
    if ratio >= 0.70:
        return 14.0
    if ratio >= 0.50:
        return 7.0
    return 0.0


def _classify_confidence(score: float, thresholds: dict, veto_label: str | None = None):
    if veto_label:
        return veto_label, False
    forte = float(thresholds.get("forte", 75))
    moderado = float(thresholds.get("moderado", 50))
    fraco = float(thresholds.get("fraco", 30))
    if score >= forte:
        return "FORTE", True
    if score >= moderado:
        return "MODERADO", True
    if score >= fraco:
        return "FRACO", False
    return "EVITAR", False


def _calc_harvesting_score(snapshot: dict, history_rows: list[dict], settings: dict):
    if not snapshot:
        return {"score": 0.0, "shouldOpen": False, "confidence": "EVITAR"}
    funding_pct = abs(float(snapshot.get("funding_rate_pct", 0)))
    funding_rate = float(snapshot.get("funding_rate", 0))
    volatility = abs(float(snapshot.get("price_24h_pcnt", 0)))
    volume = float(snapshot.get("volume_24h", 0))
    interval = int(snapshot.get("funding_interval", 8) or 8)

    limits = settings["limits"]
    weights = settings["weights"]
    thresholds = settings["thresholds"]

    max_volatility = float(limits.get("max_volatility", 35))
    min_volume = float(limits.get("min_volume", 2_000_000))

    if volatility > max_volatility:
        conf, open_flag = _classify_confidence(0, thresholds, veto_label="VETO R/R")
        return {"score": 0.0, "shouldOpen": open_flag, "confidence": conf}
    if volume > 0 and volume < min_volume:
        conf, open_flag = _classify_confidence(0, thresholds, veto_label="VETO R/R")
        return {"score": 0.0, "shouldOpen": open_flag, "confidence": conf}

    fee_round_trip_pct = 0.04
    payments_per_year = (24.0 / interval) * 365.0 if interval > 0 else 0
    gross_apy = funding_pct * payments_per_year if payments_per_year > 0 else 0
    net_payment = funding_pct - (fee_round_trip_pct / payments_per_year) if payments_per_year > 0 else -1

    if net_payment <= 0:
        apy_score = 0.0
    elif gross_apy >= 200:
        apy_score = 40.0
    elif gross_apy >= 100:
        apy_score = 25 + (gross_apy - 100) / 100 * 15
    elif gross_apy >= 40:
        apy_score = 10 + (gross_apy - 40) / 60 * 15
    elif gross_apy >= 15:
        apy_score = (gross_apy - 15) / 25 * 10
    else:
        apy_score = 0.0

    if volume >= 300_000_000:
        vol_score = 20.0
    elif volume >= 80_000_000:
        vol_score = 13 + (volume - 80_000_000) / (300_000_000 - 80_000_000) * 7
    elif volume >= 20_000_000:
        vol_score = 6 + (volume - 20_000_000) / (80_000_000 - 20_000_000) * 7
    elif volume >= min_volume:
        vol_score = (volume - min_volume) / max(1.0, (20_000_000 - min_volume)) * 6
    else:
        vol_score = 0.0

    if interval <= 1:
        int_score = 10.0
    elif interval <= 2:
        int_score = 8.0
    elif interval <= 4:
        int_score = 5.0
    else:
        int_score = 0.0

    consistency_score = _calc_consistency_score(history_rows, funding_rate)
    momentum_score = _calc_momentum_score(history_rows[-16:], funding_rate)

    apy_score *= float(weights.get("apy", 40)) / 40.0
    vol_score *= float(weights.get("vol", 20)) / 20.0
    int_score *= float(weights.get("int", 10)) / 10.0
    consistency_score *= float(weights.get("consistency", 15)) / 15.0
    momentum_score *= float(weights.get("momentum", 15)) / 15.0

    total = max(0.0, min(100.0, round(apy_score + vol_score + int_score + consistency_score + momentum_score, 2)))
    confidence, should_open = _classify_confidence(total, thresholds)
    return {"score": total, "shouldOpen": should_open, "confidence": confidence}


def _calc_counter_score(snapshot: dict, history_rows: list[dict], settings: dict):
    if not snapshot:
        return {"score": 0.0, "shouldOpen": False, "confidence": "EVITAR"}
    funding_pct = abs(float(snapshot.get("funding_rate_pct", 0)))
    funding_rate = float(snapshot.get("funding_rate", 0))
    volatility = abs(float(snapshot.get("price_24h_pcnt", 0)))
    volume = float(snapshot.get("volume_24h", 0))

    limits = settings["limits"]
    thresholds = settings["thresholds"]
    weights = settings["weights"]
    min_volume = float(limits.get("min_volume", 2_000_000))
    min_funding = float(limits.get("min_funding_rate_pct", 0.01))

    if volume > 0 and volume < min_volume:
        conf, open_flag = _classify_confidence(0, thresholds, veto_label="VETO")
        return {"score": 0.0, "shouldOpen": open_flag, "confidence": conf}
    if funding_pct < min_funding:
        conf, open_flag = _classify_confidence(0, thresholds, veto_label="VETO")
        return {"score": 0.0, "shouldOpen": open_flag, "confidence": conf}

    if funding_pct >= 0.15:
        extremity_score = 40.0
    elif funding_pct >= 0.10:
        extremity_score = 30 + (funding_pct - 0.10) / 0.05 * 10
    elif funding_pct >= 0.05:
        extremity_score = 15 + (funding_pct - 0.05) / 0.05 * 15
    elif funding_pct >= 0.02:
        extremity_score = 5 + (funding_pct - 0.02) / 0.03 * 10
    elif funding_pct >= 0.01:
        extremity_score = (funding_pct - 0.01) / 0.01 * 5
    else:
        extremity_score = 0.0

    persistence_score = _calc_persistence_score(history_rows, funding_rate)

    if volume >= 300_000_000:
        vol_score = 20.0
    elif volume >= 80_000_000:
        vol_score = 13 + (volume - 80_000_000) / (300_000_000 - 80_000_000) * 7
    elif volume >= 20_000_000:
        vol_score = 6 + (volume - 20_000_000) / (80_000_000 - 20_000_000) * 7
    elif volume >= min_volume:
        vol_score = (volume - min_volume) / max(1.0, (20_000_000 - min_volume)) * 6
    else:
        vol_score = 0.0

    if volatility >= 20:
        volatility_bonus = 10.0
    elif volatility >= 10:
        volatility_bonus = 7.0
    elif volatility >= 5:
        volatility_bonus = 4.0
    elif volatility >= 2:
        volatility_bonus = 2.0
    else:
        volatility_bonus = 0.0

    extremity_score *= float(weights.get("extremity", 40)) / 40.0
    persistence_score *= float(weights.get("persistence", 30)) / 30.0
    vol_score *= float(weights.get("volume", 20)) / 20.0
    volatility_bonus *= float(weights.get("volatility_bonus", 10)) / 10.0

    total = max(0.0, min(100.0, round(extremity_score + persistence_score + vol_score + volatility_bonus, 2)))
    confidence, should_open = _classify_confidence(total, thresholds)
    return {"score": total, "shouldOpen": should_open, "confidence": confidence}


def _build_projection(mode: str, trades: list[dict], snapshots_index: dict, settings: dict):
    selected = 0
    wins = 0
    total_pnl = 0.0
    scored = 0
    avg_score_acc = 0.0

    for t in trades:
        symbol = t["symbol"]
        bucket = snapshots_index.get(symbol)
        snap, history = _pick_snapshot(bucket, t["createdAt"]) if bucket else (None, [])
        if mode == "counter_trend":
            calc = _calc_counter_score(snap, history, settings)
        else:
            calc = _calc_harvesting_score(snap, history, settings)
        scored += 1
        avg_score_acc += float(calc["score"] or 0)
        if calc["shouldOpen"]:
            selected += 1
            pnl = float(t["totalPnl"] or 0)
            total_pnl += pnl
            if pnl > 0:
                wins += 1

    win_rate = (wins / selected * 100) if selected else 0.0
    avg_pnl = (total_pnl / selected) if selected else 0.0
    avg_score = (avg_score_acc / scored) if scored else 0.0
    return {
        "selectedTrades": selected,
        "skippedTrades": max(0, len(trades) - selected),
        "wins": wins,
        "losses": max(0, selected - wins),
        "winRate": round(win_rate, 2),
        "totalPnl": round(total_pnl, 6),
        "avgPnl": round(avg_pnl, 6),
        "avgScore": round(avg_score, 2),
        "scoredTrades": scored,
    }


async def _build_market_snapshot(exchange: str, mode: str):
    svc = EXCHANGES.get(exchange)
    if not svc:
        return {
            "exchange": exchange,
            "mode": mode,
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "totals": {},
            "topByScore": [],
        }
    rates = await svc.get_all_funding_rates()
    if mode == "counter_trend":
        rated = await enrich_with_score_counter_trend(rates)
    else:
        rated = await enrich_with_score(rates)

    rated = sorted(rated, key=lambda x: float((x.get("scoreData") or {}).get("score", 0)), reverse=True)
    top = rated[:20]
    counts = Counter((r.get("scoreData") or {}).get("confidence", "EVITAR") for r in rated)
    return {
        "exchange": exchange,
        "mode": mode,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "totals": dict(counts),
        "topByScore": [
            {
                "symbol": r.get("symbol"),
                "score": (r.get("scoreData") or {}).get("score", 0),
                "confidence": (r.get("scoreData") or {}).get("confidence", "EVITAR"),
                "direction": (r.get("scoreData") or {}).get("direction", "NEUTRO"),
                "fundingRatePercent": float(r.get("fundingRatePercent") or 0),
                "volume24h": float(r.get("volume24h") or r.get("turnover24h") or 0),
                "price24hPcnt": float(r.get("price24hPcnt") or 0),
            }
            for r in top
        ],
    }


def _build_fallback_analysis(mode: str, baseline: dict, recommended: dict, market_snapshot: dict, reason: str):
    mode_label = "Counter-Tendência" if mode == "counter_trend" else "Coleta de Taxa"
    text = (
        f"## Diagnóstico automático ({mode_label})\n\n"
        f"Não foi possível gerar recomendação via Gemini ({reason}).\n"
        f"Foram analisados **{baseline.get('selectedTrades', 0)} trades selecionados** "
        f"em um total de **{baseline.get('scoredTrades', 0)} avaliados**.\n\n"
        f"Top atual de mercado considerado: **{len(market_snapshot.get('topByScore', []))}** ativos.\n"
    )
    return text, recommended


async def _ask_gemini_for_recommendation(
    mode: str,
    exchange: str,
    baseline_settings: dict,
    baseline_projection: dict,
    market_snapshot: dict,
):
    if not GEMINI_API_KEY:
        return {
            "analysis_markdown": "",
            "recommended_settings": baseline_settings,
            "reasons": {},
            "fallback_reason": "GEMINI_API_KEY não configurada",
        }

    mode_label = "counter_trend" if mode == "counter_trend" else "harvesting"
    payload_input = {
        "mode": mode_label,
        "exchange": exchange,
        "baseline_settings": baseline_settings,
        "baseline_projection": baseline_projection,
        "market_snapshot_top": market_snapshot.get("topByScore", [])[:10],
        "market_totals": market_snapshot.get("totals", {}),
    }

    # Comentário de controle: prompt orientado a JSON estrito para reduzir parsing frágil.
    prompt = f"""Você é um auditor quantitativo do motor de score de cripto.

Analise o payload e recomende ajustes apenas para melhorar qualidade do filtro e lucratividade esperada.

Payload:
```json
{json.dumps(payload_input, ensure_ascii=False, indent=2)}
```

Responda EXCLUSIVAMENTE JSON válido:
```json
{{
  "analysis_markdown": "Resumo em markdown em PT-BR, objetivo e curto.",
  "recommended_settings": {{
    "thresholds": {{"forte": 0, "moderado": 0, "fraco": 0}},
    "limits": {{}},
    "weights": {{}}
  }},
  "reasons": {{
    "thresholds.forte": "motivo",
    "thresholds.moderado": "motivo",
    "thresholds.fraco": "motivo"
  }}
}}
```

Regras:
- Nunca retorne campos fora de thresholds/limits/weights.
- Mantenha coerência forte>=moderado>=fraco.
- Não use hedge/arbitragem.
"""

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 2048,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        raw_text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        parsed = _extract_json_from_ai(raw_text)
        if not parsed:
            return {
                "analysis_markdown": raw_text or "",
                "recommended_settings": baseline_settings,
                "reasons": {},
                "fallback_reason": "Gemini retornou resposta sem JSON parseável",
            }
        return {
            "analysis_markdown": str(parsed.get("analysis_markdown") or ""),
            "recommended_settings": parsed.get("recommended_settings") or baseline_settings,
            "reasons": parsed.get("reasons") or {},
            "fallback_reason": "",
        }
    except Exception as e:
        return {
            "analysis_markdown": "",
            "recommended_settings": baseline_settings,
            "reasons": {},
            "fallback_reason": str(e),
        }


def _build_delta_projection(baseline: dict, recommended: dict):
    return {
        "selectedTrades": int(recommended["selectedTrades"] - baseline["selectedTrades"]),
        "winRate": round(float(recommended["winRate"] - baseline["winRate"]), 2),
        "totalPnl": round(float(recommended["totalPnl"] - baseline["totalPnl"]), 6),
        "avgPnl": round(float(recommended["avgPnl"] - baseline["avgPnl"]), 6),
    }


def _normalize_reasons_map(raw_reasons) -> dict:
    if not isinstance(raw_reasons, dict):
        return {}
    clean = {}
    for key, val in raw_reasons.items():
        k = str(key).strip()
        if not k:
            continue
        clean[k] = str(val)[:240]
    return clean


async def run_score_ai_analysis(user_id: int, payload: dict):
    mode = _normalize_mode((payload or {}).get("mode"))
    exchange = str((payload or {}).get("exchange") or "binance").lower().strip()
    if exchange not in EXCHANGES:
        raise ValueError("exchange inválida. Use 'binance' ou 'bybit'.")
    window_days = _normalize_window_days((payload or {}).get("windowDays"))

    current_settings = await _load_mode_settings_from_db(mode)
    draft_settings = _sanitize_settings(
        mode,
        ((payload or {}).get("draftSettings") or {}),
        current_settings,
    )

    trades_info = await _load_trades_for_mode(user_id=user_id, exchange=exchange, mode=mode, window_days=window_days)
    trades = trades_info["rowsMode"]
    market_snapshot = await _build_market_snapshot(exchange=exchange, mode=mode)

    if trades:
        min_dt = min(t["createdAt"] for t in trades) - timedelta(days=5)
        max_dt = max(t["createdAt"] for t in trades) + timedelta(hours=1)
        symbols = sorted({t["symbol"] for t in trades})
        snapshots_index = await _load_snapshots(exchange=exchange, symbols=symbols, start_dt=min_dt, end_dt=max_dt)
    else:
        snapshots_index = {}

    baseline_projection = _build_projection(mode=mode, trades=trades, snapshots_index=snapshots_index, settings=draft_settings)

    ai_result = await _ask_gemini_for_recommendation(
        mode=mode,
        exchange=exchange,
        baseline_settings=draft_settings,
        baseline_projection=baseline_projection,
        market_snapshot=market_snapshot,
    )
    recommended_sanitized = _sanitize_settings(mode, ai_result.get("recommended_settings") or {}, draft_settings)
    recommended_projection = _build_projection(
        mode=mode,
        trades=trades,
        snapshots_index=snapshots_index,
        settings=recommended_sanitized,
    )
    projection_delta = _build_delta_projection(baseline=baseline_projection, recommended=recommended_projection)

    reasons_map = _normalize_reasons_map(ai_result.get("reasons") or {})
    analysis_markdown = str(ai_result.get("analysis_markdown") or "").strip()
    if not analysis_markdown:
        analysis_markdown, recommended_sanitized = _build_fallback_analysis(
            mode=mode,
            baseline=baseline_projection,
            recommended=recommended_sanitized,
            market_snapshot=market_snapshot,
            reason=ai_result.get("fallback_reason") or "resposta vazia",
        )

    metrics = {
        "windowDays": window_days,
        "exchange": exchange,
        "mode": mode,
        "tradesFetched": trades_info["rowsAll"],
        "tradesEvaluated": len(trades),
        "ignoredWithoutBreakdown": trades_info["ignoredWithoutBreakdown"],
        "ignoredOtherMode": trades_info["ignoredOtherMode"],
        "fallbackReason": ai_result.get("fallback_reason") or "",
    }

    projection = {
        "windowDays": window_days,
        "tradesEvaluated": len(trades),
        "baseline": baseline_projection,
        "recommended": recommended_projection,
        "delta": projection_delta,
    }

    row = await db.fetchrow(
        """
        INSERT INTO score_ai_analyses (
            user_id,
            exchange,
            mode,
            window_days,
            current_settings,
            recommended_settings,
            analysis_markdown,
            metrics,
            projection,
            market_snapshot,
            applied,
            created_at
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5::jsonb,
            $6::jsonb,
            $7,
            $8::jsonb,
            $9::jsonb,
            $10::jsonb,
            FALSE,
            NOW()
        )
        RETURNING id, created_at
        """,
        user_id,
        exchange,
        mode,
        window_days,
        json.dumps(draft_settings),
        json.dumps(recommended_sanitized),
        analysis_markdown,
        json.dumps(metrics),
        json.dumps(projection),
        json.dumps(market_snapshot),
    )

    created_at = row["created_at"]
    created_at_iso = created_at.isoformat() if created_at else datetime.now(timezone.utc).isoformat()

    return {
        "success": True,
        "analysisId": row["id"],
        "mode": mode,
        "analysisMarkdown": analysis_markdown,
        "currentSettings": draft_settings,
        "recommendedSettings": recommended_sanitized,
        "recommendationReasons": reasons_map,
        "metrics": metrics,
        "projection": projection,
        "marketSnapshot": market_snapshot,
        "createdAt": created_at_iso,
    }


async def apply_score_ai_recommendation(user_id: int, analysis_id: int):
    row = await db.fetchrow(
        """
        SELECT
            id,
            mode,
            recommended_settings,
            applied
        FROM score_ai_analyses
        WHERE id = $1
          AND user_id = $2
        """,
        analysis_id,
        user_id,
    )
    if not row:
        raise ValueError("analysisId não encontrado para o usuário.")

    mode = _normalize_mode(row["mode"])
    recommended = row["recommended_settings"]
    recommended = json.loads(recommended) if isinstance(recommended, str) else (recommended or {})
    recommended = _sanitize_settings(mode, recommended, _mode_defaults(mode))

    key_map = SETTING_KEY_MAP[mode]
    key_values = {
        key_map["thresholds"]: recommended["thresholds"],
        key_map["limits"]: recommended["limits"],
        key_map["weights"]: recommended["weights"],
    }

    applied_keys = []
    # Comentário de controle: upsert explícito em system_settings para manter compatibilidade.
    for key, value in key_values.items():
        await db.execute(
            """
            INSERT INTO system_settings (key, value, description, updated_at)
            VALUES ($1, $2::jsonb, $3, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                description = COALESCE(system_settings.description, EXCLUDED.description),
                updated_at = NOW()
            """,
            key,
            json.dumps(value),
            SETTING_DESCRIPTIONS.get(key),
        )
        applied_keys.append(key)

    await db.execute(
        """
        UPDATE score_ai_analyses
        SET applied = TRUE,
            applied_at = NOW()
        WHERE id = $1
        """,
        analysis_id,
    )

    return {
        "success": True,
        "applied": True,
        "appliedKeys": applied_keys,
        "settings": key_values,
    }
