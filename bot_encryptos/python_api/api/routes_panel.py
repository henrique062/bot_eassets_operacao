"""
Painel de análise manual de moedas (metodologia Encryptos).

Expõe os dados já calculados a cada scrape (tabela eassets_metrics) para
visualização manual no frontend, sem operar com o bot. Reaproveita a lógica
estrutural de `gerar_painel.py` (score, setup, checklist do Setup de Ouro,
gate macro do BTC e T/OI).

Prefixo: /api/eassets/panel
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_pool
from db import repositories as repo

import gerar_painel as core

router = APIRouter(prefix="/api/eassets/panel", tags=["panel"])


class SymbolTagsRequest(BaseModel):
    symbols: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _f(v: Any) -> float | None:
    """Normalise asyncpg Decimal/None to JSON-friendly float."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _row_to_panel(m: dict[str, Any], alpha_symbols: set[str]) -> dict[str, Any]:
    """Map an eassets_metrics row to the panel row shape used by the frontend."""
    return {
        "symbol": m["symbol"],
        "asset": m["symbol"].replace("USDT", ""),
        "is_alpha": repo.normalize_symbol(m["symbol"]) in alpha_symbols,
        "rank": m.get("rank"),
        "score": m.get("score"),
        "setup": m.get("setup"),
        "price": _f(m.get("price")),
        "change": _f(m.get("price_change_1d")),
        "exp1d": _f(m.get("exp_1d")),
        "exp4h": _f(m.get("exp_4h")),
        "exp1h": _f(m.get("exp_1h")),
        "oitrend": _f(m.get("oi_trend")),
        "lsr": _f(m.get("lsr")),
        "lsrtrend": _f(m.get("lsr_trend")),
        "rsi4h": _f(m.get("rsi_4h")),
        "oiusd": _f(m.get("oi_usd")),
        "trades": _f(m.get("trades_min")),
        "range4h": _f(m.get("range_4h")),
        "range1d": _f(m.get("range_1d")),
        "trades1d": _f(m.get("trades_1d")),
        "toi": _f(m.get("toi")),
        "entry_score": m.get("setup_score"),
        "entry_grade": m.get("setup_grade") or "",
    }


