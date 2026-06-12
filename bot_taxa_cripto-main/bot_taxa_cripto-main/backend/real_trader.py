"""
Real Trading Live — Execução real de Funding Rate Sniping via CCXT.
Baseado na estrutura do Paper Trader, mas efetua chamadas reais de API e lida com ordens reais.
"""

import asyncio
import time
import json
import math
import aiohttp
from datetime import datetime, timezone, timedelta

from loguru import logger
import ccxt.async_support as ccxt
import database as db
import price_feed as pf
from cachetools import TTLCache
from scoring import enrich_with_score
from scoring_counter_trend import enrich_with_score_counter_trend
BRT = timezone(timedelta(hours=-3))

_sessions: dict[int, dict] = {}

# Cache de símbolos auto (TTL 8s)
_auto_symbols_cache = TTLCache(maxsize=256, ttl=8)


def _normalize_symbols(raw_symbols) -> list[str]:
    symbols = []
    for raw in (raw_symbols or []):
        s = str(raw or "").strip().upper()
        if not s:
            continue
        if not s.endswith(("USDT", "USDC")):
            s = f"{s}USDT"
        if s not in symbols:
            symbols.append(s)
    return symbols


def _clamp_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clamp_float(value, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize_operation_mode(raw_mode) -> str:
    mode = str(raw_mode or "manual").strip().lower()
    # Motivo: aceitar novo modo pós-virada que segue a direção recomendada do funding.
    if mode not in {"manual", "auto_expiring", "auto_strongest", "auto_highest_rate", "counter_trend", "post_funding_follow"}:
        return "manual"
    return mode


def _normalize_direction_mode(raw_direction) -> str:
    direction = str(raw_direction or "both").strip().lower()
    if direction not in {"long", "short", "both"}:
        return "both"
    return direction


def _build_auto_strategy(cfg: dict | None) -> dict:
    raw = cfg or {}
    mode = _normalize_operation_mode(raw.get("operationMode"))
    auto_mode_flag = bool(raw.get("autoMode", False))
    if mode == "manual" and auto_mode_flag:
        mode = "auto_strongest"

    direction = _normalize_direction_mode(raw.get("autoDirection"))
    max_symbols = _clamp_int(raw.get("autoMaxSymbols"), default=8, minimum=1, maximum=30)
    min_score = _clamp_float(raw.get("autoMinScore"), default=50.0, minimum=0.0, maximum=100.0)
    # Motivo: permitir filtro configuravel de funding minimo por sessao (em %).
    min_funding_rate_pct = _clamp_float(
        raw.get("minFundingRatePct"),
        default=0.06,
        minimum=0.0,
        maximum=5.0,
    )
    window_minutes = _clamp_int(raw.get("autoWindowMinutes"), default=60, minimum=5, maximum=240)
    preselected_symbols = _normalize_symbols(raw.get("preselectedSymbols"))

    return {
        "mode": mode,
        "direction": direction,
        "maxSymbols": max_symbols,
        "minScore": min_score,
        "minFundingRatePct": min_funding_rate_pct,
        "windowMinutes": window_minutes,
        "preselectedSymbols": preselected_symbols,
        "preselectedKey": str(raw.get("preselectedKey") or ""),
        "ctSortCriteria": raw.get("ctSortCriteria", "score"),
        "user_id": raw.get("user_id"),
    }


def _auto_strategy_key(exchange: str, strategy: dict) -> str:
    return (
        f"{exchange.lower()}|{strategy.get('mode','manual')}|{strategy.get('direction','both')}"
        f"|{int(strategy.get('maxSymbols', 8))}|{float(strategy.get('minScore', 50.0)):.2f}"
        f"|{float(strategy.get('minFundingRatePct', 0.001)):.6f}"
        f"|{int(strategy.get('windowMinutes', 60))}|{strategy.get('ctSortCriteria', 'score')}"
    )


def _funding_direction(rate_item: dict) -> str:
    fr = float(rate_item.get("fundingRate", 0) or 0)
    if fr > 0:
        return "SHORT"
    if fr < 0:
        return "LONG"
    return "NEUTRO"


def _direction_allowed(direction_mode: str, trade_direction: str) -> bool:
    if direction_mode == "both":
        return True
    if direction_mode == "long":
        return trade_direction == "LONG"
    if direction_mode == "short":
        return trade_direction == "SHORT"
    return True


def _sort_auto_candidates(mode: str, candidates: list[dict], **kwargs) -> list[dict]:
    if mode == "auto_expiring":
        return sorted(
            candidates,
            key=lambda c: (
                c.get("msLeft", 10**12),
                -float(c.get("score", 0)),
                -abs(float(c.get("fundingRatePercent", 0))),
            ),
        )

    if mode == "auto_highest_rate":
        return sorted(
            candidates,
            key=lambda c: -abs(float(c.get("fundingRatePercent", 0))),
        )

    if mode == "counter_trend":
        sort_criteria = kwargs.get("sort_criteria", "score")
        if sort_criteria == "funding_rate":
            return sorted(
                candidates,
                key=lambda c: (
                    -abs(float(c.get("fundingRatePercent", 0))),
                    -float(c.get("score", 0)),
                ),
            )
        return sorted(
            candidates,
            key=lambda c: (
                -float(c.get("score", 0)),
                -abs(float(c.get("fundingRatePercent", 0))),
                c.get("msLeft", 10**12),
            ),
        )

    # strongest
    return sorted(
        candidates,
        key=lambda c: (
            -float(c.get("score", 0)),
            -abs(float(c.get("fundingRatePercent", 0))),
            c.get("msLeft", 10**12),
        ),
    )


async def _resolve_auto_symbols(service, exchange: str, strategy: dict, prefer_preselected: bool = True) -> list[str]:
    mode = strategy.get("mode", "manual")
    if mode == "manual":
        return []

    key = _auto_strategy_key(exchange, strategy)
    cached = _auto_symbols_cache.get(key)
    if cached is not None:
        return list(cached)

    preselected_key = strategy.get("preselectedKey", "")
    preselected = _normalize_symbols(strategy.get("preselectedSymbols", []))
    if prefer_preselected and preselected and preselected_key and preselected_key == key:
        selected = preselected[: int(strategy.get("maxSymbols", 8))]
        _auto_symbols_cache[key] = selected
        return list(selected)

    rates = await service.get_all_funding_rates()
    if mode == "counter_trend":
        rates = await enrich_with_score_counter_trend(rates)
    else:
        rates = await enrich_with_score(rates)

    now_ms = int(time.time() * 1000)
    min_score = float(strategy.get("minScore", 50))
    # Motivo: aplicar filtro minimo de funding tambem na pre-selecao automatica.
    min_funding_rate_pct = float(strategy.get("minFundingRatePct", 0.001) or 0.0)
    max_symbols = int(strategy.get("maxSymbols", 8))
    direction_mode = strategy.get("direction", "both")
    window_minutes = int(strategy.get("windowMinutes", 60))
    window_ms = window_minutes * 60_000

    candidates = []
    for item in rates:
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue

        score_data = item.get("scoreData") or {}
        score = float(score_data.get("score", 0) or 0)
        fr_pct = float(item.get("fundingRatePercent", 0) or 0)
        if abs(fr_pct) < min_funding_rate_pct:
            continue

        if mode == "counter_trend":
            if score < min_score:
                continue
            if not bool(score_data.get("shouldOpen", False)):
                continue
            next_funding = int(item.get("nextFundingTime", 0) or 0)
            ms_left = next_funding - now_ms if next_funding > 0 else 10**12
            candidates.append({
                "symbol": symbol,
                "score": score,
                "fundingRatePercent": fr_pct,
                "msLeft": ms_left,
            })
            continue

        if mode == "auto_highest_rate":
            direction = _funding_direction(item)
            if direction == "NEUTRO" or not _direction_allowed(direction_mode, direction):
                continue
            next_funding = int(item.get("nextFundingTime", 0) or 0)
            ms_left = next_funding - now_ms if next_funding > 0 else 10**12
            candidates.append({
                "symbol": symbol,
                "score": score,
                "fundingRatePercent": fr_pct,
                "msLeft": ms_left,
            })
            continue

        if score < min_score:
            continue
        if not bool(score_data.get("shouldOpen", False)):
            continue

        direction = _funding_direction(item)
        if direction == "NEUTRO" or not _direction_allowed(direction_mode, direction):
            continue

        next_funding = int(item.get("nextFundingTime", 0) or 0)
        ms_left = next_funding - now_ms if next_funding > 0 else 10**12

        if mode == "auto_expiring":
            if next_funding <= 0:
                continue
            if ms_left <= 0 or ms_left > window_ms:
                continue

        candidates.append({
            "symbol": symbol,
            "score": score,
            "fundingRatePercent": fr_pct,
            "msLeft": ms_left,
        })

    ct_sort = strategy.get("ctSortCriteria", "score")
    sorted_candidates = _sort_auto_candidates(mode, candidates, sort_criteria=ct_sort)
    selected = [c["symbol"] for c in sorted_candidates[:max_symbols]]

    # Filtrar símbolos na blacklist ativa (apenas modos automáticos)
    user_id_bl = strategy.get("user_id")
    if user_id_bl:
        try:
            from symbol_blacklist import get_blacklisted_symbols
            blacklisted = await get_blacklisted_symbols(user_id_bl)
            if blacklisted:
                before = len(selected)
                selected = [s for s in selected if s not in blacklisted]
                if len(selected) < before:
                    print(f"[Blacklist] Filtrados {before - len(selected)} símbolo(s) bloqueados para user {user_id_bl}: {blacklisted}")
        except Exception as e:
            print(f"[Blacklist] Erro ao filtrar blacklist em _resolve_auto_symbols: {e}")

    _auto_symbols_cache[key] = selected
    return list(selected)

# Cache de mercados CCXT por exchange (TTL 1h) — evita load_markets() a cada operação
_markets_cache: dict[str, tuple[dict, float]] = {}
_MARKETS_CACHE_TTL = 3600.0

# Throttle para tentativas best-effort de resolver preço de TP limit.
_tp_price_refresh_throttle: dict[str, float] = {}
_TP_PRICE_REFRESH_TTL = 45.0

# Status de entrada limit manual pendente.
_PENDING_STATUS_PENDING = "pending"
_PENDING_STATUS_FILLED = "filled"
_PENDING_STATUS_CANCELED = "canceled"
_PENDING_STATUS_EXPIRED = "expired"
_PENDING_STATUS_REJECTED = "rejected"


async def _get_markets(ex, exchange_name: str) -> dict:
    """Retorna mercados do CCXT com cache de 1h por exchange.
    Injeta sempre no ex.markets para que price_to_precision/amount_to_precision funcionem."""
    cached = _markets_cache.get(exchange_name)
    if cached and (time.time() - cached[1]) < _MARKETS_CACHE_TTL:
        if not ex.markets:
            ex.markets = cached[0]
        return cached[0]
    markets = await ex.load_markets()
    _markets_cache[exchange_name] = (markets, time.time())
    return markets

def _fmt_ts(ts_ms=None) -> str:
    if ts_ms:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=BRT)
    else:
        dt = datetime.now(tz=BRT)
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def _safe_float(value) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if not parsed or parsed <= 0:
        return None
    return parsed


def _parse_brt_datetime_to_ms(value) -> int | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=BRT)
        return int(dt.timestamp() * 1000)
    text = str(value).strip()
    if not text:
        return None
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%y %H:%M:%S"):
        try:
            dt = datetime.strptime(text, pattern).replace(tzinfo=BRT)
            return int(dt.timestamp() * 1000)
        except Exception:
            continue
    return None


def _to_ms_timestamp(raw) -> int | None:
    if raw is None:
        return None
    try:
        ts = int(float(raw))
    except Exception:
        return None
    if ts <= 0:
        return None
    return ts if ts > 10_000_000_000 else ts * 1000


def _coerce_smallint(
    value,
    *,
    default: int,
    minimum: int,
    maximum: int,
    field: str,
    assume_ms_if_large: bool = False,
) -> int:
    """Converte para int com limite seguro de SMALLINT e fallback opcional de ms->s."""
    if value is None or value == "":
        parsed = default
    else:
        try:
            parsed = int(float(value))
        except Exception:
            raise ValueError(f"Campo '{field}' inválido. Informe um número em segundos.")

    if assume_ms_if_large and parsed > maximum and parsed % 1000 == 0:
        ms_to_s = parsed // 1000
        if minimum <= ms_to_s <= maximum:
            parsed = ms_to_s

    if parsed < minimum or parsed > maximum:
        hint = " (se enviou em ms, converta para segundos)" if assume_ms_if_large else ""
        raise ValueError(
            f"Campo '{field}' fora do intervalo permitido ({minimum}-{maximum}).{hint}"
        )
    return parsed


def _coerce_optional_non_negative_float(value, *, field: str) -> float | None:
    """Converte opcionalmente para float >= 0."""
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except Exception:
        raise ValueError(f"Campo '{field}' inválido. Informe um número.")
    if parsed < 0:
        raise ValueError(f"Campo '{field}' não pode ser negativo.")
    return parsed


def _coerce_optional_positive_float(value, *, field: str) -> float | None:
    # Motivo: alguns campos opcionais exigem valor estritamente > 0 (ex.: preço limit manual).
    parsed = _coerce_optional_non_negative_float(value, field=field)
    if parsed is not None and parsed <= 0:
        raise ValueError(f"Campo '{field}' deve ser maior que zero.")
    return parsed


def _calculate_entry_margin(position_value: float | None, leverage: int | float | None) -> float | None:
    # Motivo: padroniza cálculo da margem usada na entrada para relatórios e webhook.
    try:
        value = float(position_value)
    except Exception:
        return None
    if not math.isfinite(value) or value <= 0:
        return None

    try:
        lev = float(leverage)
    except Exception:
        lev = 0.0

    if math.isfinite(lev) and lev > 0:
        return value / lev
    return value


def _derive_entry_margin_from_total_pnl(total_pnl: float | None, total_pnl_pct: float | None) -> float | None:
    # Motivo: quando não há notional salvo no trade, deriva margem a partir do PnL% da própria operação.
    try:
        pnl = float(total_pnl)
        pct = float(total_pnl_pct)
    except Exception:
        return None
    if not math.isfinite(pnl) or not math.isfinite(pct) or abs(pct) < 1e-9:
        return None
    return abs(pnl / (pct / 100.0))


def _extract_tick_size(ex, ccxt_symbol: str) -> float | None:
    # Motivo: usar tick real da exchange para ajustar 1 tick no maker/limit sem cruzar book.
    market = (getattr(ex, "markets", None) or {}).get(ccxt_symbol) or {}
    info = market.get("info") or {}
    filters = info.get("filters") if isinstance(info, dict) else None
    if isinstance(filters, list):
        for flt in filters:
            if str((flt or {}).get("filterType", "")).upper() != "PRICE_FILTER":
                continue
            tick = _safe_float((flt or {}).get("tickSize"))
            if tick is not None:
                return tick

    precision_price = (market.get("precision") or {}).get("price")
    if isinstance(precision_price, int) and precision_price >= 0:
        return 10 ** (-precision_price)
    if isinstance(precision_price, float) and precision_price > 0:
        return precision_price
    return None


def _extract_order_filled_size(order: dict) -> float:
    # Motivo: normalizar filled entre formatos CCXT/fields nativos da exchange.
    info = order.get("info") if isinstance(order, dict) else {}
    candidates = [
        (order or {}).get("filled"),
        (order or {}).get("amountFilled"),
        (info or {}).get("executedQty"),
        (info or {}).get("cumExecQty"),
        (info or {}).get("cumQty"),
    ]
    for value in candidates:
        try:
            parsed = float(value)
            if parsed > 0:
                return parsed
        except Exception:
            continue
    return 0.0


def _extract_order_fill_price(order: dict, fallback_price: float) -> float:
    # Motivo: obter preço real de preenchimento e cair para fallback seguro se a exchange não reportar average.
    info = order.get("info") if isinstance(order, dict) else {}
    candidates = [
        (order or {}).get("average"),
        (order or {}).get("price"),
        (info or {}).get("avgPrice"),
        (info or {}).get("price"),
    ]
    for value in candidates:
        try:
            parsed = float(value)
            if parsed > 0:
                return parsed
        except Exception:
            continue
    return fallback_price


