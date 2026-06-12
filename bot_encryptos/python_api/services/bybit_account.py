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


async def get_wallet_balance() -> dict[str, float | str | None]:
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        raise RuntimeError("Bybit API credentials are not configured.")

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

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(
            f"{BYBIT_BASE_URL}/v5/account/wallet-balance?{query_string}",
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()

    if payload.get("retCode") != 0:
        raise RuntimeError(payload.get("retMsg") or "Bybit wallet-balance request failed.")

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
        "account_type": account.get("accountType"),
        "coin": "USDT",
        "capital": capital,
        "balance": balance,
        "equity": coin_equity,
        "wallet_balance": coin_wallet_balance,
        "total_wallet_balance": total_wallet_balance,
        "total_available_balance": total_available_balance,
    }