def _btc_macro_from_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute the BTC macro gate from the stored BTCUSDT raw json."""
    btc_raw = next((m for m in metrics if m["symbol"] == "BTCUSDT"), None)
    if not btc_raw:
        return core.btc_macro(None)
    try:
        e = json.loads(btc_raw.get("raw_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        e = {}
    return core.btc_macro(e)


def _meta_out(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meta["id"],
        "timestamp": meta["timestamp"],
        "timestamp_brt": core.to_brt(meta["timestamp"], "%d/%m/%Y %H:%M"),
        "exchange": meta.get("exchange"),
        "setup": meta.get("setup"),
        "symbols": meta.get("symbols"),
        "btc_reset": meta.get("btc_reset"),
    }


async def _resolve_snapshot_id(snapshot_id: int | None) -> int:
    if snapshot_id is not None:
        return snapshot_id
    sid = await repo.get_latest_snapshot_id(get_pool())
    if sid is None:
        raise HTTPException(status_code=404, detail="Nenhum snapshot disponível ainda.")
    return sid


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/snapshots", summary="Lista de snapshots para o seletor do painel")
async def list_snapshots(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    pool = get_pool()
    rows = await repo.list_panel_snapshots(pool, limit=limit)
    out = [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "timestamp_brt": core.to_brt(r["timestamp"], "%d/%m/%Y %H:%M"),
            "exchange": r.get("exchange"),
            "setup": r.get("setup"),
            "symbols": r.get("symbols"),
            "btc_reset": r.get("btc_reset"),
        }
        for r in rows
    ]
    return _ok(out)


@router.get("/tags/alpha", summary="Lista moedas marcadas como Binance Alpha")
async def list_alpha_symbols() -> dict[str, Any]:
    pool = get_pool()
    rows = await repo.list_symbol_tags(pool, tag="alpha")
    return _ok({
        "tag": "alpha",
        "count": len(rows),
        "symbols": [
            {
                "symbol": r["symbol"],
                "asset": r["symbol"].replace("USDT", ""),
                "source": r.get("source"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            for r in rows
        ],
    })


@router.post("/tags/alpha", summary="Adiciona moedas na tag Binance Alpha")
async def add_alpha_symbols(body: SymbolTagsRequest) -> dict[str, Any]:
    pool = get_pool()
    added = await repo.upsert_symbol_tags(pool, body.symbols, tag="alpha", source="manual")
    rows = await repo.list_symbol_tags(pool, tag="alpha")
    return _ok({"tag": "alpha", "added": added, "count": len(rows)})


@router.delete("/tags/alpha/{symbol}", summary="Remove moeda da tag Binance Alpha")
async def remove_alpha_symbol(symbol: str) -> dict[str, Any]:
    pool = get_pool()
    normalized = repo.normalize_symbol(symbol)
    deleted = await repo.delete_symbol_tag(pool, symbol, tag="alpha")
    rows = await repo.list_symbol_tags(pool, tag="alpha")
    return _ok({"tag": "alpha", "symbol": normalized, "deleted": deleted, "count": len(rows)})


@router.get("/latest", summary="Painel ranqueado do último snapshot")
async def panel_latest() -> dict[str, Any]:
    sid = await _resolve_snapshot_id(None)
    return await _build_panel(sid)


@router.get("/snapshot/{snapshot_id}", summary="Painel ranqueado de um snapshot")
async def panel_snapshot(snapshot_id: int) -> dict[str, Any]:
    return await _build_panel(snapshot_id)


async def _build_panel(snapshot_id: int) -> dict[str, Any]:
    pool = get_pool()
    meta = await repo.get_snapshot_meta(pool, snapshot_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado.")

    metrics = await repo.get_panel_metrics(pool, snapshot_id)
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    macro = _btc_macro_from_metrics(metrics)
    rows = [_row_to_panel(m, alpha_symbols) for m in metrics if m["symbol"] != "BTCUSDT"]

    return _ok({
        "meta": _meta_out(meta),
        "btc": macro,
        "rows": rows,
    })


@router.get("/setup", summary="Setup de Ouro — checklist de 7 critérios por moeda")
async def panel_setup(
    snapshot_id: int | None = Query(None),
    limit: int = Query(60, ge=1, le=300),
) -> dict[str, Any]:
    sid = await _resolve_snapshot_id(snapshot_id)
    pool = get_pool()
    meta = await repo.get_snapshot_meta(pool, sid)
    if not meta:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado.")

    metrics = await repo.get_panel_metrics(pool, sid)
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    macro = _btc_macro_from_metrics(metrics)
    safe = bool(macro.get("safe"))

    out = []
    for m in metrics:
        if m["symbol"] == "BTCUSDT":
            continue
        try:
            e = json.loads(m.get("raw_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            e = {}
        chk = core.entry_checklist(e)
        grade, grade_cls, escore = core.setup_grade(chk, safe)
        out.append({
            "symbol": m["symbol"],
            "asset": m["symbol"].replace("USDT", ""),
            "is_alpha": repo.normalize_symbol(m["symbol"]) in alpha_symbols,
            "rank": m.get("rank"),
            "score": m.get("score"),
            "setup_grade": grade,
            "setup_cls": grade_cls,
            "setup_score": escore,
            "checklist": {k: v for k, v in chk.items() if k != "score"},
            "trap": core.is_trap(e),
            "change": _f(m.get("price_change_1d")),
            "lsr": _f(m.get("lsr")),
            "oitrend": _f(m.get("oi_trend")),
        })

    # Ordena: Setup de Ouro primeiro, depois por score de entrada e score
    order = {"SETUP DE OURO": 0, "PARCIAL": 1, "": 2}
    out.sort(key=lambda r: (order.get(r["setup_grade"], 3), -r["setup_score"], -(r["score"] or 0)))
    out = out[:limit]

    return _ok({"meta": _meta_out(meta), "btc": macro, "rows": out})


@router.get("/entry-candidates", summary="Candidatos de entrada (consumido pelo motor do bot)")
async def entry_candidates(
    min_score: float = Query(0, ge=0, le=100),
    include_partial: bool = Query(False),
) -> dict[str, Any]:
    """Retorna as moedas elegíveis para entrada segundo a metodologia Encryptos.

    Esta é a ÚNICA fonte de decisão de QUAIS moedas o bot opera: o motor Rust
    consome este endpoint, em vez de calcular score próprio. Reaproveita
    `gerar_painel.entry_checklist` / `setup_grade` (Setup de Ouro) com o gate
    macro do BTC.

    Args:
        min_score: score estrutural mínimo do painel (0-100).
        include_partial: se True, inclui também grau PARCIAL além de SETUP DE OURO.

    Returns:
        { btc_safe, btc_state, snapshot_id, snapshot_ts, candidates: [...] }
        Ordenado por score de entrada e score estrutural (melhor primeiro).
    """
    pool = get_pool()
    sid = await repo.get_latest_snapshot_id(pool)
    if sid is None:
        return _ok({"btc_safe": False, "btc_state": "—", "snapshot_id": None,
                    "snapshot_ts": None, "candidates": [], "flags": {}})

    # Flags de estratégia da config ativa (o motor não precisa passá-los).
    cfg = await repo.get_latest_config(pool) or {}
    require_btc_reset = bool(cfg.get("require_btc_reset", True))
    allow_partial = include_partial or bool(cfg.get("allow_partial_setup", False))
    require_funding_neg = bool(cfg.get("require_funding_negative", False))
    eff_min_score = min_score if min_score > 0 else float(cfg.get("min_score") or 0)
    manual_targets = await repo.list_trade_targets(pool, active_only=True, mode="paper")
    manual_symbols = {str(row["symbol"]) for row in manual_targets}
    manual_mode_active = bool(manual_symbols)
    paper_mode_enabled = bool(cfg.get("paper_trading", True))

    meta = await repo.get_snapshot_meta(pool, sid)
    metrics = await repo.get_panel_metrics(pool, sid)
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    macro = _btc_macro_from_metrics(metrics)
    safe = bool(macro.get("safe"))

    allowed = {"SETUP DE OURO"} | ({"PARCIAL"} if allow_partial else set())

    # Gate do BTC: por padrão só há candidatos no Reset; o flag pode desligar isso.
    gate_open = safe or not require_btc_reset

    candidates: list[dict[str, Any]] = []
    if gate_open and (not manual_mode_active or paper_mode_enabled):
        for m in metrics:
            if m["symbol"] == "BTCUSDT":
                continue
            if manual_symbols and m["symbol"] not in manual_symbols:
                continue
            if (m.get("score") or 0) < eff_min_score:
                continue
            try:
                e = json.loads(m.get("raw_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                e = {}
            # setup_grade usa o gate macro real; mas se require_btc_reset=False,
            # avaliamos o setup como se a janela estivesse aberta.
            chk = core.entry_checklist(e)
            grade, _cls, escore = core.setup_grade(chk, safe or not require_btc_reset)
            if grade not in allowed:
                continue
            if core.is_trap(e):
                continue
            if require_funding_neg:
                fr = _parse_fr(m.get("raw_json"))
                if fr is None or fr >= 0:
                    continue
            candidates.append({
                "symbol": m["symbol"],
                "asset": m["symbol"].replace("USDT", ""),
                "is_alpha": repo.normalize_symbol(m["symbol"]) in alpha_symbols,
                "score": m.get("score"),
                "entry_score": escore,
                "grade": grade,
                "price": _f(m.get("price")),
                "exp_1d": _f(m.get("exp_1d")),
                "exp_4h": _f(m.get("exp_4h")),
                "exp_1h": _f(m.get("exp_1h")),
                "lsr": _f(m.get("lsr")),
                "oi_trend": _f(m.get("oi_trend")),
            })

        order = {"SETUP DE OURO": 0, "PARCIAL": 1}
        candidates.sort(key=lambda c: (order.get(c["grade"], 2), -c["entry_score"], -(c["score"] or 0)))

    return _ok({
        "btc_safe": safe,
        "btc_state": macro.get("state"),
        "snapshot_id": sid,
        "snapshot_ts": meta.get("timestamp") if meta else None,
        "candidates": candidates,
        "manual_target_mode": "paper" if manual_mode_active else None,
        "manual_target_symbols": sorted(manual_symbols),
        "paper_mode_required": manual_mode_active,
        "paper_mode_enabled": paper_mode_enabled,
    })


@router.get("/radar", summary="Radar de Acumulação — T/OI com persistência")
async def panel_radar(
    snapshot_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    sid = await _resolve_snapshot_id(snapshot_id)
    pool = get_pool()
    meta = await repo.get_snapshot_meta(pool, sid)
    if not meta:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado.")

    metrics = await repo.get_panel_metrics(pool, sid)
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    persistence = await repo.get_toi_persistence(pool, snapshot_id=sid, snapshot_limit=30, top_n=30)
    total_snaps = await repo.count_snapshots(pool, limit=30, snapshot_id=sid)

    rows = [m for m in metrics if m["symbol"] != "BTCUSDT" and m.get("toi") is not None]
    rows.sort(key=lambda m: _f(m.get("toi")) or 0.0, reverse=True)

    out = []
    for m in rows[:limit]:
        out.append({
            "symbol": m["symbol"],
            "asset": m["symbol"].replace("USDT", ""),
            "is_alpha": repo.normalize_symbol(m["symbol"]) in alpha_symbols,
            "toi": _f(m.get("toi")),
            "oiusd": _f(m.get("oi_usd")),
            "trades1d": _f(m.get("trades_1d")),
            "rank": m.get("rank"),
            "score": m.get("score"),
            "setup": m.get("setup"),
            "change": _f(m.get("price_change_1d")),
            "days_top": persistence.get(m["symbol"], 0),
            "total_snaps": total_snaps,
        })

    return _ok({"meta": _meta_out(meta), "rows": out})


@router.get("/topo", summary="Topo Recorrente — moedas que mais apareceram no TOP 10")
async def panel_topo(
    top_n: int = Query(10, ge=1, le=50),
    snapshot_limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    pool = get_pool()
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    rows = await repo.get_top_appearances(pool, top_n=top_n, snapshot_limit=snapshot_limit)
    out = [
        {
            "symbol": r["symbol"],
            "asset": r["symbol"].replace("USDT", ""),
            "is_alpha": repo.normalize_symbol(r["symbol"]) in alpha_symbols,
            "appearances": int(r["appearances"]),
            "best_rank": int(r["best_rank"]) if r["best_rank"] is not None else None,
            "avg_rank": _f(r["avg_rank"]),
            "max_score": int(r["max_score"]) if r["max_score"] is not None else None,
            "avg_score": _f(r["avg_score"]),
        }
        for r in rows
    ]
    return _ok(out)


@router.get("/historico/{symbol}", summary="Histórico de uma moeda nos snapshots")
async def panel_historico(
    symbol: str,
    limit: int = Query(60, ge=1, le=300),
) -> dict[str, Any]:
    pool = get_pool()
    normalized = repo.normalize_symbol(symbol)
    alpha_symbols = await repo.get_tagged_symbols(pool, tag="alpha")
    rows = await repo.get_symbol_panel_history(pool, normalized, limit=limit)
    trade_target = await repo.get_trade_target(pool, normalized, mode="paper")
    if not rows:
        raise HTTPException(status_code=404, detail="Sem histórico para esse símbolo.")

    out = [
        {
            "snapshot_id": r["snapshot_id"],
            "timestamp": r["timestamp"],
            "timestamp_brt": core.to_brt(r["timestamp"], "%d/%m %H:%M"),
            "rank": r.get("rank"),
            "score": r.get("score"),
            "setup": r.get("setup"),
            "price": _f(r.get("price")),
            "change": _f(r.get("price_change_1d")),
            "exp1d": _f(r.get("exp_1d")),
            "exp4h": _f(r.get("exp_4h")),
            "exp1h": _f(r.get("exp_1h")),
            "oitrend": _f(r.get("oi_trend")),
            "lsr": _f(r.get("lsr")),
            "lsrtrend": _f(r.get("lsr_trend")),
            "rsi4h": _f(r.get("rsi_4h")),
            "oiusd": _f(r.get("oi_usd")),
            "toi": _f(r.get("toi")),
        }
        for r in rows
    ]
    return _ok({
        "symbol": normalized,
        "asset": normalized.replace("USDT", ""),
        "is_alpha": normalized in alpha_symbols,
        "paper_target": _trade_target_out(trade_target),
        "history": out,
    })


# ===========================================================================
# Monitoração de moedas + Virada de Funding
# ===========================================================================

class MonitorRequest(BaseModel):
    symbol: str
    note: str | None = None


class TradeTargetRequest(BaseModel):
    symbol: str
    note: str | None = None


def _parse_fr(raw: Any) -> float | None:
    """Extrai o funding rate ('fr') de um raw_json de moeda."""
    try:
        e = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (json.JSONDecodeError, TypeError):
        return None
    fr = e.get("fr")
    if fr is None:
        return None
    try:
        return float(fr)
    except (TypeError, ValueError):
        return None


def _trade_target_out(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "asset": row["symbol"].replace("USDT", ""),
        "mode": row.get("mode"),
        "note": row.get("note"),
        "source": row.get("source"),
        "active": bool(row.get("active")),
        "activated_at": row.get("activated_at").isoformat() if row.get("activated_at") else None,
        "deactivated_at": row.get("deactivated_at").isoformat() if row.get("deactivated_at") else None,
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


def _funding_series(raw_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Constrói a série temporal de funding (cronológica: antigo -> novo)."""
    series = []
    for h in reversed(raw_history):  # raw_history vem novo->antigo
        fr = _parse_fr(h.get("raw_json"))
        if fr is None:
            continue
        series.append({"ts": h["timestamp"], "fr": fr})
    return series