def _serialize_pending_entry(row: dict) -> dict:
    # Motivo: padronizar payload do frontend para pendências de entrada limit.
    return {
        "pendingId": row.get("id"),
        "configId": row.get("config_id"),
        "symbol": row.get("symbol"),
        "direction": row.get("direction"),
        "side": row.get("side"),
        "size": float(row.get("size") or 0),
        "limitPrice": float(row.get("limit_price") or 0),
        "orderId": row.get("order_id"),
        "status": row.get("status"),
        "exchange": row.get("exchange"),
        "sessionName": row.get("session_name"),
        "operationMode": row.get("operation_mode"),
        "createdAt": row.get("created_at").isoformat() if row.get("created_at") else None,
        "updatedAt": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


async def _fetch_pending_entries_for_config(config_id: int) -> list[dict]:
    # Motivo: reutilizar consulta de pendências ativas por sessão em status/runtime.
    rows = await db.fetch(
        """
        SELECT id, config_id, exchange, symbol, direction, side, size, limit_price,
               order_id, status, user_id, created_at, updated_at
        FROM real_pending_entries
        WHERE config_id = $1
          AND status = $2
        ORDER BY created_at DESC
        """,
        config_id,
        _PENDING_STATUS_PENDING,
    )
    return [dict(r) for r in rows]


async def _upsert_pending_entry_runtime(config_id: int, payload: dict) -> None:
    # Motivo: manter cache em memória sincronizado para SSE imediato sem depender só do banco.
    sess = _sessions.get(config_id)
    if not sess:
        return
    pending_map = sess.setdefault("pending_entries", {})
    pending_id = payload.get("pendingId")
    if pending_id is None:
        return
    pending_map[pending_id] = payload


async def _remove_pending_entry_runtime(config_id: int, pending_id: int) -> None:
    sess = _sessions.get(config_id)
    if not sess:
        return
    sess.setdefault("pending_entries", {}).pop(pending_id, None)
    task = sess.setdefault("pending_tasks", {}).pop(pending_id, None)
    current_task = asyncio.current_task()
    if task and task is not current_task and not task.done():
        task.cancel()


async def _set_pending_entry_status(
    pending_id: int,
    status: str,
    *,
    last_error: str | None = None,
) -> None:
    await db.execute(
        """
        UPDATE real_pending_entries
        SET status = $1,
            last_error = $2,
            updated_at = NOW()
        WHERE id = $3
        """,
        status,
        last_error,
        pending_id,
    )


async def _close_manual_session_if_idle(config_id: int) -> None:
    # Motivo: sessão manual só deve encerrar quando não há posição aberta nem entrada limit pendente.
    row = await db.fetchrow(
        "SELECT operation_mode, active FROM real_config WHERE id = $1",
        config_id,
    )
    if not row or not row.get("active"):
        return
    operation_mode = str(row.get("operation_mode") or "manual")
    if operation_mode not in {"manual", "manual_position", "test"}:
        return

    open_count = await db.fetchval(
        "SELECT COUNT(*) FROM real_positions WHERE config_id = $1",
        config_id,
    )
    pending_count = await db.fetchval(
        """
        SELECT COUNT(*)
        FROM real_pending_entries
        WHERE config_id = $1
          AND status = $2
        """,
        config_id,
        _PENDING_STATUS_PENDING,
    )
    if int(open_count or 0) > 0 or int(pending_count or 0) > 0:
        return

    await db.execute(
        "UPDATE real_config SET active = FALSE, ended_at = NOW() WHERE id = $1",
        config_id,
    )

    sess = _sessions.get(config_id)
    if not sess:
        return

    current_task = asyncio.current_task()
    for task in list(sess.get("monitor_tasks", {}).values()):
        if task and task is not current_task and not task.done():
            task.cancel()
    for task in list(sess.get("pending_tasks", {}).values()):
        if task and task is not current_task and not task.done():
            task.cancel()
    main_task = sess.get("task")
    if main_task and main_task is not current_task and not main_task.done():
        main_task.cancel()
    sync_task = sess.get("sync_task")
    if sync_task and sync_task is not current_task and not sync_task.done():
        sync_task.cancel()
    _sessions.pop(config_id, None)


async def _log_order(
    config_id: int,
    event: str,
    level: str = "INFO",
    symbol: str = None,
    direction: str = None,
    exchange: str = None,
    message: str = None,
    details: dict = None,
) -> None:
    """Persiste um log de ordem/erro no banco para consulta posterior."""
    # Envia também para o logger global (server_logs)
    log_msg = f"[Bot #{config_id} | {event}]"
    if symbol:
        log_msg += f" [{symbol}]"
    if message:
        log_msg += f" {message}"

    if level.upper() == "ERROR":
        logger.bind(module="RealTrading").error(log_msg)
    elif level.upper() == "WARN":
        logger.bind(module="RealTrading").warning(log_msg)
    else:
        logger.bind(module="RealTrading").info(log_msg)

    try:
        await db.execute(
            """
            INSERT INTO real_order_logs
                (config_id, log_level, event, symbol, direction, exchange, message, details)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            config_id, level, event, symbol, direction, exchange, message,
            json.dumps(details) if details else None,
        )
    except Exception as e:
        print(f"[Log] Falha ao salvar log (config={config_id} event={event}): {e}")

async def _get_api_keys(exchange_name: str, user_id: int = None) -> dict:
    key_name = f"api_keys_{exchange_name.lower()}"
    # Prioridade: user_settings (por usuário) > system_settings (legado)
    if user_id is not None:
        val = await db.fetchval(
            "SELECT value FROM user_settings WHERE user_id = $1 AND key = $2",
            user_id, key_name,
        )
    else:
        val = await db.fetchval("SELECT value FROM system_settings WHERE key = $1", key_name)
    if not val:
        return {"apiKey": "", "apiSecret": ""}
    if isinstance(val, str):
        return json.loads(val)
    return val

async def _get_ccxt_exchange(exchange_name: str, user_id: int = None):
    keys = await _get_api_keys(exchange_name, user_id=user_id)
    api_key = keys.get("apiKey", "")
    api_secret = keys.get("apiSecret", "")

    if not api_key or not api_secret:
        raise ValueError(f"Chaves de API ausentes para {exchange_name}. Configure-as nas Configurações.")

    exchange_class = getattr(ccxt, exchange_name.lower())
    exchange = exchange_class({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            # Restringe carregamento de mercados apenas ao USDT-M (fapi/linear).
            # Sem isso, ccxt tenta carregar dapi (COIN-M), eapi (options) e spot
            # ao mesmo tempo, falhando toda operação quando qualquer um estiver instável.
            'fetchMarkets': ['linear'],
        }
    })
    return exchange


class LeverageConflictError(Exception):
    """Lançada quando o leverage não pode ser alterado por haver posição aberta com leverage diferente."""
    def __init__(self, current_leverage: int, configured_leverage: int):
        self.current_leverage = current_leverage
        self.configured_leverage = configured_leverage
        super().__init__(
            f"leverage_conflict: exchange={current_leverage}x configurado={configured_leverage}x"
        )


def _log_non_fatal(context: str, error: Exception) -> None:
    print(f"[RealTrading][WARN] {context}: {error}")


async def _safe_close_exchange(ex, context: str) -> None:
    if ex is None:
        return
    try:
        await ex.close()
    except Exception as e:
        _log_non_fatal(f"{context} - falha ao fechar conexão da exchange", e)


def _position_matches_direction(position: dict, direction: str) -> bool:
    contracts_raw = position.get("contracts")
    if contracts_raw is None:
        contracts_raw = position.get("info", {}).get("positionAmt")
    try:
        contracts = float(contracts_raw or 0)
    except Exception:
        return False
    if abs(contracts) <= 0:
        return False

    side = (
        position.get("side")
        or position.get("info", {}).get("positionSide")
        or ""
    ).upper()
    if direction == "LONG" and side in {"LONG", "BUY"}:
        return True
    if direction == "SHORT" and side in {"SHORT", "SELL"}:
        return True

    # Fallback por sinal da posição (ex.: positionAmt na Binance).
    if direction == "LONG":
        return contracts > 0
    return contracts < 0

# ──────────────────────────────────────────────
# Resume on startup
# ──────────────────────────────────────────────

async def maybe_resume_on_startup() -> None:
    """
    Chamado no startup do FastAPI.
    Relança loops de monitoramento de TODAS as sessões reais ativas no banco.
    """
    import binance_service
    import bybit_service

    rows = await db.fetch("SELECT * FROM real_config WHERE active=TRUE ORDER BY id")
    for row in rows:
        config_id = row["id"]

        exchange = row["exchange"] or "binance"
        service = binance_service if exchange == "binance" else bybit_service
        operation_mode = row.get("operation_mode", "manual")
        is_manual_position_mode = operation_mode in {"manual_position", "test"}

        session_cfg = {
            "symbols": list(row["symbols"] or []),
            "capital": float(row["capital"]),
            "balance": float(row["balance"]),
            "leverage": row["leverage"],
            "feeType": row["fee_type"],
            "feeRate": float(row["fee_rate"]),
            "exchange": exchange,
            "config_id": config_id,
            "user_id": row.get("user_id"),
            "stopLossPct": float(row["stop_loss_pct"]) if row.get("stop_loss_pct") is not None else None,
            "stopLossUsd": float(row["stop_loss_usd"]) if row.get("stop_loss_usd") is not None else None,
            "minProfitPct": float(row["min_profit_pct"]) if row.get("min_profit_pct") is not None else None,
            "targetTakeProfitPct": float(row["target_take_profit_pct"]) if row.get("target_take_profit_pct") is not None else None,
            "trailingStopPct": float(row["trailing_stop_pct"]) if row.get("trailing_stop_pct") is not None else None,
            "trailingStartProfitPct": float(row["trailing_start_profit_pct"]) if row.get("trailing_start_profit_pct") is not None else None,
            "breakEvenAtPct": float(row["break_even_at_pct"]) if row.get("break_even_at_pct") is not None else None,
            "partialTpPct": float(row["partial_tp_pct"]) if row.get("partial_tp_pct") is not None else None,
            "partialTpSize": float(row["partial_tp_size"]) if row.get("partial_tp_size") is not None else None,
            "entrySeconds": row.get("entry_seconds", 30),
            "exitSeconds": row.get("exit_seconds", 30),
            "makerTimeoutSeconds": row.get("maker_timeout_seconds", 8),
            "operationMode": row.get("operation_mode", "manual"),
            "autoDirection": row.get("auto_direction", "both"),
            "autoMaxSymbols": row.get("auto_max_symbols", 8),
            "autoMinScore": float(row.get("auto_min_score") or 50.0),
            "minFundingRatePct": _clamp_float(
                row.get("min_funding_rate_pct"),
                default=0.06,
                minimum=0.0,
                maximum=5.0,
            ),
            "autoWindowMinutes": row.get("auto_window_minutes", 60),
            "preselectedKey": "",
            "preselectedSymbols": [],
            "ctSortCriteria": row.get("ct_sort_criteria", "score"),
        }

        positions_rows = await db.fetch(
            "SELECT * FROM real_positions WHERE config_id=$1", config_id
        )
        positions = {
            r["symbol"]: {
                "symbol": r["symbol"],
                "direction": r["direction"],
                "entryPrice": float(r["entry_price"]),
                "size": float(r["size"]),
                "value": float(r["value"]),
                "fundingRate": float(r["funding_rate"]),
                "fundingRatePct": float(r["funding_rate_pct"]),
                "openTime": r.get("open_time"),
                "openTimestamp": r["open_timestamp"],
                "tpLimitOrderId": r.get("tp_limit_order_id") or None,
                "tpLimitPrice": _safe_float(r.get("tp_limit_price")),
            }
            for r in positions_rows
        }

        _sessions[config_id] = {
            "task": None if is_manual_position_mode else asyncio.create_task(_monitoring_loop(service, config_id, session_cfg)),
            "sync_task": asyncio.create_task(_position_sync_loop(config_id, session_cfg)),
            "config": session_cfg,
            "positions": positions,
            "pending_snipes": set(),
            # Motivo: rastrear entradas limit manuais pendentes no runtime para status SSE imediato.
            "pending_entries": {},
            "pending_tasks": {},
            "monitor_tasks": {},  # {symbol: asyncio.Task} — rastreia tasks de monitoramento por posição
        }

        # Recriar tarefas de monitoramento para posições abertas que sobreviveram ao restart
        for r in positions_rows:
            tp_limit_id = r.get("tp_limit_order_id") or None

            # Restaurar callback WS para detecção instantânea de TP fill (apenas Binance)
            tp_fill_event = None
            if tp_limit_id and session_cfg.get("exchange", "binance") == "binance":
                try:
                    keys = await _get_api_keys("binance", user_id=session_cfg.get("user_id"))
                    if keys.get("apiKey") and session_cfg.get("user_id"):
                        import binance_ws_user as _bws_user
                        ws_mgr = await _bws_user.get_or_create(session_cfg["user_id"], keys["apiKey"])
                        tp_fill_event = ws_mgr.register_tp(tp_limit_id)
                except Exception as e_ws:
                    print(f"[RealTrading] WS restore falhou para {r['symbol']}: {e_ws}")

            task = asyncio.create_task(_monitor_and_close_position(
                service, config_id,
                r["symbol"], r["direction"],
                float(r["size"]), float(r["entry_price"]),
                float(r["funding_rate"] or 0), float(r["funding_rate_pct"] or 0),
                open_order_id=str(r["open_order_id"]) if r.get("open_order_id") else None,
                tp_limit_order_id=tp_limit_id,
                tp_fill_event=tp_fill_event,
            ))
            _sessions[config_id]["monitor_tasks"][r["symbol"]] = task
            tp_info = f"TP limit id={tp_limit_id}" if tp_limit_id else "sem TP limit"
            print(f"[RealTrading]   ↳ Monitoramento retomado: {r['symbol']} ({r['direction']}) | {tp_info}")

        # Motivo: retoma também ordens limit manuais pendentes para não perder execução após restart.
        pending_rows = await _fetch_pending_entries_for_config(config_id)
        for pending_row in pending_rows:
            pending_payload = _serialize_pending_entry(pending_row)
            pending_id = pending_payload.get("pendingId")
            if pending_id is None:
                continue
            await _upsert_pending_entry_runtime(config_id, pending_payload)
            pending_task = asyncio.create_task(
                _watch_pending_manual_entry(
                    service=service,
                    config_id=config_id,
                    pending_row=pending_row,
                )
            )
            _sessions[config_id]["pending_tasks"][pending_id] = pending_task
            print(
                f"[RealTrading]   ↳ Entrada pendente retomada: "
                f"{pending_row['symbol']} ({pending_row['direction']}) id={pending_id}"
            )

        print(
            f"[RealTrading] Retomada sessão {config_id} ({row.get('session_name')}) "
            f"com {len(positions)} posições abertas e {len(pending_rows)} pendente(s)"
        )

# ──────────────────────────────────────────────
# Funções públicas (chamadas pelas rotas)
# ──────────────────────────────────────────────

async def get_status(user_id: int | None = None) -> dict:
    if user_id is not None:
        active_rows = await db.fetch(
            "SELECT * FROM real_config WHERE active = TRUE AND user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
    else:
        active_rows = await db.fetch("SELECT * FROM real_config WHERE active = TRUE ORDER BY created_at DESC")
    sessions_data = []
    for row in active_rows:
        sessions_data.append(await _build_session_status(dict(row)))

    first = sessions_data[0] if sessions_data else None
    return {
        "active": len(sessions_data) > 0,
        "sessions": sessions_data,
        "config": first["config"] if first else {},
        "balance": first["balance"] if first else 0.0,
        "positions": first["positions"] if first else {},
        "pendingEntries": first["pendingEntries"] if first else [],
        "totalTrades": first["totalTrades"] if first else 0,
        "trades": first["trades"] if first else [],
        "pnl": first["pnl"] if first else 0.0,
        "pnlPct": first["pnlPct"] if first else 0.0,
    }

async def get_session_status(session_id: int, user_id: int | None = None) -> dict:
    if user_id is not None:
        row = await db.fetchrow(
            "SELECT * FROM real_config WHERE id=$1 AND user_id=$2", session_id, user_id
        )
    else:
        row = await db.fetchrow("SELECT * FROM real_config WHERE id=$1", session_id)
    if not row:
        return {}
    return await _build_session_status(dict(row))


async def _resolve_tp_limit_price_best_effort(position_row: dict) -> float | None:
    current_price = _safe_float(position_row.get("tp_limit_price"))
    if current_price is not None:
        return current_price

    tp_limit_order_id = str(position_row.get("tp_limit_order_id") or "").strip()
    if not tp_limit_order_id:
        return None

    position_id = position_row.get("id")
    symbol = str(position_row.get("symbol") or "").upper()
    config_id = int(position_row.get("config_id") or 0)
    throttle_key = f"{config_id}:{symbol}:{tp_limit_order_id}"
    now = time.time()
    last_try = _tp_price_refresh_throttle.get(throttle_key, 0.0)
    if (now - last_try) < _TP_PRICE_REFRESH_TTL:
        return None
    _tp_price_refresh_throttle[throttle_key] = now

    exchange_name = str(position_row.get("exchange") or "binance").lower()
    user_id = position_row.get("user_id")
    ex = None
    try:
        ex = await _get_ccxt_exchange(exchange_name, user_id=user_id)
        markets = await _get_markets(ex, exchange_name)
        ccxt_symbol = _native_to_ccxt_symbol(markets, symbol) or symbol

        order = await ex.fetch_order(tp_limit_order_id, ccxt_symbol)
        resolved_price = (
            _safe_float(order.get("price"))
            or _safe_float(order.get("average"))
            or _safe_float(order.get("stopPrice"))
            or _safe_float((order.get("info") or {}).get("price"))
        )
        if resolved_price is None:
            return None

        await db.execute(
            "UPDATE real_positions SET tp_limit_price=$1 WHERE id=$2",
            resolved_price,
            position_id,
        )

        # Atualiza cache em memória para refletir rapidamente no status SSE.
        session = _sessions.get(config_id)
        if session:
            pos = session.get("positions", {}).get(symbol)
            if isinstance(pos, dict):
                pos["tpLimitOrderId"] = tp_limit_order_id
                pos["tpLimitPrice"] = resolved_price

        return resolved_price
    except Exception as e:
        _log_non_fatal(
            f"resolve tp_limit_price {config_id}/{symbol} (order={tp_limit_order_id})",
            e,
        )
        return None
    finally:
        await _safe_close_exchange(
            ex,
            f"_resolve_tp_limit_price_best_effort config_id={config_id} symbol={symbol}",
        )


async def get_chart_operations(
    *,
    exchange: str,
    symbol: str | None,
    user_id: int,
    limit_closed: int = 20,
) -> dict:
    exchange_name = str(exchange or "binance").lower()
    if exchange_name not in {"binance", "bybit"}:
        raise ValueError(f"Exchange inválida: {exchange_name}")

    # Motivo: endpoint agora atende dois cenários:
    # - símbolo específico (overlays do gráfico)
    # - visão global (painel com todos os pares)
    normalized_symbol = str(symbol or "").upper().strip() or None

    try:
        limit_closed_int = int(limit_closed)
    except Exception:
        raise ValueError("Parâmetro 'limit_closed' inválido.")
    limit_closed_int = max(1, min(100, limit_closed_int))

    # Motivo: manter query eficiente e explícita para cada modo (por símbolo x global).
    if normalized_symbol:
        open_query_with_tp = """
            SELECT
                p.id, p.config_id, p.symbol, p.direction, p.entry_price, p.size, p.value,
                p.open_time, p.open_timestamp, p.tp_limit_order_id, p.tp_limit_price,
                c.session_name, c.operation_mode, c.exchange, c.user_id, c.leverage
            FROM real_positions p
            INNER JOIN real_config c ON c.id = p.config_id
            WHERE c.user_id = $1
              AND c.active = TRUE
              AND c.exchange = $2
              AND p.symbol = $3
            ORDER BY p.open_timestamp DESC
        """
        open_query_legacy = """
            SELECT
                p.id, p.config_id, p.symbol, p.direction, p.entry_price, p.size, p.value,
                p.open_time, p.open_timestamp, p.tp_limit_order_id,
                NULL::NUMERIC AS tp_limit_price,
                c.session_name, c.operation_mode, c.exchange, c.user_id, c.leverage
            FROM real_positions p
            INNER JOIN real_config c ON c.id = p.config_id
            WHERE c.user_id = $1
              AND c.active = TRUE
              AND c.exchange = $2
              AND p.symbol = $3
            ORDER BY p.open_timestamp DESC
        """
        open_params = (user_id, exchange_name, normalized_symbol)
    else:
        open_query_with_tp = """
            SELECT
                p.id, p.config_id, p.symbol, p.direction, p.entry_price, p.size, p.value,
                p.open_time, p.open_timestamp, p.tp_limit_order_id, p.tp_limit_price,
                c.session_name, c.operation_mode, c.exchange, c.user_id, c.leverage
            FROM real_positions p
            INNER JOIN real_config c ON c.id = p.config_id
            WHERE c.user_id = $1
              AND c.active = TRUE
              AND c.exchange = $2
            ORDER BY p.open_timestamp DESC
        """
        open_query_legacy = """
            SELECT
                p.id, p.config_id, p.symbol, p.direction, p.entry_price, p.size, p.value,
                p.open_time, p.open_timestamp, p.tp_limit_order_id,
                NULL::NUMERIC AS tp_limit_price,
                c.session_name, c.operation_mode, c.exchange, c.user_id, c.leverage
            FROM real_positions p
            INNER JOIN real_config c ON c.id = p.config_id
            WHERE c.user_id = $1
              AND c.active = TRUE
              AND c.exchange = $2
            ORDER BY p.open_timestamp DESC
        """
        open_params = (user_id, exchange_name)

    try:
        open_rows = await db.fetch(open_query_with_tp, *open_params)
    except Exception as e:
        err = str(e).lower()
        # Motivo: alguns ambientes ainda podem não ter a coluna tp_limit_price (migração pendente).
        # Fazemos fallback para query legada para não zerar o card de operações no frontend.
        if "tp_limit_price" in err and "does not exist" in err:
            open_rows = await db.fetch(open_query_legacy, *open_params)
        else:
            raise

    open_positions = []
    for row in open_rows:
        r = dict(row)
        tp_limit_order_id = r.get("tp_limit_order_id") or None
        tp_limit_price = _safe_float(r.get("tp_limit_price"))
        entry_margin = _calculate_entry_margin(r.get("value"), r.get("leverage"))
        if tp_limit_order_id and tp_limit_price is None:
            tp_limit_price = await _resolve_tp_limit_price_best_effort(r)

        open_positions.append(
            {
                "positionId": r["id"],
                "configId": r["config_id"],
                "symbol": r["symbol"],
                "sessionName": r.get("session_name") or f"Bot #{r['config_id']}",
                "operationMode": r.get("operation_mode") or "manual",
                "direction": r["direction"],
                "entryPrice": float(r["entry_price"]),
                "size": float(r["size"]),
                "value": float(r["value"]),
                "entryMargin": entry_margin,
                "openTime": r.get("open_time"),
                "openTimestamp": _to_ms_timestamp(r.get("open_timestamp")),
                "tpLimitOrderId": tp_limit_order_id,
                "tpLimitPrice": tp_limit_price,
            }
        )

    # Motivo: retornar também entradas limit pendentes para painel global da operação manual.
    if normalized_symbol:
        pending_rows = await db.fetch(
            """
            SELECT
                p.id, p.config_id, p.exchange, p.symbol, p.direction, p.side, p.size,
                p.limit_price, p.order_id, p.status, p.created_at, p.updated_at,
                c.session_name, c.operation_mode
            FROM real_pending_entries p
            INNER JOIN real_config c ON c.id = p.config_id
            WHERE c.user_id = $1
              AND c.active = TRUE
              AND c.exchange = $2
              AND p.symbol = $3
              AND p.status = $4
            ORDER BY p.created_at DESC
            """,
            user_id,
            exchange_name,
            normalized_symbol,
            _PENDING_STATUS_PENDING,
        )
    else:
        pending_rows = await db.fetch(
            """
            SELECT
                p.id, p.config_id, p.exchange, p.symbol, p.direction, p.side, p.size,
                p.limit_price, p.order_id, p.status, p.created_at, p.updated_at,
                c.session_name, c.operation_mode
            FROM real_pending_entries p
            INNER JOIN real_config c ON c.id = p.config_id
            WHERE c.user_id = $1
              AND c.active = TRUE
              AND c.exchange = $2
              AND p.status = $3
            ORDER BY p.created_at DESC
            """,
            user_id,
            exchange_name,
            _PENDING_STATUS_PENDING,
        )
    pending_entries = [_serialize_pending_entry(dict(r)) for r in pending_rows]

    if normalized_symbol:
        closed_rows = await db.fetch(
            """
            SELECT
                t.id AS trade_id, t.config_id, t.symbol, t.direction, t.entry_price, t.exit_price,
                t.total_pnl, t.total_pnl_pct, t.close_reason, t.open_time, t.close_time, t.trade_timestamp,
                c.session_name, c.operation_mode, c.leverage
            FROM real_trades t
            INNER JOIN real_config c ON c.id = t.config_id
            WHERE c.user_id = $1
              AND c.exchange = $2
              AND t.symbol = $3
            ORDER BY t.trade_timestamp DESC
            LIMIT $4
            """,
            user_id,
            exchange_name,
            normalized_symbol,
            limit_closed_int,
        )
    else:
        closed_rows = await db.fetch(
            """
            SELECT
                t.id AS trade_id, t.config_id, t.symbol, t.direction, t.entry_price, t.exit_price,
                t.total_pnl, t.total_pnl_pct, t.close_reason, t.open_time, t.close_time, t.trade_timestamp,
                c.session_name, c.operation_mode, c.leverage
            FROM real_trades t
            INNER JOIN real_config c ON c.id = t.config_id
            WHERE c.user_id = $1
              AND c.exchange = $2
            ORDER BY t.trade_timestamp DESC
            LIMIT $3
            """,
            user_id,
            exchange_name,
            limit_closed_int,
        )

    closed_operations = []
    for row in closed_rows:
        r = dict(row)
        total_pnl = float(r["total_pnl"] or 0)
        total_pnl_pct = _safe_float(r.get("total_pnl_pct"))
        entry_margin = _derive_entry_margin_from_total_pnl(total_pnl, total_pnl_pct)
        closed_operations.append(
            {
                "tradeId": r["trade_id"],
                "configId": r["config_id"],
                "symbol": r["symbol"],
                "sessionName": r.get("session_name") or f"Bot #{r['config_id']}",
                "operationMode": r.get("operation_mode") or "manual",
                "direction": r["direction"],
                "entryPrice": float(r["entry_price"] or 0),
                "exitPrice": float(r["exit_price"] or 0),
                "totalPnl": total_pnl,
                "totalPnlPct": total_pnl_pct,
                "entryMargin": entry_margin,
                "closeReason": r.get("close_reason"),
                "openTime": r.get("open_time"),
                "closeTime": r.get("close_time"),
                "openTimestamp": _parse_brt_datetime_to_ms(r.get("open_time")),
                "closeTimestamp": _to_ms_timestamp(r.get("trade_timestamp")),
                "tradeTimestamp": _to_ms_timestamp(r.get("trade_timestamp")),
            }
        )

    return {
        "success": True,
        "exchange": exchange_name,
        "symbol": normalized_symbol or "ALL",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "openPositions": open_positions,
        "pendingEntries": pending_entries,
        "closedOperations": closed_operations,
    }

async def _build_session_status(row: dict) -> dict:
    config_id = row["id"]
    capital = float(row["capital"])
    balance = float(row["balance"])
    runtime_cfg = _sessions.get(config_id, {}).get("config", {})

    trades = await db.fetch(
        """
        SELECT id, symbol, direction, entry_price AS "entryPrice", exit_price AS "exitPrice",
               funding_rate AS "fundingRate", funding_pnl AS "fundingPnl", price_pnl AS "pricePnl",
               price_pnl_pct AS "pricePnlPct",
               fee_cost AS "feeCost", total_pnl AS "totalPnl", total_pnl_pct AS "totalPnlPct",
               balance_after AS "balanceAfter", open_time AS "openTime", close_time AS "closeTime",
               trade_timestamp AS "timestamp", exchange, COALESCE(close_reason, 'funding') AS "closeReason"
        FROM real_trades
        WHERE config_id = $1 ORDER BY trade_timestamp DESC LIMIT 50
        """,
        config_id,
    )

    positions_rows = await db.fetch("SELECT * FROM real_positions WHERE config_id = $1", config_id)
    positions = {
        r["symbol"]: {
            "symbol": r["symbol"], "direction": r["direction"], "entryPrice": float(r["entry_price"]),
            "size": float(r["size"]), "value": float(r["value"]), "fundingRatePct": float(r["funding_rate_pct"]),
            "openTime": r["open_time"],
            "tpLimitOrderId": r.get("tp_limit_order_id") or None,
            "tpLimitPrice": _safe_float(r.get("tp_limit_price")),
        }
        for r in positions_rows
    }
    pending_rows = await _fetch_pending_entries_for_config(config_id)
    pending_entries = [_serialize_pending_entry(r) for r in pending_rows]
    if config_id in _sessions:
        # Motivo: manter snapshot runtime consistente com o estado persistido no banco.
        _sessions[config_id]["pending_entries"] = {
            p["pendingId"]: p for p in pending_entries if p.get("pendingId") is not None
        }

    pnl = round(balance - capital, 2)
    pnl_pct = round((pnl / capital) * 100, 2) if capital > 0 else 0.0

    return {
        "sessionId": config_id,
        "sessionName": row.get("session_name", f"Bot Real #{config_id}"),
        "active": bool(row.get("active")),
        "paused": bool(row.get("paused", False)),
        "config": {
            "symbols": list(runtime_cfg.get("symbols") or row.get("symbols") or []),
            "capital": capital,
            "leverage": row["leverage"],
            "feeType": row["fee_type"],
            "feeRate": float(row["fee_rate"]),
            # Motivo: tratar o modo pós-funding como modo automático no status da sessão.
            "autoMode": str(runtime_cfg.get("operationMode", row.get("operation_mode", "manual"))) in {"auto_expiring", "auto_strongest", "auto_highest_rate", "counter_trend", "post_funding_follow"},
            "operationMode": runtime_cfg.get("operationMode", row.get("operation_mode", "manual")),
            "autoDirection": runtime_cfg.get("autoDirection", row.get("auto_direction", "both")),
            "autoMaxSymbols": runtime_cfg.get("autoMaxSymbols", row.get("auto_max_symbols", 8)),
            "autoMinScore": runtime_cfg.get("autoMinScore", float(row.get("auto_min_score") or 50.0)),
            # Motivo: refletir no status o filtro minimo de funding para abertura de operacoes.
            "minFundingRatePct": runtime_cfg.get(
                "minFundingRatePct",
                _clamp_float(
                    row.get("min_funding_rate_pct"),
                    default=0.001,
                    minimum=0.0,
                    maximum=5.0,
                ),
            ),
            "autoWindowMinutes": runtime_cfg.get("autoWindowMinutes", row.get("auto_window_minutes", 60)),
            "exchange": row.get("exchange", "binance"),
            "stopLossPct": float(row["stop_loss_pct"]) if row.get("stop_loss_pct") is not None else None,
            "stopLossUsd": float(row["stop_loss_usd"]) if row.get("stop_loss_usd") is not None else None,
            "minProfitPct": float(row["min_profit_pct"]) if row.get("min_profit_pct") is not None else None,
            "targetTakeProfitPct": float(row["target_take_profit_pct"]) if row.get("target_take_profit_pct") is not None else None,
            "trailingStopPct": float(row["trailing_stop_pct"]) if row.get("trailing_stop_pct") is not None else None,
            "trailingStartProfitPct": runtime_cfg.get("trailingStartProfitPct", float(row["trailing_start_profit_pct"]) if row.get("trailing_start_profit_pct") is not None else None),
            "breakEvenAtPct": float(row["break_even_at_pct"]) if row.get("break_even_at_pct") is not None else None,
            "entrySeconds": row.get("entry_seconds", 30),
            "exitSeconds": row.get("exit_seconds", 30),
            "makerTimeoutSeconds": runtime_cfg.get("makerTimeoutSeconds", row.get("maker_timeout_seconds", 8)),
            "ctSortCriteria": runtime_cfg.get("ctSortCriteria", row.get("ct_sort_criteria", "score")),
            "presetName": row.get("preset_name"),
        },
        "balance": balance,
        "positions": positions,
        "pendingEntries": pending_entries,
        "totalTrades": await db.fetchval("SELECT COUNT(*) FROM real_trades WHERE config_id = $1", config_id),
        "trades": [dict(t) for t in trades],
        "pnl": pnl, "pnlPct": pnl_pct,
        "startedAt": row.get("started_at"), "endedAt": row.get("ended_at"),
    }

async def start_trading(service, exchange: str = "binance", config: dict = None) -> dict:
    cfg = config or {}
    strategy = _build_auto_strategy(cfg)
    is_manual_mode = strategy["mode"] == "manual"
    symbols = _normalize_symbols(cfg.get("symbols", []))
    if is_manual_mode and not symbols:
        raise ValueError("Selecione ao menos 1 símbolo para o modo manual.")
    if not is_manual_mode:
        symbols = await _resolve_auto_symbols(service, exchange, strategy, prefer_preselected=True)

    capital = float(cfg.get("capital", 100.0))
    leverage = int(cfg.get("leverage", 1))
    fee_type = cfg.get("feeType", "maker")
    fee_rate = 0.0002 if fee_type == "maker" else 0.0005
    stop_loss_pct = cfg.get("stopLossPct")
    stop_loss_usd = cfg.get("stopLossUsd")
    min_profit_pct = cfg.get("minProfitPct")
    target_take_profit_pct = cfg.get("targetTakeProfitPct")
    trailing_stop_pct = cfg.get("trailingStopPct")

    # Segurança: counter_trend com leverage alto sem nenhum stop é arriscado demais
    if strategy["mode"] == "counter_trend" and leverage >= 8:
        if stop_loss_pct is None and stop_loss_usd is None and trailing_stop_pct is None:
            raise ValueError(
                f"Counter-trend com leverage {leverage}x exige ao menos um stop loss configurado "
                f"(stopLossPct, stopLossUsd ou trailingStopPct). Reduza o leverage ou configure um stop."
            )
    trailing_start_profit_pct = _coerce_optional_non_negative_float(
        cfg.get("trailingStartProfitPct"),
        field="trailingStartProfitPct",
    )
    break_even_at_pct = _coerce_optional_non_negative_float(
        cfg.get("breakEvenAtPct"),
        field="breakEvenAtPct",
    )
    partial_tp_pct = _coerce_optional_non_negative_float(
        cfg.get("partialTpPct"),
        field="partialTpPct",
    )
    partial_tp_size_raw = cfg.get("partialTpSize")
    if partial_tp_size_raw is not None:
        partial_tp_size_val = float(partial_tp_size_raw)
        if partial_tp_size_val <= 0 or partial_tp_size_val > 100:
            raise ValueError("Campo 'partialTpSize' deve ser entre 1 e 100.")
    elif partial_tp_pct is not None:
        partial_tp_size_val = 50.0
    else:
        partial_tp_size_val = None
    session_name = cfg.get("sessionName", f"Real Bot {exchange.title()}")
    entry_seconds = _coerce_smallint(
        cfg.get("entrySeconds"),
        default=30,
        minimum=1,
        maximum=32767,
        field="entrySeconds",
        assume_ms_if_large=True,
    )
    if strategy["mode"] in {"counter_trend", "post_funding_follow"}:
        # Counter-trend não usa expiração por tempo de posição.
        exit_seconds = 30
    else:
        exit_seconds = _coerce_smallint(
            cfg.get("exitSeconds"),
            default=30,
            minimum=1,
            maximum=32767,
            field="exitSeconds",
            assume_ms_if_large=True,
        )
    maker_timeout_s = _coerce_smallint(
        cfg.get("makerTimeout"),
        default=8,
        minimum=2,
        maximum=900,
        field="makerTimeout",
        assume_ms_if_large=True,
    )
    ct_sort_criteria = cfg.get("ctSortCriteria", "score")
    preset_name = cfg.get("presetName")

    user_id = cfg.get("user_id")

    # Test API Keys format / connectivity
    try:
        ex_instance = await _get_ccxt_exchange(exchange, user_id=user_id)
        await ex_instance.load_markets()
        await ex_instance.close()
    except Exception as e:
        raise ValueError(f"Falha de Autenticação na {exchange}! Verifique as chaves de API.")

    config_id = await db.fetchval(
        """
        INSERT INTO real_config
            (session_name, symbols, capital, balance, leverage, fee_type, fee_rate,
             exchange, active, started_at, stop_loss_pct, min_profit_pct, target_take_profit_pct, trailing_stop_pct,
             trailing_start_profit_pct, break_even_at_pct, partial_tp_pct, partial_tp_size,
             entry_seconds, exit_seconds, user_id,
             operation_mode, auto_direction, auto_max_symbols, auto_min_score, min_funding_rate_pct, auto_window_minutes, maker_timeout_seconds, ct_sort_criteria, preset_name)
        VALUES ($1,$2,$3,$3,$4,$5,$6,$7,TRUE,NOW(),$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27)
        RETURNING id
        """,
        session_name, symbols, capital, leverage, fee_type, fee_rate, exchange,
        float(stop_loss_pct) if stop_loss_pct is not None else None,
        float(min_profit_pct) if min_profit_pct is not None else None,
        float(target_take_profit_pct) if target_take_profit_pct is not None else None,
        float(trailing_stop_pct) if trailing_stop_pct is not None else None,
        trailing_start_profit_pct,
        break_even_at_pct, partial_tp_pct, partial_tp_size_val,
        entry_seconds, exit_seconds,
        int(user_id) if user_id is not None else None,
        strategy["mode"], strategy["direction"], strategy["maxSymbols"], strategy["minScore"],
        strategy["minFundingRatePct"], strategy["windowMinutes"],
        maker_timeout_s, ct_sort_criteria, preset_name
    )

    row = await db.fetchrow("SELECT * FROM real_config WHERE id=$1", config_id)
    session_cfg = {
        "symbols": symbols if not is_manual_mode else list(row["symbols"] or []),
        "capital": float(row["capital"]),
        "balance": float(row["balance"]),
        "leverage": row["leverage"],
        "feeType": row["fee_type"],
        "feeRate": float(row["fee_rate"]),
        "exchange": exchange,
        "config_id": config_id,
        "user_id": user_id,
        "stopLossPct": float(row["stop_loss_pct"]) if row["stop_loss_pct"] is not None else None,
        "stopLossUsd": float(row["stop_loss_usd"]) if row["stop_loss_usd"] is not None else None,
        "minProfitPct": float(row["min_profit_pct"]) if row["min_profit_pct"] is not None else None,
        "targetTakeProfitPct": float(row["target_take_profit_pct"]) if row["target_take_profit_pct"] is not None else None,
        "trailingStopPct": float(row["trailing_stop_pct"]) if row["trailing_stop_pct"] is not None else None,
        "trailingStartProfitPct": float(row["trailing_start_profit_pct"]) if row.get("trailing_start_profit_pct") is not None else trailing_start_profit_pct,
        "breakEvenAtPct": float(row["break_even_at_pct"]) if row.get("break_even_at_pct") is not None else None,
        "partialTpPct": float(row["partial_tp_pct"]) if row.get("partial_tp_pct") is not None else None,
        "partialTpSize": float(row["partial_tp_size"]) if row.get("partial_tp_size") is not None else None,
        "entrySeconds": row.get("entry_seconds", 30),
        "exitSeconds": row.get("exit_seconds", 30),
        "makerTimeoutSeconds": row.get("maker_timeout_seconds", maker_timeout_s),
        "operationMode": strategy["mode"],
        "autoDirection": strategy["direction"],
        "autoMaxSymbols": strategy["maxSymbols"],
        "autoMinScore": strategy["minScore"],
        "minFundingRatePct": strategy["minFundingRatePct"],
        "autoWindowMinutes": strategy["windowMinutes"],
        "preselectedKey": strategy["preselectedKey"],
        "preselectedSymbols": strategy["preselectedSymbols"],
        "ctSortCriteria": strategy.get("ctSortCriteria", "score"),
        "presetName": preset_name,
    }

    _sessions[config_id] = {
        "task": asyncio.create_task(_monitoring_loop(service, config_id, session_cfg)),
        "sync_task": asyncio.create_task(_position_sync_loop(config_id, session_cfg)),
        "config": session_cfg,
        "positions": {},
        "pending_snipes": set(),
        # Motivo: estrutura padrão também no modo automático para manter payload de status consistente.
        "pending_entries": {},
        "pending_tasks": {},
        "monitor_tasks": {},  # {symbol: asyncio.Task} — rastreia tasks de monitoramento por posição
    }

    return await get_session_status(config_id)

async def _sync_positions_once(
    config_id: int,
    session_cfg: dict,
    *,
    include_inactive: bool = False,
    close_reason: str = "exchange_sync",
) -> dict:
    summary = {"closed_in_db": 0, "remaining_symbols": [], "errors": []}

    if not include_inactive and config_id not in _sessions:
        rows = await db.fetch("SELECT symbol FROM real_positions WHERE config_id=$1", config_id)
        summary["remaining_symbols"] = sorted({r["symbol"] for r in rows})
        return summary

    db_positions = await db.fetch(
        """
        SELECT symbol, direction, entry_price, size, value,
               funding_rate, funding_rate_pct, open_time, open_timestamp, open_order_id,
               entry_score, entry_score_breakdown
        FROM real_positions
        WHERE config_id = $1
        """,
        config_id,
    )
    if not db_positions:
        return summary

    exchange_name = str(session_cfg.get("exchange", "binance")).lower()
    user_id = session_cfg.get("user_id")
    ex = None
    try:
        ex = await _get_ccxt_exchange(exchange_name, user_id=user_id)
        markets = await _get_markets(ex, exchange_name)

        for pos_row in db_positions:
            symbol = pos_row["symbol"]
            direction = str(pos_row["direction"] or "LONG").upper()
            entry_price = float(pos_row["entry_price"] or 0)
            size = float(pos_row["size"] or 0)
            position_value = float(pos_row["value"] or 0)
            fr = float(pos_row["funding_rate"] or 0)
            fr_pct = float(pos_row["funding_rate_pct"] or 0)
            actual_open_time = pos_row["open_time"] or _fmt_ts()
            actual_open_ts = int(pos_row["open_timestamp"] or 0)
            open_order_id = str(pos_row["open_order_id"]) if pos_row["open_order_id"] else None
            sync_entry_score = pos_row["entry_score"] if "entry_score" in pos_row.keys() else None
            sync_entry_score_breakdown = pos_row["entry_score_breakdown"] if "entry_score_breakdown" in pos_row.keys() else None

            ccxt_sym = _native_to_ccxt_symbol(markets, symbol)
            if ccxt_sym is None:
                msg = f"[SyncLoop] Símbolo {symbol} não encontrado nos mercados — pulando."
                print(msg)
                summary["errors"].append(msg)
                continue

            exchange_has_position = False
            try:
                ex_positions = await ex.fetch_positions([ccxt_sym])
                exchange_has_position = any(
                    _position_matches_direction(ep, direction)
                    for ep in ex_positions
                )
            except Exception as e:
                msg = f"[SyncLoop] Erro ao consultar posição {symbol} na exchange: {e}"
                print(msg)
                summary["errors"].append(msg)
                continue

            if exchange_has_position:
                continue

            current_price = entry_price
            try:
                ticker = await ex.fetch_ticker(ccxt_sym)
                current_price = float(ticker.get("last") or entry_price)
            except Exception as e:
                _log_non_fatal(f"_sync_positions_once {config_id}/{symbol} sem preço de ticker", e)

            runtime_cfg = _sessions.get(config_id, {}).get("config", {})
            fee_rate = float(runtime_cfg.get("feeRate", session_cfg.get("feeRate", 0.0004)) or 0.0004)
            leverage = float(runtime_cfg.get("leverage", session_cfg.get("leverage", 1)) or 1)

            price_pnl = (
                (entry_price - current_price) * size
                if direction == "SHORT"
                else (current_price - entry_price) * size
            )
            fee_cost = position_value * fee_rate * 2
            funding_pnl = abs(fr) * position_value
            total_pnl = funding_pnl + price_pnl - fee_cost

            margin = position_value / leverage if leverage > 0 else position_value
            price_pnl_pct = (price_pnl / margin) * 100 if margin > 0 else 0
            total_pnl_pct = (total_pnl / margin) * 100 if margin > 0 else 0

            # Verifica se a posição ainda existe antes de registrar o trade.
            # O monitor_and_close_position pode ter deletado a linha entre a leitura
            # inicial (db_positions) e este ponto — evita duplo registro.
            still_exists = await db.fetchval(
                "SELECT 1 FROM real_positions WHERE config_id=$1 AND symbol=$2",
                config_id, symbol,
            )
            if not still_exists:
                print(
                    f"[SyncLoop] {symbol} (config {config_id}): posição já removida do DB "
                    f"por outra task — pulando registro de trade."
                )
                continue

            current_balance = float(await db.fetchval("SELECT balance FROM real_config WHERE id=$1", config_id) or 0)
            new_balance = current_balance + total_pnl

            close_ts = int(time.time() * 1000)
            trade_id = await db.fetchval(
                """
                INSERT INTO real_trades
                    (config_id, symbol, direction, entry_price, exit_price,
                     funding_rate, funding_pnl, price_pnl, price_pnl_pct, fee_cost,
                     total_pnl, total_pnl_pct, balance_after,
                     open_time, close_time, trade_timestamp, exchange, close_reason,
                     entry_score, entry_score_breakdown)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
                RETURNING id
                """,
                config_id,
                symbol,
                direction,
                entry_price,
                current_price,
                fr_pct,
                funding_pnl,
                price_pnl,
                price_pnl_pct,
                fee_cost,
                total_pnl,
                total_pnl_pct,
                new_balance,
                actual_open_time,
                _fmt_ts(close_ts),
                close_ts,
                exchange_name,
                close_reason,
                sync_entry_score,
                sync_entry_score_breakdown,
            )
            await db.execute("UPDATE real_config SET balance=$1 WHERE id=$2", new_balance, config_id)
            await db.execute("DELETE FROM real_positions WHERE config_id=$1 AND symbol=$2", config_id, symbol)

            session_ref = _sessions.get(config_id)
            if session_ref:
                session_ref["positions"].pop(symbol, None)
                session_ref["config"]["balance"] = new_balance
                session_ref["pending_snipes"].discard(symbol)
                session_ref.get("monitor_tasks", {}).pop(symbol, None)

            # Fire-and-forget: rastreia losses na blacklist inteligente
            if trade_id and user_id:
                try:
                    from symbol_blacklist import on_trade_closed as _bl_on_trade_closed
                    asyncio.create_task(_bl_on_trade_closed(user_id, symbol, config_id, total_pnl))
                except Exception:
                    pass
                # Auto-análise IA com cooldown
                asyncio.create_task(auto_ai_analyze_and_apply(config_id, user_id, "auto_cycle_end"))

            summary["closed_in_db"] += 1
            print(
                f"[SyncLoop] {symbol} sincronizado. PnL estimado: {total_pnl:.4f} USDT. "
                f"Novo saldo: {new_balance:.4f} USDT."
            )

            if trade_id:
                asyncio.create_task(
                    _reconcile_with_exchange(
                        exchange_name,
                        user_id,
                        ccxt_sym,
                        symbol,
                        config_id,
                        trade_id,
                        actual_open_ts,
                        close_ts,
                        open_order_id,
                        None,
                        position_value,
                        int(leverage) if leverage > 0 else 1,
                    )
                )

    except Exception as e:
        import traceback
        msg = f"[RealTrading] Erro no ciclo de sincronização (config_id={config_id}): {e}\n{traceback.format_exc()}"
        print(msg)
        summary["errors"].append(msg)
    finally:
        await _safe_close_exchange(ex, f"_sync_positions_once config_id={config_id}")

    remaining_rows = await db.fetch("SELECT symbol FROM real_positions WHERE config_id = $1", config_id)
    summary["remaining_symbols"] = sorted({r["symbol"] for r in remaining_rows})

    # Auto-close manual bot if all positions are closed externally
    runtime_mode = session_cfg.get("operationMode", "manual")
    pending_count = await db.fetchval(
        """
        SELECT COUNT(*)
        FROM real_pending_entries
        WHERE config_id = $1
          AND status = $2
        """,
        config_id,
        _PENDING_STATUS_PENDING,
    )
    if (
        runtime_mode in {"test", "manual", "manual_position"}
        and not summary["remaining_symbols"]
        and int(pending_count or 0) == 0
    ):
        print(f"[RealTrading] Sessão manual #{config_id} encerrada (posições fechadas externamente).")
        await _close_manual_session_if_idle(config_id)

    return summary


async def stop_trading(session_id: int, user_id: int | None = None) -> dict:
    if user_id is not None:
        row = await db.fetchrow(
            "SELECT * FROM real_config WHERE id=$1 AND user_id=$2", session_id, user_id
        )
    else:
        row = await db.fetchrow("SELECT * FROM real_config WHERE id=$1", session_id)
    if not row:
        raise ValueError("Sessão não encontrada ou sem permissão.")

    row = dict(row)
    session = _sessions.get(session_id, {})
    runtime_cfg = session.get("config", {})

    session_cfg = {
        "exchange": runtime_cfg.get("exchange", row.get("exchange", "binance")),
        "user_id": runtime_cfg.get("user_id", row.get("user_id")),
        "feeRate": runtime_cfg.get("feeRate", float(row.get("fee_rate") or 0.0004)),
        "leverage": runtime_cfg.get("leverage", int(row.get("leverage") or 1)),
        "balance": runtime_cfg.get("balance", float(row.get("balance") or 0)),
    }

    # Motivo: cancelar entradas limit pendentes antes de encerrar a sessão.
    pending_rows = await db.fetch(
        """
        SELECT id, symbol, direction, side, size, limit_price, order_id, exchange
        FROM real_pending_entries
        WHERE config_id = $1
          AND status = $2
        ORDER BY created_at DESC
        """,
        session_id,
        _PENDING_STATUS_PENDING,
    )
    if pending_rows:
        exchange_name = session_cfg.get("exchange", "binance")
        uid = session_cfg.get("user_id")
        ex_pending = None
        markets_pending = None
        try:
            ex_pending = await _get_ccxt_exchange(exchange_name, user_id=uid)
            markets_pending = await _get_markets(ex_pending, exchange_name)
        except Exception as e:
            _log_non_fatal(f"stop_trading #{session_id}: erro ao inicializar exchange para cancelar pendências", e)

        for pending in pending_rows:
            p = dict(pending)
            order_id = str(p.get("order_id") or "").strip()
            symbol = str(p.get("symbol") or "").upper()
            cancel_error = None

            if ex_pending and order_id:
                try:
                    ccxt_sym = _native_to_ccxt_symbol(markets_pending or {}, symbol) or symbol
                    await ex_pending.cancel_order(order_id, ccxt_sym)
                except Exception as e:
                    cancel_error = str(e)
                    _log_non_fatal(
                        f"stop_trading #{session_id}: falha ao cancelar pending {symbol} order={order_id}",
                        e,
                    )

            status = _PENDING_STATUS_CANCELED if cancel_error is None else _PENDING_STATUS_REJECTED
            try:
                await _set_pending_entry_status(p["id"], status, last_error=cancel_error)
                await _remove_pending_entry_runtime(session_id, int(p["id"]))
                await _log_order(
                    session_id,
                    "pending_entry_canceled",
                    "WARN" if cancel_error else "INFO",
                    symbol=symbol,
                    direction=p.get("direction"),
                    exchange=exchange_name,
                    message=f"Entrada limit pendente cancelada para {symbol}.",
                    details={
                        "pending_id": p["id"],
                        "order_id": order_id,
                        "status": status,
                        "cancel_error": cancel_error,
                    },
                )
            except Exception as e:
                _log_non_fatal(
                    f"stop_trading #{session_id}: falha ao persistir cancelamento de pending {symbol}",
                    e,
                )

        await _safe_close_exchange(ex_pending, f"stop_trading #{session_id} pending cancel")

    # Combina posições em memória e no banco para tentar fechamento market antes da reconciliação.
    positions = dict(session.get("positions", {}))
    db_positions = await db.fetch(
        "SELECT symbol, direction, size FROM real_positions WHERE config_id=$1",
        session_id,
    )
    for p in db_positions:
        positions.setdefault(
            p["symbol"],
            {
                "direction": p["direction"],
                "size": float(p["size"] or 0),
            },
        )

    if positions:
        exchange_name = session_cfg.get("exchange", "binance")
        uid = session_cfg.get("user_id")
        print(f"[RealTrading] stop_trading #{session_id}: fechando {len(positions)} posição(ões) antes de parar...")
        ex = None
        try:
            ex = await _get_ccxt_exchange(exchange_name, user_id=uid)
            mkt = await _get_markets(ex, exchange_name)
            hedge = await _is_hedge_mode(ex)

            for symbol, pos_data in positions.items():
                direction = str(pos_data.get("direction", "LONG")).upper()
                size = float(pos_data.get("size", 0) or 0)
                if size <= 0:
                    continue
                ccxt_sym = _native_to_ccxt_symbol(mkt, symbol) or symbol
                side_to_close = "sell" if direction == "LONG" else "buy"

                try:
                    await ex.cancel_all_orders(ccxt_sym)
                except Exception as e:
                    _log_non_fatal(f"stop_trading #{session_id}: falha ao cancelar ordens de {symbol}", e)

                try:
                    close_params = _order_params(direction, hedge, reduce_only=True)
                    await ex.create_market_order(ccxt_sym, side_to_close, size, params=close_params)
                    print(f"[RealTrading] stop_trading #{session_id}: {symbol} ({direction}) fechado via market.")
                except Exception as e:
                    _log_non_fatal(f"stop_trading #{session_id}: erro ao fechar {symbol}", e)
        except Exception as e:
            _log_non_fatal(f"stop_trading #{session_id}: erro ao inicializar exchange", e)
        finally:
            await _safe_close_exchange(ex, f"stop_trading #{session_id}")

    max_attempts = 6
    retry_sleep_s = 2
    sync_closed_total = 0
    sync_errors: list[str] = []
    remaining_symbols: list[str] = []

    for attempt in range(1, max_attempts + 1):
        sync_result = await _sync_positions_once(
            session_id,
            session_cfg,
            include_inactive=True,
        )
        sync_closed_total += int(sync_result.get("closed_in_db", 0) or 0)
        sync_errors.extend(sync_result.get("errors", []))
        remaining_symbols = list(sync_result.get("remaining_symbols", []))
        if not remaining_symbols:
            break
        print(
            f"[RealTrading] stop_trading #{session_id}: tentativa {attempt}/{max_attempts}, "
            f"ainda restam posições: {remaining_symbols}"
        )
        if attempt < max_attempts:
            await asyncio.sleep(retry_sleep_s)

    if remaining_symbols:
        return {
            "success": False,
            "blocked": True,
            "sessionId": session_id,
            "remainingCount": len(remaining_symbols),
            "remainingSymbols": remaining_symbols,
            "message": (
                "Parada bloqueada: ainda existem posições abertas no banco. "
                "Feche manualmente ou tente parar novamente."
            ),
            "warnings": sync_errors[-5:],
        }

    # Só encerra runtime e marca inactive quando não há mais posições abertas.
    if session_id in _sessions:
        for _, monitor_task in list(_sessions[session_id].get("monitor_tasks", {}).items()):
            if monitor_task and not monitor_task.done():
                monitor_task.cancel()
        for _, pending_task in list(_sessions[session_id].get("pending_tasks", {}).items()):
            if pending_task and not pending_task.done():
                pending_task.cancel()

        task = _sessions[session_id].get("task")
        if task and not task.done():
            task.cancel()

        sync_task = _sessions[session_id].get("sync_task")
        if sync_task and not sync_task.done():
            sync_task.cancel()

        del _sessions[session_id]

    # Libera conexão WS User Data se não houver mais bots ativos do usuário.
    if session_cfg.get("exchange", "binance") == "binance":
        uid_stop = session_cfg.get("user_id")
        if uid_stop is not None:
            remaining_ids = [
                sid for sid, payload in _sessions.items()
                if payload.get("config", {}).get("user_id") == uid_stop
            ]
            try:
                import binance_ws_user as _bws_user
                await _bws_user.release_if_no_sessions(uid_stop, remaining_ids)
            except Exception as e:
                _log_non_fatal(
                    f"stop_trading #{session_id}: erro ao liberar WS user-data de user_id={uid_stop}",
                    e,
                )

    await db.execute("UPDATE real_config SET active=FALSE, ended_at=NOW() WHERE id=$1", session_id)
    status = await get_session_status(session_id, user_id=user_id)
    status = status or {}
    status["success"] = True
    status["blocked"] = False
    status["remainingCount"] = 0
    status["remainingSymbols"] = []
    status["message"] = "Bot parado com sucesso."
    status["syncClosedInDb"] = sync_closed_total
    if sync_errors:
        status["warnings"] = sync_errors[-5:]
    return status

async def get_sessions(user_id: int | None = None) -> list[dict]:
    if user_id is not None:
        rows = await db.fetch(
            """
            SELECT pc.id, pc.session_name, pc.symbols, pc.capital, pc.balance, pc.leverage, pc.fee_type,
                pc.exchange, pc.active, pc.started_at, pc.ended_at, pc.created_at, pc.stop_loss_pct, pc.min_profit_pct, pc.target_take_profit_pct, pc.trailing_stop_pct, pc.trailing_start_profit_pct,
                pc.operation_mode, pc.auto_direction, pc.auto_max_symbols, pc.auto_min_score, pc.min_funding_rate_pct, pc.auto_window_minutes, pc.preset_name,
                COUNT(pt.id) AS total_trades,
                COALESCE(SUM(CASE WHEN pt.total_pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(CASE WHEN pt.total_pnl <= 0 THEN 1 ELSE 0 END), 0) AS losses,
                COALESCE(SUM(pt.total_pnl), 0) AS trades_pnl
            FROM real_config pc
            LEFT JOIN real_trades pt ON pt.config_id = pc.id
            WHERE pc.user_id = $1
            GROUP BY pc.id ORDER BY pc.created_at DESC
            """,
            user_id,
        )
    else:
        rows = await db.fetch("""
            SELECT pc.id, pc.session_name, pc.symbols, pc.capital, pc.balance, pc.leverage, pc.fee_type,
                pc.exchange, pc.active, pc.started_at, pc.ended_at, pc.created_at, pc.stop_loss_pct, pc.min_profit_pct, pc.target_take_profit_pct, pc.trailing_stop_pct, pc.trailing_start_profit_pct,
                pc.operation_mode, pc.auto_direction, pc.auto_max_symbols, pc.auto_min_score, pc.min_funding_rate_pct, pc.auto_window_minutes, pc.preset_name,
                COUNT(pt.id) AS total_trades,
                COALESCE(SUM(CASE WHEN pt.total_pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(CASE WHEN pt.total_pnl <= 0 THEN 1 ELSE 0 END), 0) AS losses,
                COALESCE(SUM(pt.total_pnl), 0) AS trades_pnl
            FROM real_config pc
            LEFT JOIN real_trades pt ON pt.config_id = pc.id
            GROUP BY pc.id ORDER BY pc.created_at DESC
        """)
    return [dict(r) for r in rows]

async def close_all_positions(session_id: int, user_id: int | None = None) -> dict:
    if user_id is not None:
        row = await db.fetchrow(
            "SELECT id FROM real_config WHERE id=$1 AND user_id=$2", session_id, user_id
        )
        if not row:
            raise ValueError("Sessão não encontrada ou sem permissão.")

    session = _sessions.get(session_id, {})
    session_cfg = session.get("config", {})
    positions = dict(session.get("positions", {}))

    if not positions:
        return {"closed": 0, "message": "Nenhuma posição aberta."}

    exchange_name = session_cfg.get("exchange", "binance")
    uid = session_cfg.get("user_id")
    closed_count = 0

    try:
        ex = await _get_ccxt_exchange(exchange_name, user_id=uid)
        mkt = await ex.load_markets()
        hedge = await _is_hedge_mode(ex)

        for symbol, pos_data in positions.items():
            direction = pos_data.get("direction", "LONG")
            size = float(pos_data.get("size", 0))
            ccxt_sym = _native_to_ccxt_symbol(mkt, symbol) or symbol
            side_to_close = 'sell' if direction == 'LONG' else 'buy'

            try:
                await ex.cancel_all_orders(ccxt_sym)
            except Exception as e:
                _log_non_fatal(f"close_all_positions #{session_id}: falha ao cancelar ordens de {symbol}", e)

            try:
                close_params = _order_params(direction, hedge, reduce_only=True)
                await ex.create_market_order(ccxt_sym, side_to_close, size, params=close_params)
                print(f"[RealTrading] close_all_positions #{session_id}: {symbol} ({direction}) fechado.")
                closed_count += 1
            except Exception as e:
                print(f"[RealTrading] close_all_positions #{session_id}: erro ao fechar {symbol}: {e}")

        await _safe_close_exchange(ex, f"close_all_positions #{session_id}")
    except Exception as e:
        print(f"[RealTrading] close_all_positions #{session_id}: erro ao inicializar exchange: {e}")
        return {"closed": 0, "error": str(e)}

    return {"closed": closed_count}


async def trigger_manual_trade(
    session_id: int,
    symbol: str | None = None,
    user_id: int | None = None,
) -> dict:
    """Dispara um snipe imediato em um bot ativo, marcado como trigger manual."""
    if user_id is not None:
        row = await db.fetchrow(
            """
            SELECT id, active, exchange, symbols, operation_mode
            FROM real_config
            WHERE id=$1 AND user_id=$2
            """,
            session_id,
            user_id,
        )
    else:
        row = await db.fetchrow(
            """
            SELECT id, active, exchange, symbols, operation_mode
            FROM real_config
            WHERE id=$1
            """,
            session_id,
        )
    if not row:
        raise ValueError("Sessão não encontrada ou sem permissão.")
    if not row.get("active"):
        raise ValueError("A sessão não está ativa.")

    session = _sessions.get(session_id)
    if not session:
        raise ValueError("Sessão ativa não carregada no runtime. Reinicie o bot e tente novamente.")

    session_cfg = session.get("config", {})
    session_symbols = [
        str(s).upper()
        for s in (session_cfg.get("symbols") or row.get("symbols") or [])
        if str(s or "").strip()
    ]
    if not session_symbols:
        raise ValueError("Este bot não possui símbolos configurados para disparo.")

    selected_symbol = str(symbol or session_symbols[0]).upper().strip()
    if selected_symbol not in session_symbols:
        raise ValueError(f"Símbolo '{selected_symbol}' não pertence a este bot.")

    positions = session.get("positions", {})
    if selected_symbol in positions:
        raise ValueError(f"Já existe posição aberta para {selected_symbol}.")

    pending = session.setdefault("pending_snipes", set())
    if selected_symbol in pending:
        raise ValueError(f"{selected_symbol} já está com disparo pendente.")

    exchange_name = str(session_cfg.get("exchange") or row.get("exchange") or "binance").lower()
    operation_mode = str(session_cfg.get("operationMode") or row.get("operation_mode") or "manual")

    if exchange_name == "bybit":
        import bybit_service as service
    else:
        import binance_service as service

    pending.add(selected_symbol)
    await _log_order(
        session_id,
        "manual_trigger",
        "INFO",
        symbol=selected_symbol,
        exchange=exchange_name,
        message=f"Disparo manual solicitado para {selected_symbol}",
        details={"trigger_type": "manual", "operation_mode": operation_mode},
    )

    task = None
    try:
        if operation_mode == "counter_trend":
            rates = await service.get_all_funding_rates()
            symbol_data = next((r for r in rates if r["symbol"] == selected_symbol), None)
            if not symbol_data:
                raise ValueError(f"Símbolo {selected_symbol} não encontrado nos rates da exchange.")
            prev_fr = float(symbol_data.get("fundingRate", 0) or 0.0)
            task = asyncio.create_task(
                _execute_counter_trend_snipe(
                    service,
                    selected_symbol,
                    session_id,
                    0,
                    prev_fr,
                    force_immediate=True,
                    trigger_type="manual",
                )
            )
        elif operation_mode == "post_funding_follow":
            # Motivo: no disparo manual, usar a direção recomendada do funding atual, sem inverter.
            rates = await service.get_all_funding_rates()
            symbol_data = next((r for r in rates if r["symbol"] == selected_symbol), None)
            if not symbol_data:
                raise ValueError(f"Símbolo {selected_symbol} não encontrado nos rates da exchange.")
            prev_fr = float(symbol_data.get("fundingRate", 0) or 0.0)
            prev_fr_pct = float(symbol_data.get("fundingRatePercent", 0) or 0.0)
            task = asyncio.create_task(
                _execute_snipe(
                    service,
                    selected_symbol,
                    session_id,
                    0,
                    force_immediate=True,
                    trigger_type="manual",
                    entry_timing="after_funding_follow",
                    reference_funding_rate=prev_fr,
                    reference_funding_rate_pct=prev_fr_pct,
                )
            )
        else:
            task = asyncio.create_task(
                _execute_snipe(
                    service,
                    selected_symbol,
                    session_id,
                    0,
                    force_immediate=True,
                    trigger_type="manual",
                )
            )

        session.setdefault("monitor_tasks", {})[selected_symbol] = task
    except Exception:
        pending.discard(selected_symbol)
        raise

    return {
        "success": True,
        "message": f"Disparo manual enviado para {selected_symbol}.",
        "sessionId": session_id,
        "symbol": selected_symbol,
        "triggerType": "manual",
        "operationMode": operation_mode,
    }


async def edit_session(session_id: int, config: dict, user_id: int | None = None) -> dict:
    """Edita configurações de uma sessão ativa (stop loss, min profit, nome)."""
    if user_id is not None:
        row = await db.fetchrow(
            "SELECT id FROM real_config WHERE id=$1 AND user_id=$2", session_id, user_id
        )
        if not row:
            raise ValueError("Sessão não encontrada ou sem permissão.")
    mode_row = await db.fetchrow("SELECT operation_mode FROM real_config WHERE id=$1", session_id)
    mode_from_db = (mode_row or {}).get("operation_mode")
    mode_from_runtime = _sessions.get(session_id, {}).get("config", {}).get("operationMode")
    operation_mode = mode_from_runtime or mode_from_db or "manual"
    # Motivo: ediÃ§Ã£o de exitSeconds deve ser bloqueada para modos sem timeout.
    is_no_timeout_mode = operation_mode in {"counter_trend", "post_funding_follow"}

    updates = []
    params = []
    idx = 1

    if "stopLossPct" in config:
        updates.append(f"stop_loss_pct = ${idx}")
        params.append(float(config["stopLossPct"]) if config["stopLossPct"] is not None else None)
        idx += 1
    if "stopLossUsd" in config:
        updates.append(f"stop_loss_usd = ${idx}")
        params.append(float(config["stopLossUsd"]) if config["stopLossUsd"] is not None else None)
        idx += 1
    if "minProfitPct" in config:
        updates.append(f"min_profit_pct = ${idx}")
        params.append(float(config["minProfitPct"]) if config["minProfitPct"] is not None else None)
        idx += 1
    if "targetTakeProfitPct" in config:
        updates.append(f"target_take_profit_pct = ${idx}")
        params.append(float(config["targetTakeProfitPct"]) if config["targetTakeProfitPct"] is not None else None)
        idx += 1
    if "trailingStopPct" in config:
        updates.append(f"trailing_stop_pct = ${idx}")
        params.append(float(config["trailingStopPct"]) if config["trailingStopPct"] is not None else None)
        idx += 1
    if "trailingStartProfitPct" in config:
        updates.append(f"trailing_start_profit_pct = ${idx}")
        params.append(_coerce_optional_non_negative_float(
            config.get("trailingStartProfitPct"),
            field="trailingStartProfitPct",
        ))
        idx += 1
    if "breakEvenAtPct" in config:
        updates.append(f"break_even_at_pct = ${idx}")
        params.append(_coerce_optional_non_negative_float(config.get("breakEvenAtPct"), field="breakEvenAtPct"))
        idx += 1
    if "partialTpPct" in config:
        updates.append(f"partial_tp_pct = ${idx}")
        params.append(_coerce_optional_non_negative_float(config.get("partialTpPct"), field="partialTpPct"))
        idx += 1
    if "partialTpSize" in config:
        updates.append(f"partial_tp_size = ${idx}")
        val = float(config["partialTpSize"]) if config["partialTpSize"] is not None else None
        params.append(val)
        idx += 1
    if "sessionName" in config:
        updates.append(f"session_name = ${idx}")
        params.append(str(config["sessionName"]))
        idx += 1
    if "capital" in config:
        # Quando atualizamos o capital, precisamos ajustar o saldo (balance += (novo_capital - capital_antigo))
        # O PnL continua = saldo atual - capital
        updates.append(f"capital = ${idx}")
        params.append(float(config["capital"]))
        idx += 1
        updates.append(f"balance = balance + (${idx-1} - capital)")
    parsed_entry_seconds = None
    parsed_exit_seconds = None
    parsed_maker_timeout = None
    parsed_min_funding_rate_pct = None

    if "entrySeconds" in config:
        parsed_entry_seconds = _coerce_smallint(
            config.get("entrySeconds"),
            default=30,
            minimum=1,
            maximum=32767,
            field="entrySeconds",
            assume_ms_if_large=True,
        )
        updates.append(f"entry_seconds = ${idx}")
        params.append(parsed_entry_seconds)
        idx += 1
    if "exitSeconds" in config and not is_no_timeout_mode:
        parsed_exit_seconds = _coerce_smallint(
            config.get("exitSeconds"),
            default=30,
            minimum=1,
            maximum=32767,
            field="exitSeconds",
            assume_ms_if_large=True,
        )
        updates.append(f"exit_seconds = ${idx}")
        params.append(parsed_exit_seconds)
        idx += 1
    if "makerTimeoutSeconds" in config:
        parsed_maker_timeout = _coerce_smallint(
            config.get("makerTimeoutSeconds"),
            default=8,
            minimum=2,
            maximum=900,
            field="makerTimeoutSeconds",
            assume_ms_if_large=True,
        )
        updates.append(f"maker_timeout_seconds = ${idx}")
        params.append(parsed_maker_timeout)
        idx += 1
    if "autoMaxSymbols" in config:
        updates.append(f"auto_max_symbols = ${idx}")
        params.append(int(config["autoMaxSymbols"]))
        idx += 1
    if "autoMinScore" in config:
        updates.append(f"auto_min_score = ${idx}")
        params.append(float(config["autoMinScore"]))
        idx += 1
    if "minFundingRatePct" in config:
        # Motivo: permitir ajuste do minimo de funding tambem na edicao do bot.
        parsed_min_funding_rate_pct = _clamp_float(
            config.get("minFundingRatePct"),
            default=0.001,
            minimum=0.0,
            maximum=5.0,
        )
        updates.append(f"min_funding_rate_pct = ${idx}")
        params.append(parsed_min_funding_rate_pct)
        idx += 1
    if "ctSortCriteria" in config:
        updates.append(f"ct_sort_criteria = ${idx}")
        params.append(str(config["ctSortCriteria"]))
        idx += 1
    if "paused" in config:
        updates.append(f"paused = ${idx}")
        params.append(bool(config["paused"]))
        idx += 1

    if updates:
        params.append(session_id)
        await db.execute(
            f"UPDATE real_config SET {', '.join(updates)}, updated_at=NOW() WHERE id=${idx}",
            *params,
        )
        if session_id in _sessions:
            sess_cfg = _sessions[session_id]["config"]
            if "stopLossPct" in config: sess_cfg["stopLossPct"] = config["stopLossPct"]
            if "stopLossUsd" in config: sess_cfg["stopLossUsd"] = config["stopLossUsd"]
            if "minProfitPct" in config: sess_cfg["minProfitPct"] = config["minProfitPct"]
            if "targetTakeProfitPct" in config: sess_cfg["targetTakeProfitPct"] = config["targetTakeProfitPct"]
            if "trailingStopPct" in config: sess_cfg["trailingStopPct"] = config["trailingStopPct"]
            if "trailingStartProfitPct" in config:
                sess_cfg["trailingStartProfitPct"] = _coerce_optional_non_negative_float(
                    config.get("trailingStartProfitPct"),
                    field="trailingStartProfitPct",
                )
            if "breakEvenAtPct" in config:
                sess_cfg["breakEvenAtPct"] = _coerce_optional_non_negative_float(config.get("breakEvenAtPct"), field="breakEvenAtPct")
            if "partialTpPct" in config:
                sess_cfg["partialTpPct"] = _coerce_optional_non_negative_float(config.get("partialTpPct"), field="partialTpPct")
            if "partialTpSize" in config:
                sess_cfg["partialTpSize"] = float(config["partialTpSize"]) if config["partialTpSize"] is not None else None
            if "capital" in config:
                diff = float(config["capital"]) - sess_cfg["capital"]
                sess_cfg["capital"] = float(config["capital"])
                sess_cfg["balance"] += diff
            if "entrySeconds" in config and parsed_entry_seconds is not None: sess_cfg["entrySeconds"] = parsed_entry_seconds
            if "exitSeconds" in config and parsed_exit_seconds is not None: sess_cfg["exitSeconds"] = parsed_exit_seconds
            if "makerTimeoutSeconds" in config and parsed_maker_timeout is not None: sess_cfg["makerTimeoutSeconds"] = parsed_maker_timeout
            if "autoMaxSymbols" in config: sess_cfg["autoMaxSymbols"] = int(config["autoMaxSymbols"])
            if "autoMinScore" in config: sess_cfg["autoMinScore"] = float(config["autoMinScore"])
            if "minFundingRatePct" in config and parsed_min_funding_rate_pct is not None:
                sess_cfg["minFundingRatePct"] = parsed_min_funding_rate_pct
            if "ctSortCriteria" in config: sess_cfg["ctSortCriteria"] = str(config["ctSortCriteria"])
            if "paused" in config: sess_cfg["paused"] = bool(config["paused"])

    return await get_session_status(session_id)


# ──────────────────────────────────────────────────────────────
# Auto-análise IA contínua (fire-and-forget, com cooldown)
# ──────────────────────────────────────────────────────────────

_AUTO_ANALYZE_COOLDOWN: dict[int, datetime] = {}
AUTO_ANALYZE_MIN_MINUTES = 30


async def auto_ai_analyze_and_apply(config_id: int, user_id: int, trigger_type: str = "auto_cycle_end") -> None:
    """
    Analisa automaticamente o bot após um ciclo e aplica sugestões da IA se houver mudanças.
    Fire-and-forget — nunca quebra o fluxo de trading.
    Cooldown de AUTO_ANALYZE_MIN_MINUTES minutos entre análises por bot.
    """
    try:
        import json as _json
        from ai_service import analyze_bot_cycle

        # 1. Cooldown
        now = datetime.now(timezone.utc)
        last = _AUTO_ANALYZE_COOLDOWN.get(config_id)
        if last and (now - last).total_seconds() < AUTO_ANALYZE_MIN_MINUTES * 60:
            return
        _AUTO_ANALYZE_COOLDOWN[config_id] = now

        # 2. Busca config + últimos 50 trades
        row = await db.fetchrow("SELECT * FROM real_config WHERE id=$1 AND user_id=$2", config_id, user_id)
        if not row:
            return
        trades_rows = await db.fetch(
            "SELECT * FROM real_trades WHERE config_id=$1 ORDER BY id DESC LIMIT 50", config_id
        )
        if len(trades_rows) < 3:
            return  # Dados insuficientes

        # 3. Busca último histórico para comparação
        last_hist = await db.fetchrow(
            "SELECT * FROM bot_ai_config_history WHERE config_id=$1 ORDER BY created_at DESC LIMIT 1", config_id
        )

        # 4. Preenche perf_after do histórico anterior (se ainda não avaliado)
        if last_hist and not last_hist["perf_evaluated_at"]:
            after_trades = await db.fetch(
                "SELECT total_pnl FROM real_trades WHERE config_id=$1 AND created_at > $2 LIMIT 10",
                config_id, last_hist["created_at"],
            )
            if after_trades:
                pnl_after = sum(float(t["total_pnl"] or 0) for t in after_trades)
                await db.execute(
                    "UPDATE bot_ai_config_history SET perf_pnl_after=$1, perf_trades_after=$2, perf_evaluated_at=NOW() WHERE id=$3",
                    pnl_after, len(after_trades), last_hist["id"],
                )

        # 5. Monta contexto de histórico para o prompt da IA
        history_context = ""
        if last_hist:
            changes = last_hist["changes_applied"]
            if isinstance(changes, str):
                changes = _json.loads(changes)
            pnl_after_val = last_hist.get("perf_pnl_after")
            pnl_str = f"+${pnl_after_val:.2f}" if pnl_after_val else "ainda não avaliado"
            history_context = (
                f"Última alteração automática ({last_hist['trigger_type']}): "
                f"{_json.dumps(changes)} — desempenho após: {pnl_str} "
                f"em {last_hist.get('perf_trades_after', 0)} trades."
            )

        # 6. Monta bot_config e trades para análise
        bot_config = {
            "operationMode": row["operation_mode"],
            "exchange": row["exchange"],
            "capital": float(row["capital"] or 0),
            "leverage": row["leverage"],
            "feeType": row["fee_type"],
            "entrySeconds": row.get("entry_seconds", 30),
            "exitSeconds": row.get("exit_seconds", 30),
            "stopLossPct": float(row["stop_loss_pct"]) if row.get("stop_loss_pct") is not None else None,
            "minProfitPct": float(row["min_profit_pct"]) if row.get("min_profit_pct") is not None else None,
            "trailingStartProfitPct": float(row["trailing_start_profit_pct"]) if row.get("trailing_start_profit_pct") is not None else None,
            "autoMaxSymbols": row.get("auto_max_symbols", 8),
            "makerTimeoutSeconds": row.get("maker_timeout_seconds", 8),
            "symbols": list(row["symbols"] or []),
        }
        trades = [
            {
                "symbol": t["symbol"],
                "direction": t["direction"],
                "totalPnl": float(t["total_pnl"] or 0),
                "totalPnlPct": float(t["total_pnl_pct"] or 0),
                "fundingPnl": float(t["funding_pnl"] or 0),
                "pricePnl": float(t["price_pnl"] or 0),
                "pricePnlPct": float(t["price_pnl_pct"] or 0),
                "feeCost": float(t["fee_cost"] or 0),
                "closeReason": t["close_reason"],
                "openTime": str(t.get("open_time") or ""),
                "closeTime": str(t.get("close_time") or ""),
            }
            for t in trades_rows
        ]
        perf_pnl_before = sum(float(t["total_pnl"] or 0) for t in trades_rows[:10])

        # 7. Chama IA
        result = await analyze_bot_cycle(
            bot_config, trades, trigger_type=trigger_type, history_context=history_context
        )
        suggested = result.get("suggested_config", {})

        # 8. Salva análise no banco
        analysis_id = await db.fetchval(
            "INSERT INTO bot_ai_analyses (config_id, analysis_text, suggested_config, trigger_type) VALUES ($1,$2,$3::jsonb,$4) RETURNING id",
            config_id, result.get("analysis", ""), _json.dumps(suggested), trigger_type,
        )

        # 9. Extrai valores (formato {value, reason}) e aplica mudanças
        if suggested:
            flat_suggested = {k: (v["value"] if isinstance(v, dict) and "value" in v else v) for k, v in suggested.items()}
            changes_applied = {}
            for param, new_val in flat_suggested.items():
                old_val = bot_config.get(param)
                if old_val != new_val:
                    changes_applied[param] = {"from": old_val, "to": new_val}

            if changes_applied:
                await edit_session(config_id, flat_suggested, user_id=user_id)
                await db.execute("UPDATE bot_ai_analyses SET applied=TRUE, applied_at=NOW() WHERE id=$1", analysis_id)
                await db.execute(
                    """
                    INSERT INTO bot_ai_config_history
                    (config_id, analysis_id, trigger_type, changes_applied, perf_pnl_before, perf_trades_before, prev_history_id)
                    VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7)
                    """,
                    config_id, analysis_id, trigger_type, _json.dumps(changes_applied),
                    perf_pnl_before, min(10, len(trades_rows)),
                    last_hist["id"] if last_hist else None,
                )
                logger.info(f"[AutoAI] Bot #{config_id} analisado ({trigger_type}). Mudanças: {list(changes_applied.keys())}")
            else:
                logger.info(f"[AutoAI] Bot #{config_id} analisado ({trigger_type}). Sem mudanças necessárias.")
        else:
            logger.info(f"[AutoAI] Bot #{config_id} analisado ({trigger_type}). IA não sugeriu alterações.")

    except Exception as e:
        logger.warning(f"[AutoAI] Erro análise automática bot #{config_id}: {e}")


async def delete_session(session_id: int, user_id: int | None = None) -> dict:
    """Deleta uma sessão de real trading inativa."""
    row = await db.fetchrow("SELECT active FROM real_config WHERE id=$1", session_id)
    if not row:
        raise ValueError("Sessão não encontrada")
    if row["active"]:
        raise ValueError("Não é possível deletar sessão ativa. Pare-a primeiro.")
    if user_id is not None:
        owner = await db.fetchrow(
            "SELECT id FROM real_config WHERE id=$1 AND user_id=$2", session_id, user_id
        )
        if not owner:
            raise ValueError("Sem permissão para deletar esta sessão.")
    await db.execute("DELETE FROM real_config WHERE id=$1", session_id)
    return {"success": True, "message": "Sessão deletada com sucesso"}


# ──────────────────────────────────────────────
# Loop de monitoramento e execução de snipes
# ──────────────────────────────────────────────

async def _is_hedge_mode(ex) -> bool:
    """Detecta se a conta Binance está em Hedge Mode (dual side position)."""
    try:
        resp = await ex.fapiPrivateGetPositionSideDual()
        return bool(resp.get('dualSidePosition', False))
    except Exception:
        return False


def _order_params(direction: str, hedge_mode: bool, reduce_only: bool = False) -> dict:
    """Retorna os params corretos para a ordem dependendo do modo da conta."""
    if hedge_mode:
        return {'positionSide': direction}  # 'LONG' ou 'SHORT'
    return {'reduceOnly': True} if reduce_only else {}


async def _set_leverage_and_margin(ex, symbol, leverage):
    try:
        await ex.set_leverage(leverage, symbol)
    except Exception as e:
        err_msg = str(e).lower()
        # Detecta erro de leverage bloqueado por posição aberta (Binance: -4028/-4142, Bybit similar)
        is_blocked = any(kw in err_msg for kw in [
            "open position", "position exist", "leverage not modified",
            "4028", "4142",
        ])
        if is_blocked:
            try:
                positions = await ex.fetch_positions([symbol])
                for pos in positions:
                    pos_lev = pos.get("leverage")
                    pos_size = abs(float(
                        pos.get("contracts") or
                        pos.get("info", {}).get("positionAmt", 0) or
                        pos.get("info", {}).get("size", 0) or
                        0
                    ))
                    if pos_lev is not None and pos_size > 0:
                        actual_lev = int(float(pos_lev))
                        if actual_lev != int(leverage):
                            raise LeverageConflictError(actual_lev, int(leverage))
            except LeverageConflictError:
                raise  # propaga para o caller tratar
            except Exception as inner:
                _log_non_fatal(f"_set_leverage_and_margin {symbol}: fetch_positions", inner)
        _log_non_fatal(f"_set_leverage_and_margin {symbol}: set_leverage", e)
    try:
        await ex.set_margin_mode('isolated', symbol)
    except Exception as e:
        _log_non_fatal(f"_set_leverage_and_margin {symbol}: set_margin_mode", e)

async def _place_order(
    ex, ccxt_symbol: str, side: str, size: float,
    fee_type: str, direction: str, hedge_mode: bool,
    timeout_s: int = 8,
    config_id: int | None = None,
    exchange_name: str | None = None,
) -> dict:
    """
    Cria ordem respeitando o fee_type:
    - taker → market order (execução imediata)
    - maker → limit GTX (post-only) no bid/ask; fallback para market se
              não preencher dentro de timeout_s segundos.
    Retorna o dict da ordem executada.
    """
    base_params = _order_params(direction, hedge_mode)
    native_symbol = str(ccxt_symbol).replace("/", "").replace(":USDT", "").replace(":USD", "")

    if fee_type != 'maker':
        return await ex.create_market_order(ccxt_symbol, side, size, params=base_params)

    # Maker: limit post-only no bid/ask com ajuste de 1 tick para não cruzar o book.
    ticker = await ex.fetch_ticker(ccxt_symbol)
    bid = float(ticker.get("bid") or 0)
    ask = float(ticker.get("ask") or 0)
    last = float(ticker.get("last") or 0)

    base_price = bid if side == "buy" else ask
    if base_price <= 0:
        base_price = last
    if base_price <= 0:
        return await ex.create_market_order(ccxt_symbol, side, size, params=base_params)

    tick_size = _extract_tick_size(ex, ccxt_symbol)
    if side == "buy" and ask > 0:
        # Motivo: garante que ordem de compra maker fique estritamente abaixo do ask.
        if tick_size is not None:
            base_price = min(base_price, ask - tick_size)
        else:
            base_price = min(base_price, ask * 0.99999)
    elif side == "sell" and bid > 0:
        # Motivo: garante que ordem de venda maker fique estritamente acima do bid.
        if tick_size is not None:
            base_price = max(base_price, bid + tick_size)
        else:
            base_price = max(base_price, bid * 1.00001)

    if base_price <= 0:
        return await ex.create_market_order(ccxt_symbol, side, size, params=base_params)

    try:
        price = float(ex.price_to_precision(ccxt_symbol, base_price))
    except Exception:
        price = base_price

    if side == "buy" and ask > 0 and price >= ask and tick_size is not None:
        price = float(ex.price_to_precision(ccxt_symbol, max(ask - tick_size, tick_size)))
    if side == "sell" and bid > 0 and price <= bid and tick_size is not None:
        price = float(ex.price_to_precision(ccxt_symbol, bid + tick_size))

    if price <= 0:
        return await ex.create_market_order(ccxt_symbol, side, size, params=base_params)

    maker_params = {**base_params, 'timeInForce': 'GTX'}
    order = None
    try:
        order = await ex.create_limit_order(ccxt_symbol, side, size, price, params=maker_params)
        print(f"[Order] Maker limit {side} {size} {ccxt_symbol} @ {price} — aguardando preenchimento...")

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            await asyncio.sleep(1)
            info = await ex.fetch_order(order['id'], ccxt_symbol)
            status = info.get('status', '')
            if status in ('closed', 'filled'):
                print(f"[Order] Maker preenchida.")
                return info
            if status in ('canceled', 'cancelled', 'expired', 'rejected'):
                order = None
                break

        # Timeout — cancela e faz fallback para market
        if order:
            try:
                await ex.cancel_order(order['id'], ccxt_symbol)
                # Aguarda 1s para Binance liberar a margem reservada pela ordem cancelada
                # antes de tentar o market order (evita -2019 Margin is insufficient)
                await asyncio.sleep(1)
            except Exception as e:
                _log_non_fatal(f"_place_order {ccxt_symbol}: falha ao cancelar maker order", e)
        print(f"[Order] Maker não preenchida em {timeout_s}s, usando market (taker).")
        if config_id is not None:
            await _log_order(
                config_id,
                "maker_fallback",
                "WARN",
                symbol=native_symbol,
                direction=direction,
                exchange=exchange_name,
                message=f"Maker não preenchida em {timeout_s}s, usando market (taker).",
                details={
                    "order_id": order.get("id") if isinstance(order, dict) else None,
                    "timeout_s": timeout_s,
                    "side": side,
                    "price": price,
                    "reason": "timeout",
                },
            )
    except Exception as e:
        print(f"[Order] Erro no maker order ({e}), usando market (taker).")
        if config_id is not None:
            await _log_order(
                config_id,
                "maker_fallback",
                "WARN",
                symbol=native_symbol,
                direction=direction,
                exchange=exchange_name,
                message=f"Erro no maker order ({e}), usando market (taker).",
                details={
                    "order_id": order.get("id") if isinstance(order, dict) else None,
                    "timeout_s": timeout_s,
                    "side": side,
                    "price": price,
                    "reason": "create_limit_error",
                    "exception": str(e),
                },
            )

    return await ex.create_market_order(ccxt_symbol, side, size, params=base_params)


# ──────────────────────────────────────────────
# Reconciliação com dados reais da exchange
# ──────────────────────────────────────────────

async def _reconcile_with_exchange(
    exchange_name: str,
    user_id: int | None,
    ccxt_symbol: str,
    native_symbol: str,
    config_id: int,
    trade_id: int,
    open_ts_ms: int,
    close_ts_ms: int,
    open_order_id: str | None,
    close_order_id: str | None,
    position_value: float,
    leverage: int,
) -> None:
    """Reconcilia trade com dados reais da exchange (preços, fees, funding, PnL)."""
    await asyncio.sleep(5)
    ex = None
    try:
        ex = await _get_ccxt_exchange(exchange_name, user_id=user_id)
        since = max(0, open_ts_ms - 10_000)

        try:
            my_trades = await ex.fetch_my_trades(ccxt_symbol, since=since, limit=100)
        except Exception as e:
            print(f"[Reconcile] Erro fetch_my_trades trade {trade_id}: {e}")
            return

        open_trades = (
            [t for t in my_trades if str(t.get('order', '')) == str(open_order_id)]
            if open_order_id else []
        )
        close_trades = (
            [t for t in my_trades if str(t.get('order', '')) == str(close_order_id)]
            if close_order_id else []
        )

        if not open_trades and not close_trades:
            print(f"[Reconcile] Trade {trade_id}: nenhum trade encontrado na exchange.")
            return

        updates: dict = {}

        # Abertura
        fee_open = 0.0
        if open_trades:
            qty_open = sum(float(t.get('amount', 0)) for t in open_trades)
            cost_open = sum(float(t.get('cost', 0)) for t in open_trades)
            fee_open = sum(float(t.get('fee', {}).get('cost', 0) or 0) for t in open_trades)
            if qty_open > 0:
                updates['entry_price'] = cost_open / qty_open

        # Fechamento
        fee_close = 0.0
        price_pnl_real = None
        if close_trades:
            qty_close = sum(float(t.get('amount', 0)) for t in close_trades)
            cost_close = sum(float(t.get('cost', 0)) for t in close_trades)
            fee_close = sum(float(t.get('fee', {}).get('cost', 0) or 0) for t in close_trades)
            price_pnl_real = sum(
                float(t.get('info', {}).get('realizedPnl', 0) or 0) for t in close_trades
            )
            if qty_close > 0:
                updates['exit_price'] = cost_close / qty_close
            updates['price_pnl'] = price_pnl_real

        total_fee = fee_open + fee_close
        if total_fee > 0:
            updates['fee_cost'] = total_fee

        # Funding real da Binance
        # Inicializa como None: se API lançar exceção, não atualizamos (mantém valor anterior).
        # Se API retornar lista vazia, funding_pnl_real = 0.0 (sem pagamentos no período) — CORRETO.
        funding_pnl_real = None
        try:
            income_resp = await ex.fapiPrivateGetIncome(params={
                'symbol': native_symbol.upper(),
                'incomeType': 'FUNDING_FEE',
                'startTime': open_ts_ms - 1000,
                'endTime': close_ts_ms + 300_000,
                'limit': 10,
            })
            # Sempre atualiza: lista vazia = sem funding no período ($0), não a estimativa incorreta
            funding_pnl_real = sum(float(i.get('income', 0) or 0) for i in income_resp) if income_resp else 0.0
            updates['funding_pnl'] = funding_pnl_real
        except Exception as e:
            print(f"[Reconcile] Não foi possível buscar funding income: {e}")

        # Recalcula PnL total e percentuais
        if price_pnl_real is not None or funding_pnl_real is not None or total_fee > 0:
            old_row = await db.fetchrow(
                "SELECT price_pnl, funding_pnl, fee_cost, total_pnl, balance_after FROM real_trades WHERE id=$1",
                trade_id,
            )
            if old_row:
                p_pnl = updates.get('price_pnl', float(old_row['price_pnl'] or 0))
                f_pnl = updates.get('funding_pnl', float(old_row['funding_pnl'] or 0))
                f_cost = updates.get('fee_cost', float(old_row['fee_cost'] or 0))
                new_total = p_pnl + f_pnl - f_cost
                updates['total_pnl'] = new_total
                margin = position_value / leverage if leverage > 0 else position_value
                if margin > 0:
                    updates['price_pnl_pct'] = (p_pnl / margin) * 100
                    updates['total_pnl_pct'] = (new_total / margin) * 100
                # Ajusta balance_after e real_config.balance pelo delta
                old_total = float(old_row['total_pnl'] or 0)
                delta = new_total - old_total
                if abs(delta) > 0.000001:
                    new_balance_after = float(old_row['balance_after'] or 0) + delta
                    updates['balance_after'] = new_balance_after
                    await db.execute(
                        "UPDATE real_config SET balance = balance + $1 WHERE id = $2",
                        delta, config_id,
                    )

        if updates:
            set_parts = [f"{col} = ${i + 1}" for i, col in enumerate(updates)]
            params = list(updates.values())
            params.append(trade_id)
            sql = (
                f"UPDATE real_trades SET {', '.join(set_parts)}, reconciled_at = NOW() "
                f"WHERE id = ${len(params)}"
            )
            await db.execute(sql, *params)
            print(f"[Reconcile] Trade {trade_id} atualizado: {list(updates.keys())}")
        else:
            print(f"[Reconcile] Trade {trade_id}: sem dados novos para reconciliar.")

    except Exception as e:
        print(f"[Reconcile] Erro fatal ao reconciliar trade {trade_id}: {e}")
    finally:
        if ex:
            await _safe_close_exchange(ex, f"_reconcile_with_exchange trade_id={trade_id}")


async def _reconcile_and_notify(
    exchange_name: str,
    user_id: int | None,
    ccxt_symbol: str,
    native_symbol: str,
    config_id: int,
    trade_id: int,
    open_ts_ms: int,
    close_ts_ms: int,
    open_order_id: str | None,
    close_order_id: str | None,
    position_value: float,
    leverage: int,
    *,
    session_cfg: dict,
    direction: str,
    size: float,
    fr_pct: float,
    close_reason: str,
    open_time_str: str,
    close_time_str: str,
) -> None:
    """Reconcilia trade com a exchange e depois envia webhook com os valores reais do DB."""
    entry_margin = _calculate_entry_margin(position_value, leverage)
    await _reconcile_with_exchange(
        exchange_name, user_id, ccxt_symbol, native_symbol,
        config_id, trade_id, open_ts_ms, close_ts_ms,
        open_order_id, close_order_id, position_value, leverage,
    )
    # Re-lê do DB após reconciliação: se reconciliou, terá valores reais; senão, terá estimados
    row = await db.fetchrow(
        """SELECT entry_price, exit_price, price_pnl, price_pnl_pct,
                  fee_cost, funding_pnl, total_pnl, total_pnl_pct
           FROM real_trades WHERE id=$1""",
        trade_id,
    )
    if row:
        await _send_webhook('CLOSED', session_cfg, {
            "trade_id": trade_id, "symbol": native_symbol, "direction": direction,
            "entryPrice": float(row['entry_price'] or 0),
            "exitPrice": float(row['exit_price'] or 0),
            "size": size, "fundingRatePct": fr_pct,
            "fundingPnl": float(row['funding_pnl'] or 0),
            "pricePnl": float(row['price_pnl'] or 0),
            "pricePnlPct": float(row['price_pnl_pct'] or 0),
            "feeCost": float(row['fee_cost'] or 0),
            "totalPnl": float(row['total_pnl'] or 0),
            "totalPnlPct": float(row['total_pnl_pct'] or 0),
            "entryMargin": entry_margin,
            "closeReason": close_reason,
            "openTime": open_time_str, "closeTime": close_time_str,
        })


async def _replace_tp_limit(
    ex, ccxt_sym: str, symbol: str, direction: str, size: float,
    entry_price: float, position_value: float, fr: float,
    cfg: dict, config_id: int, exchange_name: str, uid: int | None,
    old_tp_order_id: str | None = None,
) -> "tuple[str | None, asyncio.Event | None]":
    """Re-coloca a TP limit order caso a anterior tenha sido cancelada externamente."""
    try:
        leverage = cfg.get("leverage", 10)
        target_take_profit_pct = cfg.get("targetTakeProfitPct")
        if not target_take_profit_pct:
            return None, None

        fee_rate = cfg.get("feeRate", 0.0002)
        margin = position_value / leverage if leverage > 0 else position_value
        fee_cost_est = position_value * fee_rate * 2
        funding_pnl = abs(fr) * position_value
        target_pnl = margin * (float(target_take_profit_pct) / 100.0)
        req_price_pnl = target_pnl - funding_pnl + fee_cost_est
        delta_price = req_price_pnl / size if size > 0 else 0
        target_price = entry_price - delta_price if direction == "SHORT" else entry_price + delta_price
        target_price = float(ex.price_to_precision(ccxt_sym, target_price))

        side_to_close = "buy" if direction == "SHORT" else "sell"
        hedge = await _is_hedge_mode(ex)
        limit_params = _order_params(direction, hedge, reduce_only=True)

        order = await ex.create_limit_order(
            ccxt_sym, side_to_close, size, target_price, params=limit_params
        )
        new_order_id = str(order.get("id", ""))
        if not new_order_id:
            raise ValueError(f"Exchange não retornou order ID ao re-colocar TP em {symbol}")

        await db.execute(
            "UPDATE real_positions SET tp_limit_order_id=$1, tp_limit_price=$2 WHERE config_id=$3 AND symbol=$4",
            new_order_id, target_price, config_id, symbol,
        )

        # Registrar no WS User Data (Binance) para detecção rápida
        new_fill_event = None
        if exchange_name == "binance" and new_order_id:
            try:
                keys = await _get_api_keys("binance", user_id=uid)
                if keys.get("apiKey") and uid:
                    import binance_ws_user as _bws_user
                    ws_mgr = await _bws_user.get_or_create(uid, keys["apiKey"])
                    # Desregistrar antiga se existir
                    if old_tp_order_id:
                        try:
                            ws_mgr.unregister_tp(old_tp_order_id)
                        except Exception:
                            pass
                    new_fill_event = ws_mgr.register_tp(new_order_id)
            except Exception as e_ws:
                print(f"[RealTrading] WS User Data indisponível para re-registro de TP: {e_ws}")

        await _log_order(
            config_id, "tp_reorder", "WARNING",
            symbol=symbol, direction=direction, exchange=exchange_name,
            message=f"TP re-colocada em {symbol}: nova ordem {new_order_id} @ {target_price:.6f} (anterior: {old_tp_order_id})",
            details={"old_order_id": old_tp_order_id, "new_order_id": new_order_id, "target_price": target_price},
        )
        return new_order_id, new_fill_event

    except Exception as e:
        await _log_order(
            config_id, "tp_reorder_failed", "ERROR",
            symbol=symbol, direction=direction, exchange=exchange_name,
            message=f"Falha ao re-colocar TP em {symbol}: {e}",
            details={"old_order_id": old_tp_order_id, "error": str(e)},
        )
        return None, None


async def _monitor_and_close_position(
    service, config_id: int, symbol: str, direction: str, size: float,
    entry_price: float, fr: float, fr_pct: float, open_order_id: str | None = None,
    tp_limit_order_id: str | None = None,
    tp_fill_event: "asyncio.Event | None" = None,
) -> None:
    close_reason = "funding"
    session_cfg_ref = _sessions.get(config_id, {}).get("config", {})
    exchange_name = session_cfg_ref.get("exchange", "bybit")
    uid = session_cfg_ref.get("user_id")

    try:
        ex = await _get_ccxt_exchange(exchange_name, user_id=uid)
    except Exception as e:
        print(f"[RealTrading] Falha auth para fechar {symbol}: {e}")
        return

    try:
        # Busca dados reais da posição antes de fechá-la
        pos_row = await db.fetchrow(
            "SELECT open_time, open_timestamp, value, open_order_id FROM real_positions WHERE config_id=$1 AND symbol=$2",
            config_id, symbol,
        )
        actual_open_time = pos_row['open_time'] if pos_row else _fmt_ts()
        actual_open_ts = int(pos_row['open_timestamp'] or 0) if pos_row else int(time.time() * 1000)
        position_value = (
            float(pos_row['value'] or (size * entry_price)) if pos_row else (size * entry_price)
        )
        open_order_id = open_order_id or (
            str(pos_row['open_order_id']) if pos_row and pos_row['open_order_id'] else None
        )

        mkt = await ex.load_markets()
        ccxt_sym = _native_to_ccxt_symbol(mkt, symbol) or symbol

        cfg = _sessions[config_id]["config"]
        runtime_mode = session_cfg_ref.get("operationMode")
        if runtime_mode is None:
            runtime_mode = await db.fetchval("SELECT operation_mode FROM real_config WHERE id=$1", config_id)
        is_counter_trend = runtime_mode == "counter_trend"
        is_post_funding_follow = runtime_mode == "post_funding_follow"
        # Motivo: timeout por tempo fica desativado em todos os modos pÃ³s-virada.
        is_no_timeout_mode = is_counter_trend or is_post_funding_follow

        entry_seconds = int(cfg.get("entrySeconds", 30))
        exit_seconds = int(cfg.get("exitSeconds", 30)) if not is_no_timeout_mode else 0
        # Motivo: no pós-funding favorável o timeout começa no open_time (não soma delay de entrada de novo).
        if is_post_funding_follow:
            target_exit_time = actual_open_ts + (exit_seconds * 1000)
        else:
            target_exit_time = actual_open_ts + (entry_seconds + exit_seconds) * 1000
        past_target_exit = False
        current_price = entry_price
        close_order_id = None
        exit_price = entry_price
        _tp_fail_count = 0  # Contador de falhas consecutivas no fetch_order da TP
        _tp_ws_check_counter = 0  # Contador para verificação periódica REST no caminho WS

        # Trailing Stop — estado inicial
        trailing_stop_pct = cfg.get("trailingStopPct")
        trailing_start_profit_pct = cfg.get("trailingStartProfitPct")
        trailing_armed = trailing_stop_pct is not None and (
            trailing_start_profit_pct is None or float(trailing_start_profit_pct) <= 0
        )
        trailing_peak_price = entry_price  # Maior preço favorável atingido (% do preço)

        # Break-Even Stop — estado inicial
        break_even_at_pct = cfg.get("breakEvenAtPct")
        break_even_activated = False
        dynamic_stop_loss_price: float | None = None

        # TP Parcial — estado inicial
        partial_tp_pct = cfg.get("partialTpPct")
        partial_tp_size_pct = float(cfg.get("partialTpSize") or 50.0)
        partial_tp_executed = False

        for _ in range(28800):
            if config_id not in _sessions:
                return

            cfg = _sessions[config_id]["config"]
            now_ms = int(time.time() * 1000)
            trailing_stop_pct = cfg.get("trailingStopPct")
            trailing_start_profit_pct = cfg.get("trailingStartProfitPct")
            break_even_at_pct = cfg.get("breakEvenAtPct")
            partial_tp_pct = cfg.get("partialTpPct")
            partial_tp_size_pct = float(cfg.get("partialTpSize") or 50.0)

            if tp_limit_order_id:
                if tp_fill_event is not None:
                    # Caminho rápido: aguarda evento WebSocket com timeout de 1s
                    try:
                        await asyncio.wait_for(tp_fill_event.wait(), timeout=1.0)
                        import binance_ws_user as _bws_user
                        mgr = _bws_user._connections.get(uid)
                        ws_fill_price = mgr.get_fill_price(tp_limit_order_id) if mgr else None
                        exit_price = ws_fill_price or current_price
                        close_order_id = tp_limit_order_id
                        close_reason = "take_profit_target"
                        print(f"[RealTrading] TP Limit preenchida via WS! {symbol} @ {exit_price}")
                        break
                    except asyncio.TimeoutError:
                        _tp_ws_check_counter += 1
                        # A cada 60s, verificar via REST se a TP ainda está ativa
                        if _tp_ws_check_counter >= 60:
                            _tp_ws_check_counter = 0
                            try:
                                tp_ord_check = await ex.fetch_order(tp_limit_order_id, ccxt_sym)
                                if tp_ord_check.get('status') in ('closed', 'filled'):
                                    print(f"[RealTrading] TP detectada via check periódico WS! {symbol}")
                                    exit_price = float(tp_ord_check.get('average') or tp_ord_check.get('price') or current_price)
                                    close_order_id = tp_limit_order_id
                                    close_reason = "take_profit_target"
                                    break
                                elif tp_ord_check.get('status') == 'canceled':
                                    await _log_order(
                                        config_id, "tp_cancelled", "WARNING",
                                        symbol=symbol, direction=direction, exchange=exchange_name,
                                        message=f"TP cancelada externamente (WS check) em {symbol}: {tp_limit_order_id}. Tentando recolocar...",
                                        details={"order_id": tp_limit_order_id},
                                    )
                                    new_id, new_event = await _replace_tp_limit(
                                        ex, ccxt_sym, symbol, direction, size,
                                        entry_price, position_value, fr, cfg,
                                        config_id, exchange_name, uid,
                                        old_tp_order_id=tp_limit_order_id,
                                    )
                                    if new_id:
                                        tp_limit_order_id = new_id
                                        tp_fill_event = new_event
                                    else:
                                        tp_limit_order_id = None
                                        tp_fill_event = None
                            except Exception:
                                pass  # Será tentado novamente nos próximos 60s
                else:
                    # Fallback REST (Bybit ou WS indisponível)
                    try:
                        tp_ord = await ex.fetch_order(tp_limit_order_id, ccxt_sym)
                        if tp_ord.get('status') in ('closed', 'filled'):
                            print(f"[RealTrading] TP Limit preenchida! {symbol}")
                            exit_price = float(tp_ord.get('average') or tp_ord.get('price') or current_price)
                            close_order_id = tp_limit_order_id
                            close_reason = "take_profit_target"
                            break
                        elif tp_ord.get('status') == 'canceled':
                            # TP foi cancelada externamente — logar e tentar recolocar
                            await _log_order(
                                config_id, "tp_cancelled", "WARNING",
                                symbol=symbol, direction=direction, exchange=exchange_name,
                                message=f"TP cancelada externamente (REST) em {symbol}: {tp_limit_order_id}. Tentando recolocar...",
                                details={"order_id": tp_limit_order_id},
                            )
                            new_id, new_event = await _replace_tp_limit(
                                ex, ccxt_sym, symbol, direction, size,
                                entry_price, position_value, fr, cfg,
                                config_id, exchange_name, uid,
                                old_tp_order_id=tp_limit_order_id,
                            )
                            if new_id:
                                tp_limit_order_id = new_id
                                tp_fill_event = new_event
                            else:
                                tp_limit_order_id = None
                                tp_fill_event = None
                        _tp_fail_count = 0  # Reset ao ter sucesso na chamada
                    except Exception as _tp_rest_err:
                        _tp_fail_count += 1
                        # Rate limit: backoff exponencial para não agravar 429
                        _err_str = str(_tp_rest_err).lower()
                        if "429" in _err_str or "too many requests" in _err_str or "rate limit" in _err_str:
                            _backoff = min(2 ** min(_tp_fail_count, 6), 64)  # cap 64s
                            await asyncio.sleep(_backoff)
                        # A cada 5 falhas consecutivas (~5s), verificar se posição ainda existe na exchange
                        if _tp_fail_count % 5 == 0:
                            try:
                                ex_pos = await ex.fetch_positions([ccxt_sym])
                                pos_exists = any(
                                    abs(float(p.get('contracts') or p.get('info', {}).get('positionAmt') or 0)) > 0
                                    and (p.get('side') or '').upper() == direction
                                    for p in ex_pos
                                )
                                if not pos_exists:
                                    # Posição fechada na exchange (TP preenchida, mas fetch_order indisponível)
                                    print(f"[RealTrading] TP detectada via fetch_positions: {symbol} não tem posição aberta.")
                                    close_order_id = tp_limit_order_id
                                    close_reason = "take_profit_target"
                                    break
                            except Exception as e:
                                _log_non_fatal(
                                    f"_monitor_and_close_position {config_id}/{symbol}: fallback fetch_positions do TP",
                                    e,
                                )

            try:
                ticker = await ex.fetch_ticker(ccxt_sym)
                current_price = float(ticker.get('last') or entry_price)
            except Exception as e:
                _log_non_fatal(
                    f"_monitor_and_close_position {config_id}/{symbol}: fetch_ticker",
                    e,
                )

            price_pnl = ((entry_price - current_price) * size if direction == "SHORT" else (current_price - entry_price) * size)
            fee_cost = position_value * session_cfg_ref.get("feeRate", 0.0004) * 2
            funding_pnl = abs(fr) * position_value
            total_pnl = funding_pnl + price_pnl - fee_cost
            leverage = cfg.get("leverage", 10)
            margin = position_value / leverage if leverage > 0 else position_value
            price_pnl_pct = (price_pnl / margin) * 100 if margin > 0 else 0
            total_pnl_pct = (total_pnl / margin) * 100 if margin > 0 else 0

            # Break-Even Automático: quando lucro de preço >= X%, move SL dinâmico para o entry price
            if break_even_at_pct is not None and not break_even_activated and price_pnl_pct >= float(break_even_at_pct):
                break_even_activated = True
                dynamic_stop_loss_price = entry_price
                print(f"[RealTrading] Break-Even ativado! {symbol} lucro {price_pnl_pct:.4f}% >= {break_even_at_pct}% | SL → entrada @ {entry_price:.6f}")
                await _log_order(
                    config_id, "break_even_activated", "INFO",
                    symbol=symbol, direction=direction, exchange=exchange_name,
                    message=f"Break-Even ativado em {symbol}: lucro {price_pnl_pct:.4f}% >= {break_even_at_pct}% | SL movido para entrada @ {entry_price:.6f}",
                    details={"price_pnl_pct": price_pnl_pct, "break_even_at_pct": break_even_at_pct, "entry_price": entry_price},
                )

            # TP Parcial: fecha X% da posição quando lucro de preço >= alvo
            if partial_tp_pct is not None and not partial_tp_executed and price_pnl_pct >= float(partial_tp_pct):
                try:
                    partial_size = size * (partial_tp_size_pct / 100.0)
                    partial_size = float(ex.amount_to_precision(ccxt_sym, partial_size))
                    if partial_size > 0:
                        hedge = await _is_hedge_mode(ex)
                        close_side = 'sell' if direction == 'LONG' else 'buy'
                        params_partial: dict = {"reduceOnly": True}
                        if hedge:
                            params_partial["positionSide"] = "LONG" if direction == "LONG" else "SHORT"
                        await ex.create_market_order(ccxt_sym, close_side, partial_size, params=params_partial)
                        size -= partial_size
                        partial_tp_executed = True
                        print(f"[RealTrading] TP Parcial: fechou {partial_tp_size_pct:.0f}% ({partial_size:.6f}) de {symbol} @ ~{current_price:.6f} | lucro {price_pnl_pct:.4f}%")
                        await _log_order(
                            config_id, "partial_tp", "INFO",
                            symbol=symbol, direction=direction, exchange=exchange_name,
                            message=f"TP Parcial executado: fechou {partial_tp_size_pct:.0f}% de {symbol} @ ~{current_price:.6f} | lucro {price_pnl_pct:.4f}%",
                            details={"partial_size": partial_size, "remaining_size": size, "price_pnl_pct": price_pnl_pct, "current_price": current_price},
                        )
                except Exception as _e_partial:
                    _log_non_fatal(f"_monitor_and_close_position {config_id}/{symbol}: TP Parcial", _e_partial)

            # Trailing Stop — baseado em % do PREÇO (todos os modos)
            if trailing_stop_pct is None:
                trailing_armed = False
            elif not trailing_armed:
                if direction == "LONG":
                    price_change_pct = (current_price - entry_price) / entry_price * 100
                else:
                    price_change_pct = (entry_price - current_price) / entry_price * 100
                if trailing_start_profit_pct is None or price_change_pct >= float(trailing_start_profit_pct):
                    trailing_armed = True
                    trailing_peak_price = current_price
                    await _log_order(
                        config_id,
                        "trailing_armed",
                        "INFO",
                        symbol=symbol,
                        direction=direction,
                        exchange=exchange_name,
                        message=f"Trailing armado em {symbol}: variação de preço {price_change_pct:.4f}% (gatilho {float(trailing_start_profit_pct or 0):.4f}%) @ {current_price:.6f}",
                        details={
                            "current_price": current_price,
                            "entry_price": entry_price,
                            "trailing_stop_pct": trailing_stop_pct,
                            "trailing_start_profit_pct": trailing_start_profit_pct,
                            "price_change_pct": price_change_pct,
                        },
                    )

            if trailing_stop_pct is not None and trailing_armed:
                if direction == "LONG":
                    if current_price > trailing_peak_price:
                        trailing_peak_price = current_price
                    drop_pct = (trailing_peak_price - current_price) / trailing_peak_price * 100
                    if drop_pct >= float(trailing_stop_pct):
                        print(f"[RealTrading] Trailing Stop disparado! {symbol} @ {current_price:.6f} | pico={trailing_peak_price:.6f} queda={drop_pct:.4f}% >= {trailing_stop_pct}%")
                        close_reason = "trailing_stop"
                        break
                else:  # SHORT: preço caindo é favorável
                    if current_price < trailing_peak_price:
                        trailing_peak_price = current_price
                    rise_pct = (current_price - trailing_peak_price) / trailing_peak_price * 100
                    if rise_pct >= float(trailing_stop_pct):
                        print(f"[RealTrading] Trailing Stop disparado! {symbol} @ {current_price:.6f} | pico={trailing_peak_price:.6f} subida={rise_pct:.4f}% >= {trailing_stop_pct}%")
                        close_reason = "trailing_stop"
                        break

            stop_loss_pct = cfg.get("stopLossPct")
            stop_loss_usd = cfg.get("stopLossUsd")

            if stop_loss_pct is not None and price_pnl_pct < -abs(stop_loss_pct):
                close_reason = "stop_loss_pct"
                break
            elif stop_loss_usd is not None and total_pnl < -abs(stop_loss_usd):
                close_reason = "stop_loss_usd"
                break

            # Break-Even Stop dinâmico: fecha se preço retornar ao entry após break-even ativado
            if dynamic_stop_loss_price is not None:
                if direction == "LONG" and current_price <= dynamic_stop_loss_price:
                    close_reason = "break_even_stop"
                    break
                elif direction == "SHORT" and current_price >= dynamic_stop_loss_price:
                    close_reason = "break_even_stop"
                    break

            # Timeout e minProfitPct — apenas para modos de sniping com funding
            # Operação manual (manual_position/test) não expira por tempo.
            if not is_no_timeout_mode and runtime_mode not in {"test", "manual_position"}:
                if not past_target_exit and now_ms >= target_exit_time:
                    past_target_exit = True
                if past_target_exit:
                    min_profit_pct = cfg.get("minProfitPct")
                    if min_profit_pct is not None:
                        if total_pnl_pct >= min_profit_pct:
                            close_reason = "funding"
                            break
                    else:
                        close_reason = "timeout"
                        break

            await asyncio.sleep(1)

        # Desregistrar callback WS independente do motivo de saída
        if tp_fill_event is not None and tp_limit_order_id:
            try:
                import binance_ws_user as _bws_user
                mgr = _bws_user._connections.get(uid)
                if mgr:
                    mgr.unregister_tp(tp_limit_order_id)
            except Exception as e:
                _log_non_fatal(
                    f"_monitor_and_close_position {config_id}/{symbol}: unregister_tp",
                    e,
                )

        if tp_limit_order_id and close_order_id != tp_limit_order_id:
            try:
                await ex.cancel_order(tp_limit_order_id, ccxt_sym)
            except Exception as e:
                _log_non_fatal(
                    f"_monitor_and_close_position {config_id}/{symbol}: cancel_order TP",
                    e,
                )
        elif tp_limit_order_id is None:
            # Posição retomada após restart sem ID de TP — cancelar ordens reduce-only residuais
            try:
                open_orders = await ex.fetch_open_orders(ccxt_sym)
                hedge_mode = await _is_hedge_mode(ex)
                for ord in open_orders:
                    is_reduce = (
                        ord.get('reduceOnly') or
                        ord.get('info', {}).get('reduceOnly') in (True, 'true') or
                        (hedge_mode and (ord.get('info', {}).get('positionSide') or '').upper() == direction)
                    )
                    if is_reduce:
                        try:
                            await ex.cancel_order(str(ord['id']), ccxt_sym)
                        except Exception as e:
                            _log_non_fatal(
                                f"_monitor_and_close_position {config_id}/{symbol}: cancel_order residual {ord.get('id')}",
                                e,
                            )
            except Exception as e:
                _log_non_fatal(
                    f"_monitor_and_close_position {config_id}/{symbol}: fetch_open_orders residual",
                    e,
                )

        if close_order_id is None:
            side_to_close = 'sell' if direction == 'LONG' else 'buy'
            hedge = await _is_hedge_mode(ex)
            fee_type = session_cfg_ref.get("feeType", "taker")
            maker_timeout = session_cfg_ref.get("makerTimeoutSeconds", 8)
            print(f"[RealTrading] Fechando {symbol} ({ccxt_sym}) hedge={hedge} fee={fee_type}... motivo: {close_reason}")
            await _log_order(config_id, "close_attempt", "INFO", symbol=symbol, direction=direction,
                             exchange=exchange_name,
                             message=f"Fechando {symbol} @ ~{current_price:.4f} | motivo: {close_reason}",
                             details={"side_to_close": side_to_close, "size": size,
                                      "current_price": current_price, "close_reason": close_reason,
                                      "fee_type": fee_type, "hedge_mode": hedge})
            _last_close_err = None
            for _close_attempt in range(1, 4):  # Até 3 tentativas
                try:
                    order = await _place_order(
                        ex,
                        ccxt_sym,
                        side_to_close,
                        size,
                        fee_type,
                        direction,
                        hedge,
                        timeout_s=maker_timeout,
                        config_id=config_id,
                        exchange_name=exchange_name,
                    )
                    exit_price = float(order.get('average') or order.get('price') or current_price)
                    close_order_id = str(order.get('id', '') or '')
                    await _log_order(config_id, "close_success", "INFO", symbol=symbol, direction=direction,
                                     exchange=exchange_name,
                                     message=f"Posição fechada: {symbol} @ {exit_price:.4f}",
                                     details={"order_id": close_order_id, "exit_price": exit_price,
                                              "close_reason": close_reason})
                    _last_close_err = None
                    break
                except Exception as _ce:
                    _last_close_err = _ce
                    if _close_attempt < 3:
                        await _log_order(
                            config_id, "close_retry", "WARNING",
                            symbol=symbol, direction=direction, exchange=exchange_name,
                            message=f"Tentativa {_close_attempt} de fechar {symbol} falhou: {_ce}. Retry em {2**_close_attempt}s...",
                            details={"attempt": _close_attempt, "error": str(_ce)},
                        )
                        await asyncio.sleep(2 ** _close_attempt)
            close_err = _last_close_err
            if close_err is not None:
                # Verificar se a posição já foi fechada externamente (ex: TP limit preenchida)
                position_on_exchange = True
                try:
                    ex_positions = await ex.fetch_positions([ccxt_sym])
                    position_on_exchange = any(
                        abs(float(p.get('contracts') or p.get('info', {}).get('positionAmt') or 0)) > 0
                        and (p.get('side') or '').upper() == direction
                        for p in ex_positions
                    )
                except Exception as e:
                    _log_non_fatal(
                        f"_monitor_and_close_position {config_id}/{symbol}: fetch_positions após falha de close",
                        e,
                    )

                if not position_on_exchange:
                    # Posição já fechada na exchange (TP limit ou fechamento externo)
                    print(f"[RealTrading] {symbol}: posição já fechada na exchange — sincronizando DB.")
                    close_reason = close_reason if close_reason != "funding" else "exchange_sync"
                    exit_price = current_price
                    close_order_id = tp_limit_order_id or "external"
                    # Tentar recuperar preço real do TP limit se disponível
                    if tp_limit_order_id:
                        try:
                            tp_ord = await ex.fetch_order(tp_limit_order_id, ccxt_sym)
                            if tp_ord.get('status') in ('closed', 'filled'):
                                exit_price = float(tp_ord.get('average') or tp_ord.get('price') or current_price)
                                close_order_id = tp_limit_order_id
                                close_reason = "take_profit_target"
                        except Exception as e:
                            _log_non_fatal(
                                f"_monitor_and_close_position {config_id}/{symbol}: fetch_order TP após fechamento externo",
                                e,
                            )
                    await _log_order(config_id, "close_success", "INFO", symbol=symbol, direction=direction,
                                     exchange=exchange_name,
                                     message=f"Posição {symbol} sincronizada — fechada na exchange @ ~{exit_price:.4f}",
                                     details={"close_reason": close_reason, "original_error": str(close_err)})
                else:
                    # Posição ainda aberta mas não conseguimos fechar — repassar o erro
                    raise close_err

        # Anti-duplicação: verificar se posição ainda existe antes de registrar o trade
        # Aproveita o SELECT para ler entry_score e entry_score_breakdown
        still_open = await db.fetchrow(
            "SELECT id, entry_score, entry_score_breakdown FROM real_positions WHERE config_id=$1 AND symbol=$2",
            config_id, symbol
        )
        if not still_open:
            # Trade já registrado por outra task (sync_loop ou monitor concorrente) — evitar duplicação
            print(f"[RealTrading] {symbol}: posição já removida do DB por outra task — pulando registro de trade.")
            if config_id in _sessions:
                _sessions[config_id]["positions"].pop(symbol, None)
                _sessions[config_id].get("monitor_tasks", {}).pop(symbol, None)
            return

        monitor_entry_score = still_open["entry_score"] if "entry_score" in still_open.keys() else None
        monitor_entry_score_breakdown = still_open["entry_score_breakdown"] if "entry_score_breakdown" in still_open.keys() else None

        # PnL estimado (será reconciliado com dados reais em background)
        cfg = _sessions[config_id]["config"]
        price_pnl = ((entry_price - exit_price) * size if direction == "SHORT" else (exit_price - entry_price) * size)
        fee_rate = cfg.get("feeRate", 0.0004)
        fee_cost = position_value * fee_rate * 2
        funding_pnl = abs(fr) * position_value  # Estimado; reconciliação busca o valor real
        total_pnl = funding_pnl + price_pnl - fee_cost

        leverage = cfg.get("leverage", 10)
        margin = position_value / leverage if leverage > 0 else position_value
        price_pnl_pct = (price_pnl / margin) * 100 if margin > 0 else 0
        total_pnl_pct = (total_pnl / margin) * 100 if margin > 0 else 0

        current_balance = float(await db.fetchval("SELECT balance FROM real_config WHERE id=$1", config_id))
        new_balance = current_balance + total_pnl

        close_ts = int(time.time() * 1000)
        trade_id = await db.fetchval(
            """
            INSERT INTO real_trades
                (config_id, symbol, direction, entry_price, exit_price, funding_rate, funding_pnl, price_pnl, price_pnl_pct, fee_cost,
                 total_pnl, total_pnl_pct, balance_after, open_time, close_time, trade_timestamp, exchange, close_reason,
                 entry_score, entry_score_breakdown)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
            RETURNING id
            """,
            config_id, symbol, direction, entry_price, exit_price, fr_pct, funding_pnl, price_pnl, price_pnl_pct, fee_cost,
            total_pnl, total_pnl_pct, new_balance, actual_open_time, _fmt_ts(close_ts), close_ts, exchange_name, close_reason,
            monitor_entry_score, monitor_entry_score_breakdown,
        )
        await db.execute("UPDATE real_config SET balance=$1 WHERE id=$2", new_balance, config_id)
        await db.execute("DELETE FROM real_positions WHERE config_id=$1 AND symbol=$2", config_id, symbol)

        if config_id in _sessions:
            _sessions[config_id]["positions"].pop(symbol, None)
            _sessions[config_id]["config"]["balance"] = new_balance
            _sessions[config_id].get("monitor_tasks", {}).pop(symbol, None)

        # Fire-and-forget: rastreia losses na blacklist inteligente
        if trade_id and uid:
            try:
                from symbol_blacklist import on_trade_closed as _bl_on_trade_closed
                asyncio.create_task(_bl_on_trade_closed(uid, symbol, config_id, total_pnl))
            except Exception:
                pass
            # Auto-análise IA com cooldown
            asyncio.create_task(auto_ai_analyze_and_apply(config_id, uid, "auto_cycle_end"))

        # Reconciliação + Webhook assíncrono: o webhook é enviado APÓS reconciliação
        # para garantir que os valores reais da exchange (price_pnl, fees, funding) sejam usados.
        if trade_id:
            asyncio.create_task(_reconcile_and_notify(
                exchange_name, uid, ccxt_sym, symbol,
                config_id, trade_id, actual_open_ts, close_ts,
                open_order_id, close_order_id if close_order_id else None,
                position_value, cfg.get("leverage", 1),
                session_cfg=session_cfg_ref,
                direction=direction,
                size=size,
                fr_pct=fr_pct,
                close_reason=close_reason,
                open_time_str=actual_open_time,
                close_time_str=_fmt_ts(close_ts),
            ))

        # Sessão de operação manual (novo/legado): encerra automaticamente ao fechar posição
        if runtime_mode in {"test", "manual", "manual_position"}:
            await _close_manual_session_if_idle(config_id)
    except Exception as e:
        print(f"[RealTrading] Erro fechando posição {symbol}: {e}")
        await _log_order(config_id, "error", "ERROR", symbol=symbol,
                         exchange=exchange_name,
                         message=f"Erro ao fechar posição {symbol}: {e}",
                         details={"exception": str(e), "close_reason": close_reason})
    finally:
        await ex.close()



async def _send_webhook(event_type: str, session_cfg: dict, trade_data: dict) -> None:
    """Envia webhooks assíncronos de abertura ou fechamento de ordem real."""
    url = "https://bot.vorxia.pro/webhook/fundtrader"
    user_id = session_cfg.get("user_id")
    user_info = {}

    if user_id is not None:
        try:
            row = await db.fetchrow("SELECT id, email FROM users WHERE id = $1", user_id)
            if row:
                user_info = dict(row)
        except Exception as e:
            _log_non_fatal(f"_send_webhook user lookup user_id={user_id}", e)

    payload = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user_info,
        "bot_config": {
            "config_id": session_cfg.get("config_id"),
            "exchange": session_cfg.get("exchange"),
            "leverage": session_cfg.get("leverage"),
            "operationMode": session_cfg.get("operationMode", "N/A"),
        },
        "trade": trade_data
    }

    # Motivo: garante envio da margem de entrada no webhook, mesmo quando o caller envia apenas value.
    trade_payload = payload.get("trade") if isinstance(payload.get("trade"), dict) else None
    if isinstance(trade_payload, dict) and trade_payload.get("entryMargin") is None:
        trade_payload["entryMargin"] = _calculate_entry_margin(
            trade_payload.get("value"),
            session_cfg.get("leverage"),
        )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                print(f"[Webhook] {event_type} enviado p/ {url}. Status: {resp.status}")
    except Exception as e:
        print(f"[Webhook] Erro ao enviar webhook {event_type}: {e}")

async def _execute_counter_trend_snipe(
    service,
    symbol: str,
    config_id: int,
    time_to_funding: int,
    prev_fr: float,
    force_immediate: bool = False,
    trigger_type: str = "auto",
) -> None:
    """
    Counter-Trend: entra na direção OPOSTA ao funding anterior, logo após a virada.

    Lógica de mercado:
    - prev_fr > 0 (funding positivo): shorts pagavam → muitos shorts → na virada, shorts fecham → pressão compradora → LONG
    - prev_fr < 0 (funding negativo): longs pagavam → muitos longs → na virada, longs fecham → pressão vendedora → SHORT

    entry_seconds: delay adicional após a virada antes de entrar (ex: 5s para deixar o movimento começar)
    sem timeout máximo: o fechamento depende de TP/SL/trailing/manual
    """
    session = _sessions.get(config_id)
    if not session:
        return

    cfg = session["config"]
    entry_sec = cfg.get("entrySeconds", 0)
    exchange_name = cfg["exchange"]
    leverage = cfg["leverage"]
    ex = None
    market = None
    ccxt_sym = None
    hedge = False
    # Gravar timestamp antes do PRE-WARM para compensar o tempo que ele consumir
    task_start_ms = int(time.time() * 1000)

    try:
        # ── PRE-WARM: operações lentas feitas com antecedência, antes do sleep ──
        try:
            ex = await _get_ccxt_exchange(exchange_name, user_id=cfg.get("user_id"))
            market = await _get_markets(ex, exchange_name)
            ccxt_sym = _native_to_ccxt_symbol(market, symbol)
            if ccxt_sym:
                await _set_leverage_and_margin(ex, ccxt_sym, leverage)
                hedge = await _is_hedge_mode(ex)
            else:
                print(f"[CounterTrend] Pre-warm: {symbol} não encontrado nos mercados, tentará na entrada.")
        except LeverageConflictError as lce:
            msg = (
                f"Símbolo {symbol} ignorado: leverage {lce.current_leverage}x ativo na exchange "
                f"(bot configurado: {lce.configured_leverage}x). Posição aberta por outro bot."
            )
            print(f"[CounterTrend] {msg}")
            await _log_order(config_id, "leverage_conflict", "WARN", symbol=symbol,
                             exchange=exchange_name, message=msg,
                             details={"exchange_leverage": lce.current_leverage,
                                      "configured_leverage": lce.configured_leverage})
            if ex is not None:
                await _safe_close_exchange(ex, f"_execute_counter_trend_snipe leverage_conflict {config_id}/{symbol}")
            return
        except Exception as e_pw:
            print(f"[CounterTrend] Pre-warm falhou para {symbol}: {e_pw}. Tentará na entrada.")
            if ex is not None:
                await _safe_close_exchange(
                    ex,
                    f"_execute_counter_trend_snipe pre-warm {config_id}/{symbol}",
                )
            ex = None
            market = None
            ccxt_sym = None

        # ── SLEEP: aguarda até a virada do funding compensando o tempo do PRE-WARM ──
        if not force_immediate:
            elapsed_ms = int(time.time() * 1000) - task_start_ms
            remaining_ttf_ms = time_to_funding - elapsed_ms
            wait_until_flip = remaining_ttf_ms / 1000.0
            if wait_until_flip > 0:
                await asyncio.sleep(wait_until_flip)

            # Aguarda delay adicional pós-virada configurado (ex: 2s para deixar o movimento começar)
            if entry_sec > 0:
                await asyncio.sleep(entry_sec)

        if config_id not in _sessions:
            return

        # ── EXECUÇÃO: apenas operações leves no momento crítico ──────────────
        # Direção OPOSTA ao funding anterior
        direction = "LONG" if prev_fr > 0 else "SHORT"
        if not _direction_allowed(cfg.get("autoDirection", "both"), direction):
            await _log_order(config_id, "direction_skip", "WARN", symbol=symbol,
                             direction=direction, exchange=exchange_name,
                             message=f"Direção {direction} bloqueada pelo filtro '{cfg.get('autoDirection')}'")
            return

        # Fallback: se o pre-warm falhou, tenta agora (com possível delay)
        if ex is None:
            ex = await _get_ccxt_exchange(exchange_name, user_id=cfg.get("user_id"))
        if market is None or ccxt_sym is None:
            market = await _get_markets(ex, exchange_name)
            ccxt_sym = _native_to_ccxt_symbol(market, symbol)
            if ccxt_sym is None:
                await ex.close()
                ex = None
                print(f"[CounterTrend] Símbolo {symbol} não encontrado nos mercados.")
                await _log_order(config_id, "symbol_not_found", "ERROR", symbol=symbol,
                                 exchange=exchange_name,
                                 message=f"Símbolo {symbol} não encontrado nos mercados da {exchange_name}")
                return
            try:
                await _set_leverage_and_margin(ex, ccxt_sym, leverage)
            except LeverageConflictError as lce:
                msg = (
                    f"Símbolo {symbol} ignorado: leverage {lce.current_leverage}x ativo na exchange "
                    f"(bot configurado: {lce.configured_leverage}x). Posição aberta por outro bot."
                )
                print(f"[CounterTrend] {msg}")
                await _log_order(config_id, "leverage_conflict", "WARN", symbol=symbol,
                                 exchange=exchange_name, message=msg,
                                 details={"exchange_leverage": lce.current_leverage,
                                          "configured_leverage": lce.configured_leverage})
                await _safe_close_exchange(ex, f"_execute_counter_trend_snipe leverage_conflict {config_id}/{symbol}")
                return
            hedge = await _is_hedge_mode(ex)

        # Preço fresco no momento da entrada (não pode ser pre-warm)
        ticker = await ex.fetch_ticker(ccxt_sym)
        entry_price = float(ticker.get('last') or ticker.get('close') or 0)
        if entry_price <= 0:
            await ex.close()
            ex = None
            await _log_order(config_id, "error", "ERROR", symbol=symbol, exchange=exchange_name,
                             message="Preço inválido (0) ao abrir posição counter-trend")
            return

        db_balance = float(await db.fetchval("SELECT balance FROM real_config WHERE id=$1", config_id))
        num_symbols = int(cfg.get("autoMaxSymbols") or len(cfg.get("symbols", [])) or 1)
        intended_per_slot = (db_balance * leverage * 0.95) / num_symbols

        # Desconta margem já usada por posições abertas nesta sessão (zero latência,
        # sem chamada extra à exchange) para evitar -2019 em aberturas paralelas.
        open_positions = _sessions.get(config_id, {}).get("positions", {})
        used_margin = sum(float(p.get("value", 0)) / leverage for p in open_positions.values())
        available_balance = max(0.0, db_balance - used_margin)
        position_value = min(available_balance * leverage * 0.95, intended_per_slot)

        size = position_value / entry_price
        size = float(ex.amount_to_precision(ccxt_sym, size))

        fee_type = cfg.get("feeType", "taker")
        maker_timeout = cfg.get("makerTimeoutSeconds", 8)
        side = 'buy' if direction == 'LONG' else 'sell'

        print(f"[CounterTrend] Abrindo {direction} {size} {symbol} ({ccxt_sym}) | funding anterior: {prev_fr:.6f}")
        await _log_order(config_id, "open_attempt", "INFO", symbol=symbol, direction=direction,
                         exchange=exchange_name,
                         message=f"Tentando abrir {direction} {size} {symbol} @ ~{entry_price}",
                         details={"ccxt_symbol": ccxt_sym, "side": side, "size": size,
                                  "entry_price": entry_price, "fee_type": fee_type,
                                  "leverage": leverage, "position_value": round(position_value, 4),
                                  "prev_funding_rate": prev_fr, "hedge_mode": hedge,
                                  "trigger_type": trigger_type})
        order = await _place_order(
            ex,
            ccxt_sym,
            side,
            size,
            fee_type,
            direction,
            hedge,
            timeout_s=maker_timeout,
            config_id=config_id,
            exchange_name=exchange_name,
        )
        actual_entry = float(order.get('average') or order.get('price') or entry_price)
        open_order_id = str(order.get('id', '') or '') or None

        open_ts = int(time.time() * 1000)
        open_time_str = _fmt_ts()

        await _log_order(config_id, "open_success", "INFO", symbol=symbol, direction=direction,
                         exchange=exchange_name,
                         message=f"Posição aberta: {direction} {size} {symbol} @ {actual_entry}",
                         details={"order_id": open_order_id, "actual_entry": actual_entry,
                                  "size": size, "position_value": round(position_value, 4),
                                  "open_time": open_time_str, "trigger_type": trigger_type})

        # Calcula score no momento da abertura
        try:
            ct_rates = await service.get_all_funding_rates()
            ct_rates = await enrich_with_score_counter_trend(ct_rates)
            ct_symbol_data = next((r for r in ct_rates if r["symbol"] == symbol), None)
            ct_score_data = (ct_symbol_data or {}).get("scoreData") or {}
            ct_entry_score = ct_score_data.get("score")
            ct_breakdown = ct_score_data.get("breakdown")
            ct_entry_score_breakdown = json.dumps(ct_breakdown) if ct_breakdown else None
        except Exception:
            ct_entry_score = None
            ct_entry_score_breakdown = None

        await db.execute(
            """
            INSERT INTO real_positions
                (config_id, symbol, direction, entry_price, size, value, funding_rate, funding_rate_pct, open_time, open_timestamp, exchange, open_order_id,
                 entry_score, entry_score_breakdown)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
            config_id, symbol, direction, actual_entry, size, position_value,
            0.0, 0.0, open_time_str, open_ts, exchange_name, open_order_id,
            ct_entry_score, ct_entry_score_breakdown,
        )

        session["positions"][symbol] = {
            "symbol": symbol, "direction": direction, "entryPrice": actual_entry, "size": size,
            "value": position_value, "fundingRatePct": 0.0, "openTime": open_time_str,
            "tpLimitOrderId": None, "tpLimitPrice": None,
        }

        asyncio.create_task(_send_webhook('OPEN', cfg, {
            "symbol": symbol, "direction": direction, "entryPrice": actual_entry,
            "size": size, "value": float(position_value), "fundingRatePct": 0.0,
            "entryMargin": _calculate_entry_margin(position_value, leverage),
            "openTime": open_time_str,
        }))

        await ex.close()
        ex = None

        # Take Profit limit (sem funding_pnl pois não capturamos funding)
        target_take_profit_pct = cfg.get("targetTakeProfitPct")
        limit_order_id = None
        if target_take_profit_pct is not None:
            ex_tp = None
            try:
                ex_tp = await _get_ccxt_exchange(exchange_name, user_id=cfg.get("user_id"))
                await _get_markets(ex_tp, exchange_name)  # injeta markets no ex_tp para price_to_precision
                margin = position_value / leverage if leverage > 0 else position_value
                fee_cost_est = position_value * cfg.get("feeRate", 0.0002) * 2
                # Counter-trend não captura funding — target de preço cobre apenas taxa
                target_pnl = margin * (target_take_profit_pct / 100.0)
                req_price_pnl = target_pnl + fee_cost_est
                delta_price = req_price_pnl / size if size > 0 else 0

                target_price = actual_entry + delta_price if direction == "LONG" else actual_entry - delta_price
                target_price = float(ex_tp.price_to_precision(ccxt_sym, target_price))
                side_to_close = 'sell' if direction == 'LONG' else 'buy'

                limit_params = _order_params(direction, hedge, reduce_only=True)
                limit_order = await ex_tp.create_limit_order(ccxt_sym, side_to_close, size, target_price, params=limit_params)
                limit_order_id = str(limit_order.get('id', ''))
                print(f"[CounterTrend] TP Limit enviada: {limit_order_id} @ {target_price}")
                # Persiste ID e preço da TP limit no banco para recuperação após restart.
                await db.execute(
                    "UPDATE real_positions SET tp_limit_order_id=$1, tp_limit_price=$2 WHERE config_id=$3 AND symbol=$4",
                    limit_order_id, target_price, config_id, symbol,
                )
                if symbol in session["positions"]:
                    session["positions"][symbol]["tpLimitOrderId"] = limit_order_id
                    session["positions"][symbol]["tpLimitPrice"] = target_price
            except Exception as e:
                print(f"[CounterTrend] Erro ao criar TP Limit: {e}")
            finally:
                if ex_tp is not None:
                    await _safe_close_exchange(
                        ex_tp,
                        f"_execute_counter_trend_snipe TP exchange {config_id}/{symbol}",
                    )

        # Registrar callback no User Data WS para detecção instantânea de TP fill (apenas Binance)
        tp_fill_event = None
        if limit_order_id and exchange_name == "binance":
            try:
                keys = await _get_api_keys("binance", user_id=cfg.get("user_id"))
                if keys.get("apiKey") and cfg.get("user_id"):
                    import binance_ws_user as _bws_user
                    ws_mgr = await _bws_user.get_or_create(cfg["user_id"], keys["apiKey"])
                    tp_fill_event = ws_mgr.register_tp(limit_order_id)
            except Exception as e_ws:
                print(f"[CounterTrend] WS User Data não disponível: {e_ws}")

        await _monitor_and_close_position(
            service, config_id, symbol, direction, size, actual_entry,
            0.0, 0.0,  # fr = 0.0, fr_pct = 0.0 (sem funding)
            open_order_id=open_order_id, tp_limit_order_id=limit_order_id,
            tp_fill_event=tp_fill_event,
        )

    except Exception as e:
        print(f"[CounterTrend] Erro crítico para {symbol}: {e}")
        cfg_ref = _sessions.get(config_id, {}).get("config", {})
        await _log_order(config_id, "error", "ERROR", symbol=symbol,
                         exchange=cfg_ref.get("exchange"),
                         message=f"Erro crítico counter-trend {symbol}: {e}",
                         details={"exception": str(e)})
        if ex is not None:
            await _safe_close_exchange(
                ex,
                f"_execute_counter_trend_snipe erro crítico {config_id}/{symbol}",
            )
    finally:
        sess = _sessions.get(config_id)
        if sess:
            sess.get("pending_snipes", set()).discard(symbol)


async def _execute_snipe(
    service,
    symbol: str,
    config_id: int,
    time_to_funding: int,
    force_immediate: bool = False,
    trigger_type: str = "auto",
    expected_funding_time_ms: int = 0,
    entry_timing: str = "before_funding",
    reference_funding_rate: float | None = None,
    reference_funding_rate_pct: float | None = None,
) -> None:
    session = _sessions.get(config_id)
    if not session: return

    cfg = session["config"]
    # Motivo: suportar entrada pós-virada sem criar uma função duplicada de execução.
    is_post_funding_follow = entry_timing == "after_funding_follow"
    entry_sec = cfg.get("entrySeconds", 30)
    exchange_name = cfg["exchange"]
    leverage = cfg["leverage"]
    ex = None
    market = None
    ccxt_sym = None
    hedge = False
    # Gravar timestamp antes do PRE-WARM para compensar o tempo que ele consumir
    task_start_ms = int(time.time() * 1000)

    try:
        # ── PRE-WARM: operações lentas feitas com antecedência, antes do sleep ──
        # load_markets() e set_leverage podem demorar 2-5s — executar agora evita
        # esse delay no momento crítico da entrada.
        try:
            ex = await _get_ccxt_exchange(exchange_name, user_id=cfg.get("user_id"))
            market = await _get_markets(ex, exchange_name)
            ccxt_sym = _native_to_ccxt_symbol(market, symbol)
            if ccxt_sym:
                await _set_leverage_and_margin(ex, ccxt_sym, leverage)
                hedge = await _is_hedge_mode(ex)
            else:
                print(f"[RealTrading] Pre-warm: {symbol} não encontrado nos mercados, tentará na entrada.")
        except LeverageConflictError as lce:
            msg = (
                f"Símbolo {symbol} ignorado: leverage {lce.current_leverage}x ativo na exchange "
                f"(bot configurado: {lce.configured_leverage}x). Posição aberta por outro bot."
            )
            print(f"[RealTrading] {msg}")
            await _log_order(config_id, "leverage_conflict", "WARN", symbol=symbol,
                             exchange=exchange_name, message=msg,
                             details={"exchange_leverage": lce.current_leverage,
                                      "configured_leverage": lce.configured_leverage})
            if ex is not None:
                await _safe_close_exchange(ex, f"_execute_snipe leverage_conflict {config_id}/{symbol}")
            return
        except Exception as e_pw:
            print(f"[RealTrading] Pre-warm falhou para {symbol}: {e_pw}. Tentará na entrada.")
            if ex is not None:
                await _safe_close_exchange(
                    ex,
                    f"_execute_snipe pre-warm {config_id}/{symbol}",
                )
            ex = None
            market = None
            ccxt_sym = None

        # ── SLEEP: aguarda o momento de entrada compensando o tempo do PRE-WARM ──
        if not force_immediate:
            elapsed_ms = int(time.time() * 1000) - task_start_ms
            remaining_ttf_ms = time_to_funding - elapsed_ms
            if is_post_funding_follow:
                # Motivo: no modo pós-funding, entrySeconds representa delay após a virada.
                target_entry_delay = (remaining_ttf_ms / 1000.0) + entry_sec
            else:
                target_entry_delay = (remaining_ttf_ms / 1000.0) - entry_sec
            if target_entry_delay > 0:
                await asyncio.sleep(target_entry_delay)
            # Verificação de segurança: se o funding já virou durante o PRE-WARM/sleep, abortar
            if (not is_post_funding_follow) and expected_funding_time_ms > 0 and int(time.time() * 1000) >= expected_funding_time_ms:
                await _log_order(config_id, "entry_skip_post_funding", "WARN", symbol=symbol,
                                 exchange=exchange_name,
                                 message=f"Entrada em {symbol} cancelada: funding já aconteceu (PRE-WARM/delay excedeu janela)")
                return

        # ── EXECUÇÃO: apenas operações leves no momento crítico ──────────────
        rates = await service.get_all_funding_rates()
        rates = await enrich_with_score(rates)
        symbol_data = next((r for r in rates if r["symbol"] == symbol), None)
        if not symbol_data:
            await _log_order(config_id, "symbol_not_found", "ERROR", symbol=symbol,
                             exchange=exchange_name,
                             message=f"Símbolo {symbol} não encontrado nos rates da exchange")
            return

        fr = float(symbol_data["fundingRate"] or 0)
        fr_pct = float(symbol_data["fundingRatePercent"] or 0)
        direction_fr = float(reference_funding_rate) if reference_funding_rate is not None else fr
        direction_fr_pct = (
            float(reference_funding_rate_pct)
            if reference_funding_rate_pct is not None
            else fr_pct
        )
        # Motivo: no pós-funding seguimos o sinal pré-virada; se vier nulo, usa o funding atual como fallback.
        if is_post_funding_follow and direction_fr == 0:
            direction_fr = fr
            direction_fr_pct = fr_pct
        anomaly_fr_pct = direction_fr_pct if is_post_funding_follow else fr_pct

        # Detecção de anomalia: funding > 5% por período é suspeito (erro de dados ou manipulação)
        if abs(float(anomaly_fr_pct or 0)) > 5.0:
            msg = (
                f"Anomalia detectada em {symbol}: fundingRate={anomaly_fr_pct:.4f}% (>5%). "
                f"Snipe cancelado por segurança."
            )
            print(f"[RealTrading] WARNING {msg}")
            await _log_order(config_id, "anomaly_detected", "WARN", symbol=symbol,
                             exchange=exchange_name, message=msg,
                             details={"funding_rate_pct": anomaly_fr_pct, "entry_timing": entry_timing})
            return

        # Extrai score do momento de abertura
        snipe_score_data = symbol_data.get("scoreData") or {}
        snipe_entry_score = snipe_score_data.get("score")
        snipe_breakdown = snipe_score_data.get("breakdown")
        snipe_entry_score_breakdown = json.dumps(snipe_breakdown) if snipe_breakdown else None

        if direction_fr == 0:
            await _log_order(
                config_id,
                "direction_skip",
                "WARN",
                symbol=symbol,
                exchange=exchange_name,
                message=f"Entrada cancelada em {symbol}: funding sem direcao (0).",
                details={"entry_timing": entry_timing, "funding_rate": direction_fr, "funding_rate_pct": direction_fr_pct},
            )
            return

        direction = "SHORT" if direction_fr > 0 else "LONG"
        # Motivo: no modo pós-funding não há captura imediata de funding.
        effective_fr = 0.0 if is_post_funding_follow else fr
        effective_fr_pct = 0.0 if is_post_funding_follow else fr_pct
        if not _direction_allowed(cfg.get("autoDirection", "both"), direction):
            await _log_order(config_id, "direction_skip", "WARN", symbol=symbol,
                             direction=direction, exchange=exchange_name,
                             message=f"Direção {direction} bloqueada pelo filtro '{cfg.get('autoDirection')}'",
                             details={
                                 "funding_rate": direction_fr,
                                 "funding_rate_pct": direction_fr_pct,
                                 "entry_timing": entry_timing,
                             })
            return

        # Fallback: se o pre-warm falhou, tenta agora (com possível delay)
        if ex is None:
            ex = await _get_ccxt_exchange(exchange_name, user_id=cfg.get("user_id"))
        if market is None or ccxt_sym is None:
            market = await _get_markets(ex, exchange_name)
            ccxt_sym = _native_to_ccxt_symbol(market, symbol)
            if ccxt_sym is None:
                await ex.close()
                ex = None
                print(f"[RealTrading] Símbolo {symbol} não encontrado nos mercados.")
                await _log_order(config_id, "symbol_not_found", "ERROR", symbol=symbol,
                                 exchange=exchange_name,
                                 message=f"Símbolo {symbol} não encontrado nos mercados da {exchange_name}")
                return
            try:
                await _set_leverage_and_margin(ex, ccxt_sym, leverage)
            except LeverageConflictError as lce:
                msg = (
                    f"Símbolo {symbol} ignorado: leverage {lce.current_leverage}x ativo na exchange "
                    f"(bot configurado: {lce.configured_leverage}x). Posição aberta por outro bot."
                )
                print(f"[RealTrading] {msg}")
                await _log_order(config_id, "leverage_conflict", "WARN", symbol=symbol,
                                 exchange=exchange_name, message=msg,
                                 details={"exchange_leverage": lce.current_leverage,
                                          "configured_leverage": lce.configured_leverage})
                await _safe_close_exchange(ex, f"_execute_snipe leverage_conflict {config_id}/{symbol}")
                return
            hedge = await _is_hedge_mode(ex)

        entry_price = symbol_data["lastPrice"]

        db_balance = float(await db.fetchval("SELECT balance FROM real_config WHERE id=$1", config_id))
        num_symbols = int(cfg.get("autoMaxSymbols") or len(cfg.get("symbols", [])) or 1)
        intended_per_slot = (db_balance * leverage * 0.95) / num_symbols

        # Desconta margem já usada por posições abertas nesta sessão (zero latência,
        # sem chamada extra à exchange) para evitar -2019 em aberturas paralelas.
        open_positions = _sessions.get(config_id, {}).get("positions", {})
        used_margin = sum(float(p.get("value", 0)) / leverage for p in open_positions.values())
        available_balance = max(0.0, db_balance - used_margin)
        position_value = min(available_balance * leverage * 0.95, intended_per_slot)

        size = position_value / entry_price
        size = float(ex.amount_to_precision(ccxt_sym, size))
        fee_type = cfg.get("feeType", "taker")
        maker_timeout = cfg.get("makerTimeoutSeconds", 8)
        side = 'buy' if direction == 'LONG' else 'sell'
        print(f"[RealTrading] Abrindo {direction} {size} {symbol} ({ccxt_sym}) hedge={hedge} fee={fee_type}")

        await _log_order(config_id, "open_attempt", "INFO", symbol=symbol, direction=direction,
                         exchange=exchange_name,
                         message=f"Tentando abrir {direction} {size} {symbol} @ ~{entry_price}",
                         details={"ccxt_symbol": ccxt_sym, "side": side, "size": size,
                                  "entry_price": entry_price, "fee_type": fee_type,
                                  "leverage": leverage, "position_value": round(position_value, 4),
                                  "funding_rate": direction_fr, "funding_rate_pct": direction_fr_pct, "hedge_mode": hedge,
                                  "trigger_type": trigger_type, "entry_timing": entry_timing})

        order = await _place_order(
            ex,
            ccxt_sym,
            side,
            size,
            fee_type,
            direction,
            hedge,
            timeout_s=maker_timeout,
            config_id=config_id,
            exchange_name=exchange_name,
        )
        actual_entry = order.get('average') or order.get('price') or entry_price
        open_order_id = str(order.get('id', '') or '') or None

        open_ts = int(time.time() * 1000)
        open_time_str = _fmt_ts()

        await _log_order(config_id, "open_success", "INFO", symbol=symbol, direction=direction,
                         exchange=exchange_name,
                         message=f"Posição aberta: {direction} {size} {symbol} @ {actual_entry}",
                         details={"order_id": open_order_id, "actual_entry": float(actual_entry),
                                  "size": size, "position_value": round(position_value, 4),
                                  "funding_rate_pct": effective_fr_pct, "open_time": open_time_str,
                                  "trigger_type": trigger_type, "entry_timing": entry_timing})

        await db.execute(
            """
            INSERT INTO real_positions
                (config_id, symbol, direction, entry_price, size, value, funding_rate, funding_rate_pct, open_time, open_timestamp, exchange, open_order_id,
                 entry_score, entry_score_breakdown)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
            config_id, symbol, direction, actual_entry, size, position_value, effective_fr, effective_fr_pct, open_time_str, open_ts, exchange_name, open_order_id,
            snipe_entry_score, snipe_entry_score_breakdown,
        )

        session["positions"][symbol] = {
            "symbol": symbol, "direction": direction, "entryPrice": actual_entry, "size": size,
            "value": position_value, "fundingRatePct": effective_fr_pct, "openTime": open_time_str,
            "tpLimitOrderId": None, "tpLimitPrice": None,
        }

        # Dispara Webhook assíncrono (Abertura)
        asyncio.create_task(_send_webhook('OPEN', cfg, {
            "symbol": symbol, "direction": direction, "entryPrice": actual_entry,
            "size": size, "value": float(position_value), "fundingRatePct": effective_fr_pct,
            "entryMargin": _calculate_entry_margin(position_value, leverage),
            "openTime": open_time_str
        }))

        await ex.close()
        ex = None  # Marca como fechada para evitar double-close no except

        target_take_profit_pct = cfg.get("targetTakeProfitPct")
        limit_order_id = None
        if target_take_profit_pct is not None:
            ex_tp = None
            try:
                ex_tp = await _get_ccxt_exchange(exchange_name, user_id=cfg.get("user_id"))
                await _get_markets(ex_tp, exchange_name)  # injeta markets no ex_tp para price_to_precision
                margin = position_value / leverage if leverage > 0 else position_value
                # Usa cfg.get("feeRate") — fee_rate não existe neste escopo da função
                fee_cost_est = position_value * cfg.get("feeRate", 0.0002) * 2
                funding_pnl = abs(effective_fr) * position_value
                target_pnl = margin * (target_take_profit_pct / 100.0)
                req_price_pnl = target_pnl - funding_pnl + fee_cost_est
                delta_price = req_price_pnl / size if size > 0 else 0

                target_price = actual_entry + delta_price if direction == "LONG" else actual_entry - delta_price
                target_price = float(ex_tp.price_to_precision(ccxt_sym, target_price))
                side_to_close = 'sell' if direction == 'LONG' else 'buy'

                limit_params = _order_params(direction, hedge, reduce_only=True)
                _tp_create_err = None
                for _tp_attempt in range(1, 4):  # Até 3 tentativas com backoff
                    try:
                        limit_order = await ex_tp.create_limit_order(ccxt_sym, side_to_close, size, target_price, params=limit_params)
                        limit_order_id = str(limit_order.get('id', ''))
                        _tp_create_err = None
                        break
                    except Exception as _tce:
                        _tp_create_err = _tce
                        if _tp_attempt < 3:
                            await asyncio.sleep(2 ** _tp_attempt)
                if _tp_create_err is not None:
                    await _log_order(
                        config_id, "tp_create_failed", "ERROR",
                        symbol=symbol, direction=direction, exchange=exchange_name,
                        message=f"Falha ao criar TP limit em {symbol} após 3 tentativas: {_tp_create_err}",
                        details={"target_price": target_price, "error": str(_tp_create_err)},
                    )
                else:
                    print(f"[RealTrading] Ordem TP Limit enviada: {limit_order_id} @ {target_price}")
                    # Persiste ID e preço da TP limit no banco para recuperação após restart.
                    await db.execute(
                        "UPDATE real_positions SET tp_limit_order_id=$1, tp_limit_price=$2 WHERE config_id=$3 AND symbol=$4",
                        limit_order_id, target_price, config_id, symbol,
                    )
                    if symbol in session["positions"]:
                        session["positions"][symbol]["tpLimitOrderId"] = limit_order_id
                        session["positions"][symbol]["tpLimitPrice"] = target_price
            except Exception as e:
                print(f"[RealTrading] Erro ao colocar Take Profit Limit: {e}")
            finally:
                if ex_tp is not None:
                    await _safe_close_exchange(
                        ex_tp,
                        f"_execute_snipe TP exchange {config_id}/{symbol}",
                    )

        # Registrar callback no User Data WS para detecção instantânea de TP fill (apenas Binance)
        tp_fill_event = None
        if limit_order_id and exchange_name == "binance":
            try:
                keys = await _get_api_keys("binance", user_id=cfg.get("user_id"))
                if keys.get("apiKey") and cfg.get("user_id"):
                    import binance_ws_user as _bws_user
                    ws_mgr = await _bws_user.get_or_create(cfg["user_id"], keys["apiKey"])
                    tp_fill_event = ws_mgr.register_tp(limit_order_id)
            except Exception as e_ws:
                print(f"[RealTrading] WS User Data não disponível para snipe: {e_ws}")

        await _monitor_and_close_position(
            service, config_id, symbol, direction, size, actual_entry, effective_fr, effective_fr_pct,
            open_order_id=open_order_id, tp_limit_order_id=limit_order_id,
            tp_fill_event=tp_fill_event,
        )

    except Exception as e:
        print(f"[RealTrading] Erro crítico no Snipe para {symbol}: {e}")
        cfg_ref = _sessions.get(config_id, {}).get("config", {})
        await _log_order(config_id, "error", "ERROR", symbol=symbol,
                         exchange=cfg_ref.get("exchange"),
                         message=f"Erro crítico no snipe de {symbol}: {e}",
                         details={"exception": str(e)})
        # Fecha conexão apenas se ex foi inicializada antes do erro
        if ex is not None:
            await _safe_close_exchange(
                ex,
                f"_execute_snipe erro crítico {config_id}/{symbol}",
            )
    finally:
        sess = _sessions.get(config_id)
        if sess:
            sess.get("pending_snipes", set()).discard(symbol)

async def _position_sync_loop(config_id: int, session_cfg: dict) -> None:
    """
    Verifica a cada 180s se posições abertas no DB ainda existem na exchange.
    Se uma posição foi fechada/liquidada na exchange mas permanece no DB,
    fecha-a no DB com close_reason='exchange_sync' e registra o trade.
    """
    while config_id in _sessions:
        try:
            await asyncio.sleep(30)

            if config_id not in _sessions:
                break
            sync_result = await _sync_positions_once(config_id, session_cfg)
            if sync_result.get("errors"):
                print(
                    f"[SyncLoop] config_id={config_id}: "
                    f"{len(sync_result['errors'])} erro(s) não fatal(is) no ciclo."
                )

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[SyncLoop] Erro inesperado (config_id={config_id}): {e}")


async def _monitoring_loop(service, config_id: int, session_cfg: dict) -> None:
    _last_health_check = 0.0

    while config_id in _sessions:
        try:
            operation_mode = session_cfg.get("operationMode", "manual")
            # Motivo: incluir o modo pós-funding favorável no ciclo automático de seleção/execução.
            is_auto_mode = operation_mode in {"auto_expiring", "auto_strongest", "auto_highest_rate", "counter_trend", "post_funding_follow"}
            is_counter_trend = operation_mode == "counter_trend"
            is_post_funding_follow = operation_mode == "post_funding_follow"
            if is_auto_mode:
                strategy = {
                    "mode": operation_mode,
                    "direction": session_cfg.get("autoDirection", "both"),
                    "maxSymbols": session_cfg.get("autoMaxSymbols", 8),
                    "minScore": session_cfg.get("autoMinScore", 50.0),
                    "minFundingRatePct": session_cfg.get("minFundingRatePct", 0.001),
                    "windowMinutes": session_cfg.get("autoWindowMinutes", 60),
                    "preselectedSymbols": session_cfg.get("preselectedSymbols", []),
                    "preselectedKey": session_cfg.get("preselectedKey", ""),
                    "ctSortCriteria": session_cfg.get("ctSortCriteria", "score"),
                    "user_id": session_cfg.get("user_id"),
                }
                resolved_symbols = await _resolve_auto_symbols(
                    service,
                    session_cfg.get("exchange", "binance"),
                    strategy,
                    prefer_preselected=False,
                )
                current_symbols = list(session_cfg.get("symbols") or [])
                if resolved_symbols != current_symbols:
                    session_cfg["symbols"] = resolved_symbols
                    if config_id in _sessions:
                        _sessions[config_id]["config"]["symbols"] = resolved_symbols
                    await db.execute(
                        "UPDATE real_config SET symbols=$1 WHERE id=$2",
                        resolved_symbols,
                        config_id,
                    )

            symbols = session_cfg.get("symbols", [])
            if not symbols:
                await asyncio.sleep(10)
                continue

            positions = _sessions.get(config_id, {}).get("positions", {})
            pending = _sessions.get(config_id, {}).get("pending_snipes", set())

            # Health check: recriar tasks de monitoramento mortas a cada 60s
            now_ts = time.time()
            if now_ts - _last_health_check >= 60:
                _last_health_check = now_ts
                monitor_tasks_ref = _sessions.get(config_id, {}).get("monitor_tasks", {})
                for sym in list(positions.keys()):
                    task = monitor_tasks_ref.get(sym)
                    if task is None or task.done():
                        pos_row = await db.fetchrow(
                            "SELECT * FROM real_positions WHERE config_id=$1 AND symbol=$2",
                            config_id, sym,
                        )
                        if pos_row:
                            print(f"[RealTrading] Health check #{config_id}: retomando monitoramento de {sym}")
                            hc_tp_id = pos_row.get("tp_limit_order_id") or None
                            hc_tp_event = None
                            if hc_tp_id and session_cfg.get("exchange", "binance") == "binance":
                                try:
                                    hc_keys = await _get_api_keys("binance", user_id=session_cfg.get("user_id"))
                                    if hc_keys.get("apiKey") and session_cfg.get("user_id"):
                                        import binance_ws_user as _bws_user
                                        hc_mgr = await _bws_user.get_or_create(session_cfg["user_id"], hc_keys["apiKey"])
                                        hc_tp_event = hc_mgr.register_tp(hc_tp_id)
                                except Exception as e:
                                    _log_non_fatal(
                                        f"_monitoring_loop health-check WS TP register {config_id}/{sym}",
                                        e,
                                    )
                            new_task = asyncio.create_task(_monitor_and_close_position(
                                service, config_id, sym,
                                pos_row["direction"], float(pos_row["size"]), float(pos_row["entry_price"]),
                                float(pos_row["funding_rate"] or 0), float(pos_row["funding_rate_pct"] or 0),
                                open_order_id=str(pos_row["open_order_id"]) if pos_row.get("open_order_id") else None,
                                tp_limit_order_id=hc_tp_id,
                                tp_fill_event=hc_tp_event,
                            ))
                            monitor_tasks_ref[sym] = new_task

            # Usar WebSocket market stream (Binance) se disponível; fallback REST
            if session_cfg.get("exchange", "binance") == "binance":
                from binance_ws_market import get_all_rates as _ws_get_all_rates
                rates = _ws_get_all_rates() or await service.get_all_funding_rates()
            else:
                rates = await service.get_all_funding_rates()

            # Pausado: continua o loop (monitora posições abertas) mas não entra em novas
            if session_cfg.get("paused", False):
                await asyncio.sleep(15)
                continue

            now_ms = int(time.time() * 1000)
            entry_sec = session_cfg.get("entrySeconds", 30)
            # Motivo: aplicar filtro minimo de funding tambem no gate final de abertura.
            min_funding_rate_pct = _clamp_float(
                session_cfg.get("minFundingRatePct"),
                default=0.001,
                minimum=0.0,
                maximum=5.0,
            )
            # Counter-trend usa janela fixa de 76s para detectar a virada se aproximando
            window_ms = 76_000 if is_counter_trend else (entry_sec * 1000) + 16_000

            next_wake_ms: float | None = None

            for symbol in symbols:
                if symbol in positions or symbol in pending: continue

                symbol_data = next((r for r in rates if r["symbol"] == symbol), None)
                if not symbol_data: continue
                fr_pct_now = float(symbol_data.get("fundingRatePercent", 0) or 0)
                if abs(fr_pct_now) < min_funding_rate_pct:
                    continue

                # TODOS os modos devem esperar o horário de virada do funding rate
                # A diferença entre modos é quais símbolos são selecionados, não quando executar
                next_funding = int(symbol_data.get("nextFundingTime", 0) or 0)
                if not next_funding: continue

                time_to_funding = next_funding - now_ms

                if 0 < time_to_funding <= window_ms:
                    pending.add(symbol)
                    monitor_tasks = _sessions.get(config_id, {}).get("monitor_tasks", {})
                    if is_counter_trend:
                        fr = float(symbol_data.get("fundingRate", 0) or 0)
                        task = asyncio.create_task(_execute_counter_trend_snipe(service, symbol, config_id, time_to_funding, fr))
                    elif is_post_funding_follow:
                        # Motivo: novo modo entra após a virada, mas seguindo a mesma direção recomendada pelo funding pré-virada.
                        fr = float(symbol_data.get("fundingRate", 0) or 0)
                        task = asyncio.create_task(
                            _execute_snipe(
                                service,
                                symbol,
                                config_id,
                                time_to_funding,
                                expected_funding_time_ms=next_funding,
                                entry_timing="after_funding_follow",
                                reference_funding_rate=fr,
                                reference_funding_rate_pct=fr_pct_now,
                            )
                        )
                    else:
                        task = asyncio.create_task(_execute_snipe(service, symbol, config_id, time_to_funding,
                                                                   expected_funding_time_ms=next_funding))
                    monitor_tasks[symbol] = task
                elif time_to_funding > window_ms:
                    wake_in = time_to_funding - window_ms
                    if next_wake_ms is None or wake_in < next_wake_ms: next_wake_ms = wake_in

            sleep_s = 30.0
            if next_wake_ms is not None:
                if next_wake_ms < 60_000: sleep_s = 2.0
                elif next_wake_ms < 300_000: sleep_s = min(next_wake_ms / 1000, 10.0)
                else: sleep_s = min(next_wake_ms / 1000, 30.0)

            await asyncio.sleep(max(sleep_s, 1.0))

        except asyncio.CancelledError:
            # Task cancelada pelo stop_trading — encerra o loop sem erro
            break
        except Exception:
            await asyncio.sleep(30)


# ──────────────────────────────────────────────
# Operação Manual — abre posição imediata e fecha por SL/Trailing
# ──────────────────────────────────────────────

def _native_to_ccxt_symbol(markets: dict, native_id: str) -> str | None:
    """
    Converte símbolo nativo da exchange (ex: AWEUSDT) para o formato
    unificado do CCXT (ex: AWE/USDT:USDT).
    Retorna None se não encontrado.
    """
    if native_id in markets:
        return native_id
    for unified_sym, mkt in markets.items():
        if mkt.get('id') == native_id and mkt.get('type') in ('swap', 'future', 'perpetual'):
            return unified_sym
    # Segunda passagem sem filtrar tipo (por compatibilidade)
    for unified_sym, mkt in markets.items():
        if mkt.get('id') == native_id:
            return unified_sym
    return None


async def _resolve_manual_post_only_price(
    ex,
    ccxt_symbol: str,
    side: str,
    requested_price: float,
) -> tuple[float, bool]:
    # Motivo: entrada limit manual deve ficar no lado maker; se cruzar book, ajusta 1 tick automaticamente.
    ticker = await ex.fetch_ticker(ccxt_symbol)
    bid = float(ticker.get("bid") or 0)
    ask = float(ticker.get("ask") or 0)
    tick_size = _extract_tick_size(ex, ccxt_symbol)

    price = float(requested_price)
    adjusted = False

    if side == "buy" and ask > 0 and price >= ask:
        if tick_size is None:
            raise ValueError("Não foi possível ajustar preço de compra para maker (tick desconhecido).")
        price = ask - tick_size
        adjusted = True
    elif side == "sell" and bid > 0 and price <= bid:
        if tick_size is None:
            raise ValueError("Não foi possível ajustar preço de venda para maker (tick desconhecido).")
        price = bid + tick_size
        adjusted = True

    if price <= 0:
        raise ValueError("Preço limit inválido após ajuste de post-only.")

    try:
        price = float(ex.price_to_precision(ccxt_symbol, price))
    except Exception:
        pass

    if side == "buy" and ask > 0 and price >= ask:
        if tick_size is None:
            raise ValueError("Preço de compra cruzaria o ask e não foi possível ajustar para maker.")
        price = float(ex.price_to_precision(ccxt_symbol, max(ask - tick_size, tick_size)))
        adjusted = True
    elif side == "sell" and bid > 0 and price <= bid:
        if tick_size is None:
            raise ValueError("Preço de venda cruzaria o bid e não foi possível ajustar para maker.")
        price = float(ex.price_to_precision(ccxt_symbol, bid + tick_size))
        adjusted = True

    if price <= 0:
        raise ValueError("Preço limit inválido após normalização de precisão.")
    return price, adjusted


async def _promote_pending_entry_to_position(
    *,
    service,
    config_id: int,
    symbol: str,
    direction: str,
    exchange_name: str,
    size: float,
    entry_price: float,
    position_value: float,
    open_order_id: str | None,
) -> None:
    # Motivo: centraliza promoção de entrada pendente (limit) para posição ativa monitorada.
    open_ts = int(time.time() * 1000)
    open_time_str = _fmt_ts(open_ts)

    await db.execute(
        """
        INSERT INTO real_positions
            (config_id, symbol, direction, entry_price, size, value,
             funding_rate, funding_rate_pct, open_time, open_timestamp, exchange, open_order_id,
             entry_score, entry_score_breakdown)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        """,
        config_id,
        symbol,
        direction,
        entry_price,
        size,
        position_value,
        0.0,
        0.0,
        open_time_str,
        open_ts,
        exchange_name,
        open_order_id,
        None,
        None,
    )

    sess = _sessions.get(config_id)
    if not sess:
        return

    sess["positions"][symbol] = {
        "symbol": symbol,
        "direction": direction,
        "entryPrice": entry_price,
        "size": size,
        "value": position_value,
        "fundingRatePct": 0.0,
        "openTime": open_time_str,
        "tpLimitOrderId": None,
        "tpLimitPrice": None,
    }

    prev_task = sess.setdefault("monitor_tasks", {}).get(symbol)
    if prev_task and not prev_task.done():
        prev_task.cancel()

    monitor_task = asyncio.create_task(
        _monitor_and_close_position(
            service,
            config_id,
            symbol,
            direction,
            size,
            entry_price,
            0.0,
            0.0,
            open_order_id=open_order_id,
            tp_limit_order_id=None,
            tp_fill_event=None,
        )
    )
    sess["monitor_tasks"][symbol] = monitor_task
    sess["task"] = monitor_task


async def _watch_pending_manual_entry(
    *,
    service,
    config_id: int,
    pending_row: dict,
) -> None:
    # Motivo: acompanhar ordem limit manual até preencher/cancelar e promover para posição automaticamente.
    pending_id = int(pending_row.get("id"))
    symbol = str(pending_row.get("symbol") or "").upper()
    direction = str(pending_row.get("direction") or "LONG").upper()
    side = str(pending_row.get("side") or ("buy" if direction == "LONG" else "sell")).lower()
    size = float(pending_row.get("size") or 0)
    limit_price = float(pending_row.get("limit_price") or 0)
    order_id = str(pending_row.get("order_id") or "").strip()
    exchange_name = str(pending_row.get("exchange") or "binance").lower()

    if not symbol or not order_id or size <= 0 or limit_price <= 0:
        await _set_pending_entry_status(
            pending_id,
            _PENDING_STATUS_REJECTED,
            last_error="payload_pending_invalido",
        )
        await _remove_pending_entry_runtime(config_id, pending_id)
        await _close_manual_session_if_idle(config_id)
        return

    user_id = pending_row.get("user_id")
    if user_id is None:
        user_id = (_sessions.get(config_id, {}).get("config", {}) or {}).get("user_id")

    ex = None
    ccxt_sym = symbol
    try:
        ex = await _get_ccxt_exchange(exchange_name, user_id=user_id)
        markets = await _get_markets(ex, exchange_name)
        ccxt_sym = _native_to_ccxt_symbol(markets, symbol) or symbol

        while True:
            row = await db.fetchrow(
                "SELECT * FROM real_pending_entries WHERE id = $1",
                pending_id,
            )
            if not row:
                await _remove_pending_entry_runtime(config_id, pending_id)
                break
            row_dict = dict(row)
            if str(row_dict.get("status") or "").lower() != _PENDING_STATUS_PENDING:
                await _remove_pending_entry_runtime(config_id, pending_id)
                break

            try:
                order = await ex.fetch_order(order_id, ccxt_sym)
            except Exception as e:
                _log_non_fatal(
                    f"_watch_pending_manual_entry {config_id}/{symbol}: fetch_order",
                    e,
                )
                await asyncio.sleep(2)
                continue

            status = str(order.get("status") or "").lower()
            filled_size = _extract_order_filled_size(order)
            fill_price = _extract_order_fill_price(order, limit_price)

            if status in {"closed", "filled"}:
                final_size = filled_size if filled_size > 0 else size
                final_value = final_size * fill_price
                await _set_pending_entry_status(pending_id, _PENDING_STATUS_FILLED)
                await _remove_pending_entry_runtime(config_id, pending_id)
                await _promote_pending_entry_to_position(
                    service=service,
                    config_id=config_id,
                    symbol=symbol,
                    direction=direction,
                    exchange_name=exchange_name,
                    size=final_size,
                    entry_price=fill_price,
                    position_value=final_value,
                    open_order_id=order_id,
                )
                await _log_order(
                    config_id,
                    "pending_entry_filled",
                    "INFO",
                    symbol=symbol,
                    direction=direction,
                    exchange=exchange_name,
                    message=f"Entrada limit preenchida para {symbol} @ {fill_price:.8f}.",
                    details={
                        "pending_id": pending_id,
                        "order_id": order_id,
                        "side": side,
                        "filled_size": final_size,
                        "fill_price": fill_price,
                        "order_status": status,
                    },
                )
                break

            if status in {"canceled", "cancelled", "expired", "rejected"}:
                if filled_size > 0:
                    final_size = filled_size
                    final_value = final_size * fill_price
                    await _set_pending_entry_status(
                        pending_id,
                        _PENDING_STATUS_FILLED,
                        last_error=f"partial_fill_before_{status}",
                    )
                    await _remove_pending_entry_runtime(config_id, pending_id)
                    await _promote_pending_entry_to_position(
                        service=service,
                        config_id=config_id,
                        symbol=symbol,
                        direction=direction,
                        exchange_name=exchange_name,
                        size=final_size,
                        entry_price=fill_price,
                        position_value=final_value,
                        open_order_id=order_id,
                    )
                    await _log_order(
                        config_id,
                        "pending_entry_filled",
                        "WARN",
                        symbol=symbol,
                        direction=direction,
                        exchange=exchange_name,
                        message=f"Entrada limit parcial preenchida para {symbol} antes de {status}.",
                        details={
                            "pending_id": pending_id,
                            "order_id": order_id,
                            "side": side,
                            "filled_size": final_size,
                            "fill_price": fill_price,
                            "order_status": status,
                        },
                    )
                else:
                    mapped_status = {
                        "canceled": _PENDING_STATUS_CANCELED,
                        "cancelled": _PENDING_STATUS_CANCELED,
                        "expired": _PENDING_STATUS_EXPIRED,
                        "rejected": _PENDING_STATUS_REJECTED,
                    }.get(status, _PENDING_STATUS_CANCELED)
                    await _set_pending_entry_status(
                        pending_id,
                        mapped_status,
                        last_error=f"order_status:{status}",
                    )
                    await _remove_pending_entry_runtime(config_id, pending_id)
                    await _log_order(
                        config_id,
                        "pending_entry_canceled",
                        "WARN",
                        symbol=symbol,
                        direction=direction,
                        exchange=exchange_name,
                        message=f"Entrada limit de {symbol} não executou ({status}).",
                        details={
                            "pending_id": pending_id,
                            "order_id": order_id,
                            "side": side,
                            "filled_size": filled_size,
                            "order_status": status,
                        },
                    )
                    await _close_manual_session_if_idle(config_id)
                break

            await asyncio.sleep(2)

    except asyncio.CancelledError:
        return
    except Exception as e:
        _log_non_fatal(f"_watch_pending_manual_entry {config_id}/{symbol}", e)
        # Motivo: evita pendência órfã se o watcher falhar de forma inesperada.
        try:
            await _set_pending_entry_status(
                pending_id,
                _PENDING_STATUS_REJECTED,
                last_error=str(e)[:300],
            )
            await _remove_pending_entry_runtime(config_id, pending_id)
            await _close_manual_session_if_idle(config_id)
        except Exception:
            pass
        await _log_order(
            config_id,
            "error",
            "ERROR",
            symbol=symbol,
            direction=direction,
            exchange=exchange_name,
            message=f"Erro monitorando entrada limit pendente de {symbol}: {e}",
            details={"pending_id": pending_id, "order_id": order_id, "exception": str(e)},
        )
    finally:
        await _safe_close_exchange(ex, f"_watch_pending_manual_entry {config_id}/{symbol}")


async def execute_manual_trade(
    exchange: str,
    symbol: str,
    direction: str,
    fee_type: str,
    capital: float,
    leverage: int,
    user_id: int,
    maker_timeout_s: int = 8,
    stop_loss_pct: float | None = None,
    stop_loss_usd: float | None = None,
    trailing_stop_pct: float | None = None,
    trailing_start_profit_pct: float | None = None,
    break_even_at_pct: float | None = None,
    partial_tp_pct: float | None = None,
    partial_tp_size: float | None = None,
    entry_limit_price: float | None = None,
) -> dict:
    """
    Abre uma posição real manual imediata e fecha por regras de proteção.
    Regras de saída aceitas: stop loss por %, stop loss USD, trailing stop,
    break-even automático e TP parcial.
    """
    symbol = symbol.upper().strip()
    if not symbol:
        raise ValueError("Símbolo inválido.")
    if direction not in ("LONG", "SHORT"):
        raise ValueError("Direção deve ser LONG ou SHORT.")
    if capital <= 0:
        raise ValueError("Capital deve ser maior que zero.")

    maker_timeout_s = _coerce_smallint(
        maker_timeout_s,
        default=8,
        minimum=2,
        maximum=900,
        field="makerTimeout",
        assume_ms_if_large=True,
    )

    stop_loss_pct = _coerce_optional_non_negative_float(
        stop_loss_pct,
        field="stopLossPct",
    )
    if stop_loss_pct is not None and stop_loss_pct <= 0:
        raise ValueError("Campo 'stopLossPct' deve ser maior que zero.")

    stop_loss_usd = _coerce_optional_non_negative_float(
        stop_loss_usd,
        field="stopLossUsd",
    )
    if stop_loss_usd is not None and stop_loss_usd <= 0:
        raise ValueError("Campo 'stopLossUsd' deve ser maior que zero.")

    trailing_stop_pct = _coerce_optional_non_negative_float(
        trailing_stop_pct,
        field="trailingStopPct",
    )
    if trailing_stop_pct is not None and trailing_stop_pct <= 0:
        raise ValueError("Campo 'trailingStopPct' deve ser maior que zero.")
    trailing_start_profit_pct = _coerce_optional_non_negative_float(
        trailing_start_profit_pct,
        field="trailingStartProfitPct",
    )
    break_even_at_pct = _coerce_optional_non_negative_float(
        break_even_at_pct,
        field="breakEvenAtPct",
    )
    if break_even_at_pct is not None and break_even_at_pct <= 0:
        raise ValueError("Campo 'breakEvenAtPct' deve ser maior que zero.")
    partial_tp_pct = _coerce_optional_non_negative_float(
        partial_tp_pct,
        field="partialTpPct",
    )
    if partial_tp_pct is not None and partial_tp_pct <= 0:
        raise ValueError("Campo 'partialTpPct' deve ser maior que zero.")
    if partial_tp_size is not None:
        partial_tp_size = float(partial_tp_size)
        if partial_tp_size <= 0 or partial_tp_size > 100:
            raise ValueError("Campo 'partialTpSize' deve ser entre 1 e 100.")
    elif partial_tp_pct is not None:
        partial_tp_size = 50.0

    if (
        stop_loss_pct is None
        and stop_loss_usd is None
        and trailing_stop_pct is None
    ):
        raise ValueError(
            "Operação manual exige ao menos uma proteção ativa: "
            "stopLossPct, stopLossUsd ou trailingStopPct."
        )

    entry_limit_price = _coerce_optional_positive_float(
        entry_limit_price,
        field="entryLimitPrice",
    )

    fee_rate = 0.0002 if fee_type == "maker" else 0.0005

    # Valida conexão e resolve símbolo para formato CCXT (ex: AWEUSDT → AWE/USDT:USDT)
    ccxt_symbol: str
    try:
        ex_check = await _get_ccxt_exchange(exchange, user_id=user_id)
        markets = await ex_check.load_markets()
        resolved = _native_to_ccxt_symbol(markets, symbol)
        await ex_check.close()
        if resolved is None:
            raise ValueError(f"Símbolo '{symbol}' não encontrado na {exchange}.")
        ccxt_symbol = resolved
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Falha de autenticação: {str(e)[:120]}")

    exchange = str(exchange or "binance").lower()
    if exchange not in {"binance", "bybit"}:
        raise ValueError(f"Exchange inválida: {exchange}")
    if exchange == "binance":
        import binance_service as service
    else:
        import bybit_service as service

    # Cria sessão de operação manual
    config_id = await db.fetchval(
        """
        INSERT INTO real_config
            (session_name, symbols, capital, balance, leverage, fee_type, fee_rate,
             exchange, active, started_at, stop_loss_pct, stop_loss_usd,
             trailing_stop_pct, trailing_start_profit_pct,
             break_even_at_pct, partial_tp_pct, partial_tp_size,
             user_id, operation_mode, maker_timeout_seconds)
        VALUES ($1, $2, $3, $3, $4, $5, $6, $7, TRUE, NOW(), $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
        RETURNING id
        """,
        f"{symbol} MANUAL", [symbol], capital, leverage, fee_type, fee_rate, exchange,
        stop_loss_pct, stop_loss_usd, trailing_stop_pct, trailing_start_profit_pct,
        break_even_at_pct, partial_tp_pct, partial_tp_size,
        int(user_id) if user_id is not None else None,
        "manual_position", maker_timeout_s,
    )

    session_cfg = {
        "symbols": [symbol],
        "capital": capital,
        "balance": capital,
        "leverage": leverage,
        "feeType": fee_type,
        "feeRate": fee_rate,
        "exchange": exchange,
        "config_id": config_id,
        "user_id": user_id,
        "makerTimeoutSeconds": maker_timeout_s,
        "operationMode": "manual_position",
        "autoDirection": "both",
        "stopLossPct": stop_loss_pct,
        "stopLossUsd": stop_loss_usd,
        "trailingStopPct": trailing_stop_pct,
        "trailingStartProfitPct": trailing_start_profit_pct,
        "breakEvenAtPct": break_even_at_pct,
        "partialTpPct": partial_tp_pct,
        "partialTpSize": partial_tp_size,
    }
    _sessions[config_id] = {
        "task": None,
        "sync_task": asyncio.create_task(_position_sync_loop(config_id, session_cfg)),
        "config": session_cfg,
        "positions": {},
        "pending_snipes": set(),
        # Motivo: operação manual pode iniciar com entrada limit pendente antes de virar posição.
        "pending_entries": {},
        "pending_tasks": {},
        "monitor_tasks": {},
    }

    # Abre posição imediatamente ou cria entrada limit pendente (usa ccxt_symbol para API, symbol para banco)
    ex = None
    try:
        ex = await _get_ccxt_exchange(exchange, user_id=user_id)
        try:
            await _set_leverage_and_margin(ex, ccxt_symbol, leverage)
        except LeverageConflictError as lce:
            raise ValueError(
                f"Não é possível abrir {symbol} com {lce.configured_leverage}x: "
                f"já existe posição aberta neste símbolo com {lce.current_leverage}x leverage. "
                f"Feche a posição existente antes de alterar o leverage."
            )

        position_value = capital * leverage
        hedge = await _is_hedge_mode(ex)
        side = 'buy' if direction == 'LONG' else 'sell'
        if entry_limit_price is not None:
            # Motivo: com preço informado, a entrada manual deve ser limit post-only sem fallback para market.
            requested_price = float(entry_limit_price)
            size = position_value / requested_price
            size = float(ex.amount_to_precision(ccxt_symbol, size))
            if not math.isfinite(size) or size <= 0:
                raise ValueError("Tamanho da ordem limit inválido para o capital/preço informados.")

            limit_price, adjusted = await _resolve_manual_post_only_price(
                ex,
                ccxt_symbol,
                side,
                requested_price,
            )
            base_params = _order_params(direction, hedge)
            limit_params = {**base_params, "timeInForce": "GTX"}
            order = await ex.create_limit_order(
                ccxt_symbol,
                side,
                size,
                limit_price,
                params=limit_params,
            )
            order_id = str(order.get("id", "") or "").strip()
            if not order_id:
                raise ValueError("A exchange não retornou ID da ordem limit manual.")

            pending_id = await db.fetchval(
                """
                INSERT INTO real_pending_entries
                    (config_id, user_id, exchange, symbol, direction, side, size, limit_price, order_id, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                RETURNING id
                """,
                config_id,
                int(user_id) if user_id is not None else None,
                exchange,
                symbol,
                direction,
                side,
                size,
                limit_price,
                order_id,
                _PENDING_STATUS_PENDING,
            )
            pending_row = await db.fetchrow(
                """
                SELECT id, config_id, exchange, symbol, direction, side, size, limit_price, order_id, status,
                       created_at, updated_at
                FROM real_pending_entries
                WHERE id = $1
                """,
                pending_id,
            )
            pending_payload = _serialize_pending_entry(dict(pending_row))
            await _upsert_pending_entry_runtime(config_id, pending_payload)
            await _log_order(
                config_id,
                "pending_entry_created",
                "INFO",
                symbol=symbol,
                direction=direction,
                exchange=exchange,
                message=f"Entrada limit enviada para {symbol} @ {limit_price}.",
                details={
                    "pending_id": pending_id,
                    "order_id": order_id,
                    "side": side,
                    "size": size,
                    "limit_price": limit_price,
                    "adjusted_to_maker": adjusted,
                    "requested_price": requested_price,
                },
            )

            pending_task = asyncio.create_task(
                _watch_pending_manual_entry(
                    service=service,
                    config_id=config_id,
                    pending_row={
                        **dict(pending_row),
                        "user_id": user_id,
                    },
                )
            )
            _sessions[config_id]["pending_tasks"][pending_id] = pending_task
            await _safe_close_exchange(
                ex,
                f"execute_manual_trade start limit config_id={config_id} symbol={symbol}",
            )
            ex = None
            return await get_session_status(config_id)

        ticker = await ex.fetch_ticker(ccxt_symbol)
        entry_price = float(ticker.get('last') or ticker.get('close') or 0)
        if entry_price <= 0:
            raise ValueError("Não foi possível obter o preço atual do símbolo.")

        size = position_value / entry_price
        size = float(ex.amount_to_precision(ccxt_symbol, size))
        if not math.isfinite(size) or size <= 0:
            raise ValueError("Tamanho da ordem de mercado/maker inválido para o capital informado.")

        print(
            f"[RealManual] Abrindo {direction} {size} {symbol} "
            f"({ccxt_symbol}) hedge={hedge} fee={fee_type} @ ~{entry_price}"
        )
        order = await _place_order(
            ex,
            ccxt_symbol,
            side,
            size,
            fee_type,
            direction,
            hedge,
            timeout_s=maker_timeout_s,
            config_id=config_id,
            exchange_name=exchange,
        )
        actual_entry = float(order.get('average') or order.get('price') or entry_price)
        open_order_id = str(order.get('id', '') or '') or None
        actual_position_value = actual_entry * size

        await _promote_pending_entry_to_position(
            service=service,
            config_id=config_id,
            symbol=symbol,
            direction=direction,
            exchange_name=exchange,
            size=size,
            entry_price=actual_entry,
            position_value=actual_position_value,
            open_order_id=open_order_id,
        )

        await _safe_close_exchange(
            ex,
            f"execute_manual_trade start immediate config_id={config_id} symbol={symbol}",
        )
        ex = None

    except Exception as e:
        if ex:
            await _safe_close_exchange(
                ex,
                f"start_manual_position erro ao abrir operação manual config_id={config_id}",
            )
        # Motivo: evitar pendência órfã caso falhe durante a criação da entrada limit manual.
        try:
            await db.execute(
                """
                UPDATE real_pending_entries
                SET status = $1,
                    last_error = $2,
                    updated_at = NOW()
                WHERE config_id = $3
                  AND status = $4
                """,
                _PENDING_STATUS_REJECTED,
                str(e)[:300],
                config_id,
                _PENDING_STATUS_PENDING,
            )
        except Exception:
            pass
        sync_task = _sessions.get(config_id, {}).get("sync_task")
        if sync_task and not sync_task.done():
            sync_task.cancel()
        for t in list(_sessions.get(config_id, {}).get("pending_tasks", {}).values()):
            if t and not t.done():
                t.cancel()
        for t in list(_sessions.get(config_id, {}).get("monitor_tasks", {}).values()):
            if t and not t.done():
                t.cancel()
        await db.execute(
            "UPDATE real_config SET active=FALSE, ended_at=NOW() WHERE id=$1", config_id
        )
        _sessions.pop(config_id, None)
        raise ValueError(f"Erro ao abrir operação manual: {str(e)[:150]}")

    return await get_session_status(config_id)


async def execute_test_trade(
    exchange: str,
    symbol: str,
    direction: str,
    fee_type: str,
    capital: float,
    leverage: int,
    user_id: int,
    maker_timeout_s: int = 8,
    stop_loss_pct: float | None = None,
    stop_loss_usd: float | None = None,
    trailing_stop_pct: float | None = None,
    trailing_start_profit_pct: float | None = None,
) -> dict:
    """
    Compatibilidade legada: endpoint /real-trading/test.
    Agora delega para operação manual real.
    """
    if (
        stop_loss_pct is None
        and stop_loss_usd is None
        and trailing_stop_pct is None
    ):
        trailing_stop_pct = 1.5

    return await execute_manual_trade(
        exchange=exchange,
        symbol=symbol,
        direction=direction,
        fee_type=fee_type,
        capital=capital,
        leverage=leverage,
        user_id=user_id,
        maker_timeout_s=maker_timeout_s,
        stop_loss_pct=stop_loss_pct,
        stop_loss_usd=stop_loss_usd,
        trailing_stop_pct=trailing_stop_pct,
        trailing_start_profit_pct=trailing_start_profit_pct,
    )
