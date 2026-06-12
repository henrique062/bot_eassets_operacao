from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from config import BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_BASE_URL

_RECV_WINDOW = "5000"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sign(query_string: str, timestamp_ms: str) -> str:
    payload = f"{timestamp_ms}{BYBIT_API_KEY}{_RECV_WINDOW}{query_string}"
    return hmac.new(
        BYBIT_API_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _headers(query_string: str, timestamp_ms: str) -> dict[str, str]:
    return {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-TIMESTAMP": timestamp_ms,
        "X-BAPI-SIGN": _sign(query_string, timestamp_ms),
        "X-BAPI-RECV-WINDOW": _RECV_WINDOW,
    }


def _disconnected(error: str) -> dict[str, bool | float | str | None]:
    return {
        "connected": False,
        "error": error,
        "account_type": None,
        "coin": "USDT",
        "capital": None,
        "balance": None,
        "equity": None,
        "wallet_balance": None,
        "total_wallet_balance": None,
        "total_available_balance": None,
    }


def _positions_disconnected(error: str) -> dict[str, object]:
    return {
        "connected": False,
        "error": error,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "positions": [],
    }


async def _signed_get(path: str, params: dict[str, str]) -> dict:
    timestamp_ms = str(int(time.time() * 1000))
    query_string = urlencode(params)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(
            f"{BYBIT_BASE_URL}{path}?{query_string}",
            headers=_headers(query_string, timestamp_ms),
        )
        response.raise_for_status()
        return response.json()


async def get_wallet_balance() -> dict[str, bool | float | str | None]:
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        return _disconnected("Bybit API credentials are not configured.")

    timestamp_ms = str(int(time.time() * 1000))
    params = {
        "accountType": "UNIFIED",
        "coin": "USDT",
    }
    query_string = urlencode(params)
    headers = _headers(query_string, timestamp_ms)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{BYBIT_BASE_URL}/v5/account/wallet-balance?{query_string}",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        try:
            payload = exc.response.json()
            message = payload.get("retMsg") or payload.get("ret_msg")
        except Exception:
            message = None
        return _disconnected(message or f"Bybit returned HTTP {exc.response.status_code}.")
    except Exception as exc:
        return _disconnected(f"Failed to fetch Bybit balance: {exc}")

    if payload.get("retCode") != 0:
        return _disconnected(payload.get("retMsg") or "Bybit wallet-balance request failed.")

    account = (payload.get("result", {}).get("list") or [{}])[0]
    coins = account.get("coin") or []
    usdt = next((coin for coin in coins if coin.get("coin") == "USDT"), {})

    total_wallet_balance = _to_float(account.get("totalWalletBalance"))
    total_available_balance = _to_float(account.get("totalAvailableBalance"))
    coin_wallet_balance = _to_float(usdt.get("walletBalance"))
    coin_equity = _to_float(usdt.get("equity"))

    capital = total_wallet_balance or coin_wallet_balance or coin_equity or 0.0
    balance = total_available_balance or coin_wallet_balance or coin_equity or capital

    return {
        "connected": True,
        "error": None,
        "account_type": account.get("accountType"),
        "coin": "USDT",
        "capital": capital,
        "balance": balance,
        "equity": coin_equity,
        "wallet_balance": coin_wallet_balance,
        "total_wallet_balance": total_wallet_balance,
        "total_available_balance": total_available_balance,
    }


async def get_open_positions() -> dict[str, object]:
    """Return current open USDT perpetual positions from Bybit."""
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        return _positions_disconnected("Bybit API credentials are not configured.")

    try:
        payload = await _signed_get(
            "/v5/position/list",
            {
                "category": "linear",
                "settleCoin": "USDT",
            },
        )
    except httpx.HTTPStatusError as exc:
        try:
            payload = exc.response.json()
            message = payload.get("retMsg") or payload.get("ret_msg")
        except Exception:
            message = None
        return _positions_disconnected(
            message or f"Bybit returned HTTP {exc.response.status_code}."
        )
    except Exception as exc:
        return _positions_disconnected(f"Failed to fetch Bybit positions: {exc}")

    if payload.get("retCode") != 0:
        return _positions_disconnected(payload.get("retMsg") or "Bybit position request failed.")

    rows = payload.get("result", {}).get("list") or []
    positions: list[dict[str, object]] = []
    for row in rows:
        size = _to_float(row.get("size")) or 0.0
        if size <= 0:
            continue

        side = row.get("side") or ""
        direction = "LONG" if side == "Buy" else "SHORT" if side == "Sell" else side.upper()
        entry_price = _to_float(row.get("avgPrice")) or 0.0
        mark_price = _to_float(row.get("markPrice"))
        value = _to_float(row.get("positionValue"))
        if value is None and entry_price:
            value = size * entry_price

        pnl = _to_float(row.get("unrealisedPnl"))
        margin = _to_float(row.get("positionIM"))
        pnl_pct = (pnl / margin * 100.0) if pnl is not None and margin else None
        created_ms = int(_to_float(row.get("createdTime")) or 0)
        updated_ms = int(_to_float(row.get("updatedTime")) or 0)

        positions.append({
            "id": f"bybit:{row.get('symbol')}:{row.get('positionIdx', 0)}",
            "symbol": row.get("symbol"),
            "direction": direction,
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "mark_price": mark_price,
            "liquidation_price": _to_float(row.get("liqPrice")),
            "value": value or 0.0,
            "leverage": _to_float(row.get("leverage")),
            "unrealised_pnl": pnl,
            "pnl_pct": pnl_pct,
            "open_timestamp": created_ms // 1000 if created_ms else None,
            "updated_at": (
                datetime.fromtimestamp(updated_ms / 1000, tz=timezone.utc).isoformat()
                if updated_ms
                else None
            ),
        })

    positions.sort(key=lambda p: float(p.get("value") or 0.0), reverse=True)
    return {
        "connected": True,
        "error": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "positions": positions,
    }