def _detect_funding_flip(series: list[dict[str, Any]]) -> dict[str, Any]:
    """Detecta a última virada de sinal do funding na série cronológica.

    'Virada' = mudança de sinal (positivo<->negativo). Funding negativo =
    shorts pagando longs = munição para short squeeze (alta). Cada moeda tem seu
    intervalo de funding, então medimos em nº de snapshots desde a virada.
    """
    out = {
        "current_fr": None,
        "current_sign": None,
        "flipped": False,
        "snapshots_since_flip": None,
        "last_flip_ts": None,
        "direction": None,  # "to_negative" (bullish) | "to_positive" (bearish)
    }
    pts = [p for p in series if p["fr"] is not None]
    if not pts:
        return out

    cur = pts[-1]["fr"]
    out["current_fr"] = cur
    out["current_sign"] = "neg" if cur < 0 else ("pos" if cur > 0 else "zero")

    def sign(v: float) -> int:
        return -1 if v < 0 else (1 if v > 0 else 0)

    # Procura a última troca de sinal (ignorando zeros) varrendo de trás pra frente
    last_sign = sign(cur)
    flip_index = None
    for i in range(len(pts) - 2, -1, -1):
        s = sign(pts[i]["fr"])
        if s == 0:
            continue
        if s != last_sign and last_sign != 0:
            flip_index = i + 1  # ponto onde já virou
            break
        last_sign = s

    if flip_index is not None:
        out["flipped"] = True
        out["snapshots_since_flip"] = len(pts) - 1 - flip_index
        out["last_flip_ts"] = pts[flip_index]["ts"]
        out["direction"] = "to_negative" if sign(cur) < 0 else "to_positive"
    return out


