"""
BANCADA PHOENIX — Binance USDM Futures live feed (REST polling)

Estratégia de polling:
  ticker/24hr   (bulk)  a cada 3s  → preço + variação 24h
  premiumIndex  (bulk)  a cada 5s  → funding rate
  openInterest  (por símbolo) 30s  → OI em USD
  LSR           (por símbolo) 60s  → Long/Short Ratio
"""

import logging
import threading
import time

import requests

log = logging.getLogger(__name__)

# ── STORE ──────────────────────────────────────────────────────────────────────
# { "ETHUSDT": { price, price_change_pct, fr, oi_usd, oi_trend, lsr, lsr_trend, ts } }
_data:       dict = {}
_prev_oi:    dict = {}   # oi_usd anterior p/ calcular oi_trend
_lock             = threading.Lock()
_tracked:    set  = set()
_started          = False

FAPI = "https://fapi.binance.com"


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

def set_tracked(symbols: list):
    global _tracked
    with _lock:
        _tracked = {s for s in symbols if s.endswith("USDT")}
    log.info(f"[feed] tracking {len(_tracked)} symbols")


def get_all() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _data.items()}


def get_symbol(sym: str) -> dict:
    with _lock:
        return dict(_data.get(sym, {}))


def is_live() -> bool:
    with _lock:
        if not _data:
            return False
        return any(v.get("ts", 0) > 0 for v in _data.values())


def merge_into_coin(symbol: str, coin: dict) -> dict:
    """Retorna cópia do coin dict com valores live da Binance sobrepostos."""
    live = get_symbol(symbol)
    if not live:
        return dict(coin)

    merged = dict(coin)
    if live.get("price"):
        merged["price"] = live["price"]
    if live.get("price_change_pct") is not None:
        merged["price_change:1D"] = live["price_change_pct"]
    if live.get("fr") is not None:
        merged["fr"] = live["fr"]
    if live.get("oi_usd") is not None:
        merged["oi:5m"] = live["oi_usd"]
    if live.get("oi_trend") is not None:
        merged["oi_trend:5m"] = live["oi_trend"]
    if live.get("lsr") is not None:
        merged["lsr:5m"] = live["lsr"]
    if live.get("lsr_trend") is not None:
        merged["lsr_trend:5m"] = live["lsr_trend"]
    return merged


# ── POLLING LOOPS ──────────────────────────────────────────────────────────────

def _poll_ticker():
    """Preço + variação 24h a cada 3s (1 chamada bulk)."""
    while True:
        try:
            r = requests.get(f"{FAPI}/fapi/v1/ticker/24hr", timeout=6)
            if r.ok:
                now = time.time()
                with _lock:
                    for item in r.json():
                        sym = item.get("symbol", "")
                        if not sym:
                            continue
                        d = _data.setdefault(sym, {})
                        d["price"]            = float(item.get("lastPrice") or 0)
                        d["price_change_pct"] = float(item.get("priceChangePercent") or 0)
                        d["ts"]               = now
        except Exception as e:
            log.debug(f"[feed] ticker error: {e}")
        time.sleep(3)


def _poll_premium():
    """Funding Rate a cada 5s (1 chamada bulk)."""
    while True:
        try:
            r = requests.get(f"{FAPI}/fapi/v1/premiumIndex", timeout=6)
            if r.ok:
                with _lock:
                    for item in r.json():
                        sym = item.get("symbol", "")
                        if not sym:
                            continue
                        _data.setdefault(sym, {})["fr"] = float(item.get("lastFundingRate") or 0)
        except Exception as e:
            log.debug(f"[feed] premium error: {e}")
        time.sleep(5)


def _poll_oi():
    """Open Interest em USD a cada 30s por símbolo rastreado."""
    while True:
        syms = list(_tracked)
        for sym in syms:
            try:
                r = requests.get(
                    f"{FAPI}/fapi/v1/openInterest",
                    params={"symbol": sym},
                    timeout=5,
                )
                if r.ok:
                    oi_qty = float(r.json().get("openInterest") or 0)
                    with _lock:
                        price    = _data.get(sym, {}).get("price", 1) or 1
                        oi_usd   = oi_qty * price
                        prev_oi  = _prev_oi.get(sym, oi_usd)
                        oi_trend = (oi_usd - prev_oi) / prev_oi * 100 if prev_oi else 0
                        _prev_oi[sym] = oi_usd
                        d = _data.setdefault(sym, {})
                        d["oi_usd"]  = oi_usd
                        d["oi_trend"] = oi_trend
            except Exception:
                pass
            time.sleep(0.15)
        time.sleep(30)


def _poll_lsr():
    """Long/Short Ratio + tendência a cada 60s por símbolo rastreado."""
    while True:
        syms = list(_tracked)
        for sym in syms:
            try:
                r = requests.get(
                    f"{FAPI}/futures/data/globalLongShortAccountRatio",
                    params={"symbol": sym, "period": "5m", "limit": 2},
                    timeout=5,
                )
                if r.ok:
                    rows = r.json()
                    if rows:
                        lsr   = float(rows[0].get("longShortRatio") or 1)
                        prev  = float(rows[1].get("longShortRatio") or lsr) if len(rows) >= 2 else lsr
                        trend = (lsr - prev) / prev * 100 if prev else 0
                        with _lock:
                            d = _data.setdefault(sym, {})
                            d["lsr"]       = lsr
                            d["lsr_trend"] = trend
            except Exception:
                pass
            time.sleep(0.2)
        time.sleep(60)


# ── START ───────────────────────────────────────────────────────────────────────

def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_poll_ticker,  daemon=True, name="ph-ticker").start()
    threading.Thread(target=_poll_premium, daemon=True, name="ph-fr").start()
    threading.Thread(target=_poll_oi,      daemon=True, name="ph-oi").start()
    threading.Thread(target=_poll_lsr,     daemon=True, name="ph-lsr").start()
    log.info("[feed] REST polling threads started")
