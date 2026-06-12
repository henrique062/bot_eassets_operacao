"""
Motor de Backtest para estratégia Funding Rate Sniping.
Simula abertura de posição antes do settlement e fechamento logo após.
Calcula P&L real considerando: funding recebido, variação de preço e fees.
"""

import time
from datetime import datetime, timezone, timedelta

# GMT-3 (Brasília)
BRT = timezone(timedelta(hours=-3))

# Fee padrão Binance Futures
DEFAULT_MAKER_FEE = 0.0002   # 0.02%
DEFAULT_TAKER_FEE = 0.0005   # 0.05%


def _fmt_ts(ts_ms: int) -> str:
    """Formata timestamp em ms para string GMT-3."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=BRT)
    return dt.strftime("%d/%m %H:%M")


async def run_backtest(
    service,
    symbol: str,
    capital: float = 1000.0,
    days: int = 7,
    entry_seconds_before: int = 60,
    exit_seconds_after: int = 60,
    fee_type: str = "maker",
    leverage: int = 1,
    mode: str = "normal",  # "normal" ou "sniping"
    target_take_profit_pct: float | None = None,
) -> dict:
    """
    Executa backtest histórico de Funding Rate Sniping.

    Modos:
    - normal: calcula variação de preço real entre velas (1h/4h)
    - sniping: simula entrada 30s antes e saída 30s depois (variação ≈ 0)

    Retorna: trades, métricas, equity curve.
    """
    fee_rate = DEFAULT_MAKER_FEE if fee_type == "maker" else DEFAULT_TAKER_FEE
    is_sniping = mode == "sniping"

    # Buscar histórico de funding (até 1000 registros)
    limit = min(days * 24, 1000)
    funding_history = await service.get_funding_history(symbol, limit)

    if not funding_history:
        return _empty_result("Sem dados de funding rate para este par")

    # Ordenar por timestamp crescente
    funding_history.sort(key=lambda x: x["fundingRateTimestamp"])

    # Filtrar por range de datas
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (days * 24 * 60 * 60 * 1000)
    funding_history = [f for f in funding_history if f["fundingRateTimestamp"] >= start_ms]

    if len(funding_history) < 2:
        return _empty_result("Dados insuficientes para o período selecionado")

    # Klines só são necessárias no modo normal
    price_lookup = {}
    klines_step_ms = 3600000  # default 1h

    if not is_sniping:
        if days <= 7:
            klines_interval = "1h"
            klines_limit = days * 24
            klines_step_ms = 3600000
        else:
            klines_interval = "4h"
            klines_limit = min(days * 6, 1000)
            klines_step_ms = 4 * 3600000

        klines = await service.get_klines(symbol, klines_interval, klines_limit)

        if not klines:
            return _empty_result("Sem dados de preço para calcular variação")

        for k in klines:
            key = (k["timestamp"] // klines_step_ms) * klines_step_ms
            price_lookup[key] = {
                "open": k["open"],
                "high": k["high"],
                "low": k["low"],
                "close": k["close"],
            }

    # ===== SIMULAR TRADES =====
    trades = []
    equity = capital
    equity_curve = [{"timestamp": start_ms, "equity": capital, "datetime": _fmt_ts(start_ms)}]
    total_funding_received = 0
    total_price_pnl = 0
    total_fees_paid = 0
    wins = 0
    losses = 0

    for funding in funding_history:
        fr = funding["fundingRate"]
        fr_pct = funding["fundingRatePercent"]
        settlement_ts = funding["fundingRateTimestamp"]

        if fr == 0:
            continue  # Pular funding neutro

        # Determinar direção (receber funding)
        direction = "SHORT" if fr > 0 else "LONG"

        if is_sniping:
            # Modo sniping: janela ~30s, variação de preço ≈ 0
            # Preço é irrelevante (price_pnl = 0), mas precisamos saber o tamanho da posição
            entry_price = float(funding.get("markPrice", 0) or 0)
            if entry_price <= 0:
                entry_price = 1.0  # fallback se não tiver markPrice
            exit_price = entry_price
            price_pnl = 0
            position_size = (equity * leverage) / entry_price
        else:
            # Modo normal: busca variação real entre klines
            settlement_key = (settlement_ts // klines_step_ms) * klines_step_ms
            entry_key = settlement_key - klines_step_ms
            exit_key = settlement_key

            entry_price_data = price_lookup.get(entry_key) or price_lookup.get(settlement_key)
            exit_price_data = price_lookup.get(exit_key) or price_lookup.get(settlement_key)

            if not entry_price_data or not exit_price_data:
                continue

            entry_price = entry_price_data["close"]
            exit_price = exit_price_data["close"]

            if entry_price <= 0:
                continue

            position_size = (equity * leverage) / entry_price
            if direction == "SHORT":
                price_pnl = (entry_price - exit_price) * position_size
            else:
                price_pnl = (exit_price - entry_price) * position_size

        if entry_price <= 0:
            continue

        funding_pnl = abs(fr) * equity * leverage
        fee_cost = equity * leverage * fee_rate * 2

        if target_take_profit_pct is not None:
            margin = equity
            req_pnl = margin * (target_take_profit_pct / 100.0)
            req_price_pnl = req_pnl - funding_pnl + fee_cost
            req_price_diff = req_price_pnl / position_size if position_size > 0 else 0

            if is_sniping:
                if funding_pnl - fee_cost >= req_pnl:
                    exit_price = entry_price
                    price_pnl = 0
            else:
                if direction == "SHORT":
                    max_favorable_price = exit_price_data["low"]
                    req_exit_price = entry_price - req_price_diff
                    if max_favorable_price <= req_exit_price:
                        exit_price = req_exit_price
                        price_pnl = (entry_price - exit_price) * position_size
                else:
                    max_favorable_price = exit_price_data["high"]
                    req_exit_price = entry_price + req_price_diff
                    if max_favorable_price >= req_exit_price:
                        exit_price = req_exit_price
                        price_pnl = (exit_price - entry_price) * position_size

        total_funding_received += funding_pnl
        total_price_pnl += price_pnl
        total_fees_paid += fee_cost

        # P&L total do trade
        trade_pnl = funding_pnl + price_pnl - fee_cost
        trade_pnl_pct = (trade_pnl / equity) * 100
        price_pnl_pct = (price_pnl / equity) * 100

        # Atualizar equity
        equity += trade_pnl

        if trade_pnl > 0:
            wins += 1
        else:
            losses += 1

        trade = {
            "id": len(trades) + 1,
            "timestamp": settlement_ts,
            "datetime": _fmt_ts(settlement_ts),
            "symbol": symbol.upper(),
            "direction": direction,
            "entryPrice": round(entry_price, 6),
            "exitPrice": round(exit_price, 6),
            "fundingRate": fr_pct,
            "fundingPnl": round(funding_pnl, 4),
            "pricePnl": round(price_pnl, 4),
            "pricePnlPct": round(price_pnl_pct, 4),
            "feeCost": round(fee_cost, 4),
            "totalPnl": round(trade_pnl, 4),
            "totalPnlPct": round(trade_pnl_pct, 4),
            "equityAfter": round(equity, 2),
        }
        trades.append(trade)

        equity_curve.append({
            "timestamp": settlement_ts,
            "equity": round(equity, 2),
            "datetime": _fmt_ts(settlement_ts),
        })

    # ===== MÉTRICAS =====
    total_trades = len(trades)
    total_pnl = equity - capital
    total_pnl_pct = ((equity - capital) / capital) * 100 if capital > 0 else 0

    if total_trades > 0:
        avg_pnl = total_pnl / total_trades
        avg_pnl_pct = total_pnl_pct / total_trades
        win_rate = (wins / total_trades) * 100
        best_trade = max(trades, key=lambda t: t["totalPnl"])
        worst_trade = min(trades, key=lambda t: t["totalPnl"])

        # Max drawdown
        peak = capital
        max_dd = 0
        for point in equity_curve:
            if point["equity"] > peak:
                peak = point["equity"]
            dd = ((peak - point["equity"]) / peak) * 100
            if dd > max_dd:
                max_dd = dd

        # Monthly return
        if days > 0:
            daily_return = total_pnl_pct / days
            monthly_return = daily_return * 30
        else:
            monthly_return = 0
    else:
        avg_pnl = avg_pnl_pct = win_rate = max_dd = monthly_return = 0
        best_trade = worst_trade = None

    return {
        "success": True,
        "symbol": symbol.upper(),
        "config": {
            "capital": capital,
            "days": days,
            "leverage": leverage,
            "feeType": fee_type,
            "feeRate": round(fee_rate * 100, 3),
            "entrySecondsBefore": entry_seconds_before,
            "exitSecondsAfter": exit_seconds_after,
            "targetTakeProfitPct": target_take_profit_pct,
        },
        "metrics": {
            "totalTrades": total_trades,
            "wins": wins,
            "losses": losses,
            "winRate": round(win_rate, 1),
            "initialCapital": capital,
            "finalEquity": round(equity, 2),
            "totalPnl": round(total_pnl, 2),
            "totalPnlPct": round(total_pnl_pct, 2),
            "avgPnlPerTrade": round(avg_pnl, 4),
            "avgPnlPctPerTrade": round(avg_pnl_pct, 4),
            "totalFundingReceived": round(total_funding_received, 2),
            "totalPricePnl": round(total_price_pnl, 2),
            "totalFeesPaid": round(total_fees_paid, 2),
            "maxDrawdown": round(max_dd, 2),
            "monthlyReturn": round(monthly_return, 2),
            "bestTrade": best_trade,
            "worstTrade": worst_trade,
        },
        "equityCurve": equity_curve,
        "trades": trades,
    }


def _empty_result(message: str) -> dict:
    return {
        "success": False,
        "message": message,
        "metrics": {},
        "equityCurve": [],
        "trades": [],
    }