@router.post("/monitor", summary="Marcar moeda para monitoração")
async def monitor_symbol(req: MonitorRequest) -> dict[str, Any]:
    pool = get_pool()
    symbol = req.symbol.upper()
    sid = await repo.get_latest_snapshot_id(pool)
    mark_price = mark_score = mark_setup = None
    if sid is not None:
        metrics = await repo.get_panel_metrics(pool, sid)
        m = next((x for x in metrics if x["symbol"] == symbol), None)
        if m:
            mark_price = _f(m.get("price"))
            mark_score = m.get("score")
            mark_setup = m.get("setup")
    row = await repo.add_monitored(pool, symbol, req.note, mark_price, mark_score, mark_setup, sid)
    return _ok({"id": row["id"], "symbol": symbol})


@router.get("/trade-targets", summary="Lista alvos manuais do robô")
async def list_trade_targets(active_only: bool = Query(True), mode: str = Query("paper")) -> dict[str, Any]:
    pool = get_pool()
    rows = await repo.list_trade_targets(pool, active_only=active_only, mode=mode)
    return _ok({
        "count": len(rows),
        "targets": [_trade_target_out(row) for row in rows],
    })


@router.post("/trade-targets/paper", summary="Ativa moeda manualmente para o robô em modo paper")
async def activate_paper_trade_target(req: TradeTargetRequest) -> dict[str, Any]:
    pool = get_pool()
    row = await repo.upsert_trade_target(
        pool,
        req.symbol,
        mode="paper",
        note=req.note,
        source="panel-history",
    )
    return _ok(_trade_target_out(row))


