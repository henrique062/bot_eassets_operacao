"""
Módulo de blacklist inteligente de símbolos.

Rastreia losses consecutivos por símbolo e usa IA para decidir cooldown automático.
Todas as funções são fail-safe — nunca lançam exceção para o caller.
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta

import database as db

# Threshold de losses consecutivos para acionar análise de IA
LOSS_THRESHOLD = 3

# Cache TTL de 30s para evitar queries a cada ciclo
_blacklist_cache: dict[int, tuple[set, float]] = {}
_CACHE_TTL = 30.0


async def on_trade_closed(user_id: int, symbol: str, config_id: int, total_pnl: float) -> None:
    """
    Hook chamado após cada trade fechado. Atualiza rastreamento de losses consecutivos.
    Fire-and-forget — nunca bloqueia o fluxo de trading.
    """
    try:
        if total_pnl >= 0:
            # Win: reset do streak (mantém registro existente se houver)
            await db.execute(
                """
                UPDATE symbol_blacklist
                SET consecutive_losses = 0, updated_at = NOW()
                WHERE user_id = $1 AND symbol = $2 AND cleared_manually = FALSE
                """,
                user_id, symbol,
            )
        else:
            # Loss: contar losses consecutivos nos últimos trades do símbolo
            recent_trades = await db.fetch(
                """
                SELECT total_pnl FROM real_trades
                WHERE config_id = $1 AND symbol = $2
                ORDER BY trade_timestamp DESC
                LIMIT 10
                """,
                config_id, symbol,
            )

            consecutive = 0
            for trade in recent_trades:
                pnl = float(trade["total_pnl"] or 0)
                if pnl < 0:
                    consecutive += 1
                else:
                    break

            await db.execute(
                """
                INSERT INTO symbol_blacklist (user_id, symbol, consecutive_losses)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, symbol)
                DO UPDATE SET consecutive_losses = $3, updated_at = NOW()
                WHERE symbol_blacklist.cleared_manually = FALSE
                """,
                user_id, symbol, consecutive,
            )

            # Se atingiu o threshold e não está já blacklisted, disparar análise IA
            if consecutive >= LOSS_THRESHOLD:
                existing = await db.fetchrow(
                    """
                    SELECT blacklisted_until FROM symbol_blacklist
                    WHERE user_id = $1 AND symbol = $2 AND cleared_manually = FALSE
                    """,
                    user_id, symbol,
                )
                now_utc = datetime.now(timezone.utc)
                already_blacklisted = (
                    existing
                    and existing["blacklisted_until"] is not None
                    and existing["blacklisted_until"] > now_utc
                )
                if not already_blacklisted:
                    asyncio.create_task(
                        _analyze_and_maybe_blacklist(user_id, symbol, config_id, consecutive)
                    )
                # Disparar reconfiguração automática do bot via IA (lazy import evita circular)
                if config_id:
                    try:
                        from real_trader import auto_ai_analyze_and_apply
                        asyncio.create_task(auto_ai_analyze_and_apply(config_id, user_id, "loss_reconfig"))
                    except Exception:
                        pass

    except Exception as e:
        print(f"[Blacklist] Erro em on_trade_closed({user_id}, {symbol}): {e}")


async def _analyze_and_maybe_blacklist(
    user_id: int, symbol: str, config_id: int, consecutive_losses: int
) -> None:
    """Chama IA para decidir blacklist. Fail-safe."""
    try:
        from ai_service import analyze_symbol_for_blacklist

        recent_trades = await db.fetch(
            """
            SELECT symbol, direction, total_pnl, total_pnl_pct, price_pnl, funding_pnl,
                   fee_cost, close_reason, open_time, close_time, exchange
            FROM real_trades
            WHERE config_id = $1 AND symbol = $2
            ORDER BY trade_timestamp DESC
            LIMIT 10
            """,
            config_id, symbol,
        )
        trades_list = [dict(t) for t in recent_trades]

        result = await analyze_symbol_for_blacklist(
            symbol=symbol,
            consecutive_losses=consecutive_losses,
            recent_trades=trades_list,
        )

        should_blacklist = result.get("should_blacklist", False)
        cooldown_hours = int(result.get("cooldown_hours", 0))
        reason = result.get("reason", "")
        analysis = result.get("analysis", "")

        if should_blacklist and cooldown_hours > 0:
            blacklisted_until = datetime.now(timezone.utc) + timedelta(hours=cooldown_hours)
            await db.execute(
                """
                INSERT INTO symbol_blacklist (user_id, symbol, consecutive_losses, blacklisted_until, ai_reason, ai_analysis)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, symbol)
                DO UPDATE SET
                    consecutive_losses = $3,
                    blacklisted_until = $4,
                    ai_reason = $5,
                    ai_analysis = $6,
                    cleared_manually = FALSE,
                    updated_at = NOW()
                """,
                user_id, symbol, consecutive_losses,
                blacklisted_until,
                reason[:300] if reason else None,
                analysis or None,
            )
            _blacklist_cache.pop(user_id, None)
            print(
                f"[Blacklist] {symbol} bloqueado por {cooldown_hours}h para user {user_id}. "
                f"Motivo: {reason[:100]}"
            )
        else:
            print(
                f"[Blacklist] IA decidiu NÃO bloquear {symbol} para user {user_id}. "
                f"Motivo: {reason[:100]}"
            )

    except Exception as e:
        print(f"[Blacklist] Erro em _analyze_and_maybe_blacklist({user_id}, {symbol}): {e}")


async def is_symbol_blacklisted(user_id: int, symbol: str) -> bool:
    """Verifica se um símbolo está na blacklist ativa. Cache TTL 30s."""
    try:
        blacklisted = await get_blacklisted_symbols(user_id)
        return symbol in blacklisted
    except Exception:
        return False


async def get_blacklisted_symbols(user_id: int) -> set:
    """Retorna conjunto de símbolos na blacklist ativa do usuário. Cache TTL 30s."""
    try:
        cached = _blacklist_cache.get(user_id)
        if cached is not None:
            symbols_set, ts = cached
            if time.monotonic() - ts < _CACHE_TTL:
                return symbols_set

        now_utc = datetime.now(timezone.utc)
        rows = await db.fetch(
            """
            SELECT symbol FROM symbol_blacklist
            WHERE user_id = $1
              AND cleared_manually = FALSE
              AND blacklisted_until IS NOT NULL
              AND blacklisted_until > $2
            """,
            user_id, now_utc,
        )
        symbols_set = {r["symbol"] for r in rows}
        _blacklist_cache[user_id] = (symbols_set, time.monotonic())
        return symbols_set

    except Exception as e:
        print(f"[Blacklist] Erro em get_blacklisted_symbols({user_id}): {e}")
        return set()


async def get_user_blacklist(user_id: int) -> list:
    """Retorna lista completa de blacklists do usuário (ativas e históricas)."""
    try:
        now_utc = datetime.now(timezone.utc)
        rows = await db.fetch(
            """
            SELECT symbol, consecutive_losses, blacklisted_until, ai_reason, ai_analysis,
                   cleared_manually, created_at, updated_at
            FROM symbol_blacklist
            WHERE user_id = $1
            ORDER BY updated_at DESC
            """,
            user_id,
        )
        result = []
        for r in rows:
            bu = r["blacklisted_until"]
            is_active = (
                not r["cleared_manually"]
                and bu is not None
                and bu > now_utc
            )
            result.append({
                "symbol": r["symbol"],
                "consecutiveLosses": r["consecutive_losses"],
                "blacklistedUntil": bu.isoformat() if bu else None,
                "aiReason": r["ai_reason"],
                "aiAnalysis": r["ai_analysis"],
                "isActive": is_active,
                "clearedManually": r["cleared_manually"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
                "updatedAt": r["updated_at"].isoformat() if r["updated_at"] else None,
            })
        return result

    except Exception as e:
        print(f"[Blacklist] Erro em get_user_blacklist({user_id}): {e}")
        return []


async def clear_symbol_blacklist(user_id: int, symbol: str) -> bool:
    """Remove blacklist de um símbolo manualmente."""
    try:
        await db.execute(
            """
            UPDATE symbol_blacklist
            SET cleared_manually = TRUE, blacklisted_until = NULL, updated_at = NOW()
            WHERE user_id = $1 AND symbol = $2
            """,
            user_id, symbol,
        )
        _blacklist_cache.pop(user_id, None)
        return True
    except Exception as e:
        print(f"[Blacklist] Erro em clear_symbol_blacklist({user_id}, {symbol}): {e}")
        return False
