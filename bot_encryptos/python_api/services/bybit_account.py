from __future__ import annotations

import hashlib
import hmac
import time
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


async def get_wallet_balance() -> dict[str, bool | float | str | None]:
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        return _disconnected("Bybit API credentials are not configured.")

    timestamp_ms = str(int(time.time() * 1000))
    params = {
        "accountType": "UNIFIED",
        "coin": "USDT",
    }
    query_string = urlencode(params)
    signature = _sign(query_string, timestamp_ms)

    headers = {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-TIMESTAMP": timestamp_ms,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": _RECV_WINDOW,
    }

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