@router.delete("/trade-targets/paper/{symbol}", summary="Desativa alvo manual paper do robô")
async def deactivate_paper_trade_target(symbol: str) -> dict[str, Any]:
    pool = get_pool()
    ok = await repo.deactivate_trade_target(pool, symbol, mode="paper")
    if not ok:
        raise HTTPException(status_code=404, detail="Moeda nao estava ativa no robo em modo paper.")
    row = await repo.get_trade_target(pool, symbol, mode="paper")
    return _ok(_trade_target_out(row))


@router.delete("/monitor/{symbol}", summary="Desmarcar moeda da monitoração")
async def unmonitor_symbol(symbol: str) -> dict[str, Any]:
    pool = get_pool()
    ok = await repo.unmark_monitored(pool, symbol.upper())
    if not ok:
        raise HTTPException(status_code=404, detail="Moeda não estava sendo monitorada.")
    return _ok({"unmarked": True})


@router.get("/monitored", summary="Lista de moedas monitoradas com variação desde a marcação")
async def list_monitored(active_only: bool = Query(True)) -> dict[str, Any]:
    pool = get_pool()
    rows = await repo.list_monitored(pool, active_only=active_only)
    try:
        alpha = await repo.get_tagged_symbols(pool, "alpha")
    except Exception:
        alpha = set()

    out = []
    for r in rows:
        mark_price = _f(r.get("mark_price"))
        cur_price = _f(r.get("cur_price"))
        delta_abs = delta_pct = None
        if mark_price and cur_price and mark_price > 0:
            delta_abs = cur_price - mark_price
            delta_pct = (cur_price / mark_price - 1.0) * 100.0

        # Virada de funding da moeda monitorada
        raw_hist = await repo.get_symbol_raw_history(pool, r["symbol"], limit=40)
        funding = _detect_funding_flip(_funding_series(raw_hist))

        out.append({
            "id": r["id"],
            "symbol": r["symbol"],
            "asset": r["symbol"].replace("USDT", ""),
            "is_alpha": repo.normalize_symbol(r["symbol"]) in alpha,
            "note": r.get("note"),
            "marked_at": r.get("marked_at").isoformat() if r.get("marked_at") else None,
            "marked_at_brt": core.to_brt(r.get("marked_at").isoformat(), "%d/%m %H:%M") if r.get("marked_at") else None,
            "mark_price": mark_price,
            "mark_score": r.get("mark_score"),
            "mark_setup": r.get("mark_setup"),
            "cur_price": cur_price,
            "cur_score": r.get("cur_score"),
            "cur_setup": r.get("cur_setup"),
            "cur_rank": r.get("cur_rank"),
            "delta_abs": delta_abs,
            "delta_pct": delta_pct,
            "change_1d": _f(r.get("price_change_1d")),
            "exp_1d": _f(r.get("exp_1d")),
            "exp_4h": _f(r.get("exp_4h")),
            "exp_1h": _f(r.get("exp_1h")),
            "oi_trend": _f(r.get("oi_trend")),
            "lsr": _f(r.get("lsr")),
            "rsi_4h": _f(r.get("rsi_4h")),
            "toi": _f(r.get("toi")),
            "funding": funding,
            "active": r.get("active"),
        })
    return _ok(out)


@router.get("/funding/{symbol}", summary="Série e virada do funding de uma moeda")
async def funding_turn(symbol: str, limit: int = Query(60, ge=2, le=300)) -> dict[str, Any]:
    pool = get_pool()
    raw_hist = await repo.get_symbol_raw_history(pool, symbol.upper(), limit=limit)
    series = _funding_series(raw_hist)
    flip = _detect_funding_flip(series)
    series_out = [
        {"ts": s["ts"], "ts_brt": core.to_brt(s["ts"], "%d/%m %H:%M"), "fr": s["fr"]}
        for s in series
    ]
    return _ok({"symbol": symbol.upper(), "asset": symbol.upper().replace("USDT", ""),
                "flip": flip, "series": series_out})
