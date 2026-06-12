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

from database import get_pool
from db import repositories as repo

import gerar_painel as core

router = APIRouter(prefix="/api/eassets/panel", tags=["panel"])


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


def _row_to_panel(m: dict[str, Any]) -> dict[str, Any]:
    """Map an eassets_metrics row to the panel row shape used by the frontend."""
    return {
        "symbol": m["symbol"],
        "asset": m["symbol"].replace("USDT", ""),
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
    macro = _btc_macro_from_metrics(metrics)
    rows = [_row_to_panel(m) for m in metrics if m["symbol"] != "BTCUSDT"]

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
                    "snapshot_ts": None, "candidates": []})

    meta = await repo.get_snapshot_meta(pool, sid)
    metrics = await repo.get_panel_metrics(pool, sid)
    macro = _btc_macro_from_metrics(metrics)
    safe = bool(macro.get("safe"))

    allowed = {"SETUP DE OURO"} | ({"PARCIAL"} if include_partial else set())

    candidates: list[dict[str, Any]] = []
    # Só há candidatos quando a janela macro do BTC está aberta (Reset).
    if safe:
        for m in metrics:
            if m["symbol"] == "BTCUSDT":
                continue
            if (m.get("score") or 0) < min_score:
                continue
            try:
                e = json.loads(m.get("raw_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                e = {}
            chk = core.entry_checklist(e)
            grade, _cls, escore = core.setup_grade(chk, safe)
            if grade not in allowed:
                continue
            if core.is_trap(e):
                continue
            candidates.append({
                "symbol": m["symbol"],
                "asset": m["symbol"].replace("USDT", ""),
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
    persistence = await repo.get_toi_persistence(pool, snapshot_limit=30, top_n=30)
    total_snaps = await repo.count_snapshots(pool, limit=30)

    rows = [m for m in metrics if m["symbol"] != "BTCUSDT" and m.get("toi") is not None]
    rows.sort(key=lambda m: _f(m.get("toi")) or 0.0, reverse=True)

    out = []
    for m in rows[:limit]:
        out.append({
            "symbol": m["symbol"],
            "asset": m["symbol"].replace("USDT", ""),
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
    rows = await repo.get_top_appearances(pool, top_n=top_n, snapshot_limit=snapshot_limit)
    out = [
        {
            "symbol": r["symbol"],
            "asset": r["symbol"].replace("USDT", ""),
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
    rows = await repo.get_symbol_panel_history(pool, symbol.upper(), limit=limit)
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
        "symbol": symbol.upper(),
        "asset": symbol.upper().replace("USDT", ""),
        "history": out,
    })
