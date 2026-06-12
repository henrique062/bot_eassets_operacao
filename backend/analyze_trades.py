"""
Análise completa das operações reais e histórico de funding rates.
Objetivo: avaliar se o score e as configurações estão otimizados para reduzir perdas e aumentar lucros.
"""
import asyncio
import asyncpg
import os
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgres://vorxia:91318244@69.62.92.189:5432/vorxia?sslmode=disable")

async def main():
    conn = await asyncpg.connect(DB_URL)
    output = []
    
    def p(text=""):
        output.append(str(text))
        print(text)

    p("=" * 100)
    p("ANÁLISE COMPLETA DE OPERAÇÕES REAIS + SCORE + FUNDING RATES")
    p(f"Data da Análise: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    p("=" * 100)

    # ============================================================
    # 1. RESUMO GERAL DAS OPERAÇÕES
    # ============================================================
    p("\n" + "=" * 60)
    p("1. RESUMO GERAL DAS OPERAÇÕES REAIS")
    p("=" * 60)

    summary = await conn.fetchrow("""
        SELECT 
            COUNT(*) as total_trades,
            COUNT(*) FILTER (WHERE total_pnl > 0) as wins,
            COUNT(*) FILTER (WHERE total_pnl < 0) as losses,
            COUNT(*) FILTER (WHERE total_pnl = 0) as breakeven,
            COALESCE(SUM(total_pnl), 0) as total_pnl,
            COALESCE(AVG(total_pnl), 0) as avg_pnl,
            COALESCE(SUM(funding_pnl), 0) as total_funding_pnl,
            COALESCE(SUM(price_pnl), 0) as total_price_pnl,
            COALESCE(SUM(fee_cost), 0) as total_fees,
            MIN(close_time) as first_trade,
            MAX(close_time) as last_trade
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
    """)

    if summary:
        total = summary['total_trades']
        wins = summary['wins']
        losses = summary['losses']
        winrate = (wins / total * 100) if total > 0 else 0
        p(f"  Total de Trades:      {total}")
        p(f"  Vitórias (Win):       {wins} ({winrate:.1f}%)")
        p(f"  Derrotas (Loss):      {losses} ({100-winrate:.1f}%)")
        p(f"  Breakeven:            {summary['breakeven']}")
        p(f"  PnL Total:            ${float(summary['total_pnl']):.4f}")
        p(f"  PnL Médio por Trade:  ${float(summary['avg_pnl']):.4f}")
        p(f"  Funding PnL Total:    ${float(summary['total_funding_pnl']):.4f}")
        p(f"  Price PnL Total:      ${float(summary['total_price_pnl']):.4f}")
        p(f"  Taxas Totais (Fees):  ${float(summary['total_fees']):.4f}")
        p(f"  Primeiro Trade:       {summary['first_trade']}")
        p(f"  Último Trade:         {summary['last_trade']}")

    # ============================================================
    # 2. ANÁLISE POR MOEDA (SYMBOL)
    # ============================================================
    p("\n" + "=" * 60)
    p("2. ANÁLISE POR MOEDA (TOP 20 POR VOLUME DE TRADES)")
    p("=" * 60)

    by_symbol = await conn.fetch("""
        SELECT 
            symbol,
            COUNT(*) as trades,
            COUNT(*) FILTER (WHERE total_pnl > 0) as wins,
            COUNT(*) FILTER (WHERE total_pnl < 0) as losses,
            COALESCE(SUM(total_pnl), 0) as total_pnl,
            COALESCE(SUM(funding_pnl), 0) as funding_pnl,
            COALESCE(SUM(price_pnl), 0) as price_pnl,
            COALESCE(SUM(fee_cost), 0) as fees
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
        GROUP BY symbol
        ORDER BY trades DESC
        LIMIT 20
    """)

    for r in by_symbol:
        trades = r['trades']
        wr = (r['wins'] / trades * 100) if trades > 0 else 0
        p(f"\n  {r['symbol']}")
        p(f"    Trades: {trades} | WinRate: {wr:.0f}% | PnL: ${float(r['total_pnl']):.4f} | Funding: ${float(r['funding_pnl']):.4f} | Price: ${float(r['price_pnl']):.4f} | Fees: ${float(r['fees']):.4f}")

    # ============================================================
    # 3. MOEDAS MAIS LUCRATIVAS vs MAIS PREJUDICIAIS
    # ============================================================
    p("\n" + "=" * 60)
    p("3. TOP 10 MOEDAS MAIS LUCRATIVAS")
    p("=" * 60)

    top_profit = await conn.fetch("""
        SELECT symbol, COUNT(*) as trades, SUM(total_pnl) as total_pnl, SUM(funding_pnl) as fund, SUM(price_pnl) as price
        FROM real_trades WHERE close_time IS NOT NULL AND close_time != ''
        GROUP BY symbol ORDER BY total_pnl DESC LIMIT 10
    """)
    for r in top_profit:
        p(f"  {r['symbol']:20s} | {r['trades']:3d} trades | PnL: ${float(r['total_pnl']):+.4f} | Fund: ${float(r['fund']):+.4f} | Price: ${float(r['price']):+.4f}")

    p("\n" + "=" * 60)
    p("4. TOP 10 MOEDAS MAIS PREJUDICIAIS")
    p("=" * 60)

    top_loss = await conn.fetch("""
        SELECT symbol, COUNT(*) as trades, SUM(total_pnl) as total_pnl, SUM(funding_pnl) as fund, SUM(price_pnl) as price
        FROM real_trades WHERE close_time IS NOT NULL AND close_time != ''
        GROUP BY symbol ORDER BY total_pnl ASC LIMIT 10
    """)
    for r in top_loss:
        p(f"  {r['symbol']:20s} | {r['trades']:3d} trades | PnL: ${float(r['total_pnl']):+.4f} | Fund: ${float(r['fund']):+.4f} | Price: ${float(r['price']):+.4f}")

    # ============================================================
    # 5. ANÁLISE POR CLOSE_REASON (motivo de fechamento)
    # ============================================================
    p("\n" + "=" * 60)
    p("5. ANÁLISE POR MOTIVO DE FECHAMENTO")
    p("=" * 60)

    by_reason = await conn.fetch("""
        SELECT 
            COALESCE(close_reason, 'unknown') as reason,
            COUNT(*) as trades,
            COUNT(*) FILTER (WHERE total_pnl > 0) as wins,
            SUM(total_pnl) as total_pnl,
            AVG(total_pnl) as avg_pnl
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
        GROUP BY close_reason
        ORDER BY trades DESC
    """)
    for r in by_reason:
        trades = r['trades']
        wr = (r['wins'] / trades * 100) if trades > 0 else 0
        p(f"  {str(r['reason']):30s} | {trades:4d} trades | WinRate: {wr:.0f}% | PnL Total: ${float(r['total_pnl']):+.4f} | PnL Médio: ${float(r['avg_pnl']):+.6f}")

    # ============================================================
    # 6. ANÁLISE POR DIREÇÃO (LONG vs SHORT)
    # ============================================================
    p("\n" + "=" * 60)
    p("6. ANÁLISE POR DIREÇÃO (LONG vs SHORT)")
    p("=" * 60)

    by_dir = await conn.fetch("""
        SELECT 
            direction,
            COUNT(*) as trades,
            COUNT(*) FILTER (WHERE total_pnl > 0) as wins,
            SUM(total_pnl) as total_pnl,
            SUM(funding_pnl) as funding_pnl,
            SUM(price_pnl) as price_pnl,
            AVG(total_pnl) as avg_pnl
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
        GROUP BY direction
    """)
    for r in by_dir:
        trades = r['trades']
        wr = (r['wins'] / trades * 100) if trades > 0 else 0
        p(f"  {str(r['direction']):10s} | {trades:4d} trades | WinRate: {wr:.0f}% | PnL: ${float(r['total_pnl']):+.4f} | Funding: ${float(r['funding_pnl']):+.4f} | Price: ${float(r['price_pnl']):+.4f}")

    # ============================================================
    # 7. TRADES COM MAIORES PERDAS (individual)
    # ============================================================
    p("\n" + "=" * 60)
    p("7. TOP 15 MAIORES PERDAS INDIVIDUAIS")
    p("=" * 60)

    worst = await conn.fetch("""
        SELECT symbol, direction, entry_price, exit_price, total_pnl, funding_pnl, price_pnl, price_pnl_pct, fee_cost, close_reason, open_time, close_time
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
        ORDER BY total_pnl ASC
        LIMIT 15
    """)
    for r in worst:
        p(f"  {r['symbol']:15s} | Dir: {str(r['direction']):5s} | Entry: {float(r['entry_price']):.6f} | Exit: {float(r['exit_price'] or 0):.6f} | PnL: ${float(r['total_pnl']):+.4f} | Fund: ${float(r['funding_pnl']):+.4f} | PricePnL%: {float(r['price_pnl_pct'] or 0):+.3f}% | Fees: ${float(r['fee_cost']):.4f} | {r['close_reason']}")

    # ============================================================
    # 8. TRADES COM MAIORES LUCROS (individual)
    # ============================================================
    p("\n" + "=" * 60)
    p("8. TOP 15 MAIORES LUCROS INDIVIDUAIS")
    p("=" * 60)

    best = await conn.fetch("""
        SELECT symbol, direction, entry_price, exit_price, total_pnl, funding_pnl, price_pnl, price_pnl_pct, fee_cost, close_reason, open_time, close_time
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
        ORDER BY total_pnl DESC
        LIMIT 15
    """)
    for r in best:
        p(f"  {r['symbol']:15s} | Dir: {str(r['direction']):5s} | Entry: {float(r['entry_price']):.6f} | Exit: {float(r['exit_price'] or 0):.6f} | PnL: ${float(r['total_pnl']):+.4f} | Fund: ${float(r['funding_pnl']):+.4f} | PricePnL%: {float(r['price_pnl_pct'] or 0):+.3f}% | Fees: ${float(r['fee_cost']):.4f} | {r['close_reason']}")

    # ============================================================
    # 9. CONFIGURAÇÕES ATIVAS DOS BOTS
    # ============================================================
    p("\n" + "=" * 60)
    p("9. CONFIGURAÇÕES DOS BOTS REAIS")
    p("=" * 60)

    configs = await conn.fetch("""
        SELECT id, session_name, exchange, active, capital, balance, leverage, fee_type, fee_rate, 
               auto_mode, stop_loss_pct, stop_loss_usd, min_profit_pct, entry_seconds, exit_seconds,
               operation_mode, auto_direction, auto_max_symbols, auto_min_score, auto_window_minutes,
               maker_timeout_seconds, ct_sort_criteria, trailing_stop_pct, target_take_profit_pct,
               started_at, created_at
        FROM real_config
        ORDER BY id
    """)
    for c in configs:
        p(f"\n  Bot #{c['id']}: {c['session_name']} ({c['exchange']}) - Ativo: {c['active']}")
        p(f"    Capital: ${float(c['capital'] or 0):.2f} | Balance: ${float(c['balance'] or 0):.2f} | Leverage: {c['leverage']}x")
        p(f"    Fee: {c['fee_type']} @ {float(c['fee_rate'] or 0):.4f}%")
        p(f"    Auto Mode: {c['auto_mode']} | Op Mode: {c['operation_mode']} | Direction: {c['auto_direction']}")
        p(f"    Auto Max Symbols: {c['auto_max_symbols']} | Auto Min Score: {c['auto_min_score']} | Window: {c['auto_window_minutes']}min")
        p(f"    Stop Loss: {float(c['stop_loss_pct'] or 0):.2f}% / ${float(c['stop_loss_usd'] or 0):.2f} | Min Profit: {float(c['min_profit_pct'] or 0):.2f}%")
        p(f"    Entry: {c['entry_seconds']}s | Exit: {c['exit_seconds']}s | Maker Timeout: {c['maker_timeout_seconds']}s")
        p(f"    CT Sort: {c['ct_sort_criteria']} | Trailing Stop: {float(c['trailing_stop_pct'] or 0):.2f}% | Take Profit: {float(c['target_take_profit_pct'] or 0):.2f}%")

    # ============================================================
    # 10. CONFIGURAÇÕES DO SCORE (system_settings)
    # ============================================================
    p("\n" + "=" * 60)
    p("10. CONFIGURAÇÕES DO SISTEMA DE SCORE")
    p("=" * 60)

    settings = await conn.fetch("""
        SELECT key, value FROM system_settings
        WHERE key IN ('score_thresholds', 'score_weights', 'score_limits')
    """)
    if settings:
        for s in settings:
            p(f"  {s['key']}: {s['value']}")
    else:
        p("  Nenhuma configuração customizada encontrada (usando defaults)")
        p("  Defaults: thresholds={forte:75, moderado:50, fraco:30}, weights={mag:30, rr:30, vol:20, int:10, urg:10}, limits={max_volatility:35, min_volume:2000000}")

    # ============================================================
    # 11. HISTÓRICO DE FUNDING RATES (ÚLTIMOS 2 DIAS)
    # ============================================================
    p("\n" + "=" * 60)
    p("11. HISTÓRICO DE FUNDING RATES (ÚLTIMOS 2 DIAS)")
    p("=" * 60)

    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)

    funding_hist = await conn.fetch("""
        SELECT 
            symbol,
            COUNT(*) as snapshots,
            AVG(funding_rate_pct::numeric) as avg_rate_pct,
            MAX(funding_rate_pct::numeric) as max_rate_pct,
            MIN(funding_rate_pct::numeric) as min_rate_pct,
            STDDEV(funding_rate_pct::numeric) as std_rate_pct,
            AVG(volume_24h::numeric) as avg_volume,
            AVG(price_24h_pcnt::numeric) as avg_volatility
        FROM funding_rate_snapshots
        WHERE captured_at >= $1
        GROUP BY symbol
        HAVING COUNT(*) >= 3
        ORDER BY ABS(AVG(funding_rate_pct::numeric)) DESC
        LIMIT 30
    """, two_days_ago)

    p(f"  Top 30 moedas por magnitude de taxa média (desde {two_days_ago.strftime('%Y-%m-%d %H:%M UTC')}):")
    for r in funding_hist:
        p(f"  {r['symbol']:15s} | Snaps: {r['snapshots']:3d} | AvgRate: {float(r['avg_rate_pct']):+.4f}% | MaxRate: {float(r['max_rate_pct']):+.4f}% | MinRate: {float(r['min_rate_pct']):+.4f}% | StdDev: {float(r['std_rate_pct'] or 0):.4f} | AvgVol: ${float(r['avg_volume'] or 0):,.0f} | AvgVolat: {float(r['avg_volatility'] or 0):.2f}%")

    # ============================================================
    # 12. CRUZAMENTO: MOEDAS OPERADAS vs FUNDING HISTÓRICO
    # ============================================================
    p("\n" + "=" * 60)
    p("12. CRUZAMENTO: MOEDAS OPERADAS vs HISTORICO DE FUNDING (2 DIAS)")
    p("=" * 60)

    cross = await conn.fetch("""
        WITH traded AS (
            SELECT DISTINCT symbol FROM real_trades WHERE close_time IS NOT NULL AND close_time != ''
        ),
        funding AS (
            SELECT 
                symbol,
                AVG(funding_rate_pct::numeric) as avg_rate,
                STDDEV(funding_rate_pct::numeric) as std_rate,
                AVG(volume_24h::numeric) as avg_vol,
                AVG(price_24h_pcnt::numeric) as avg_volat,
                COUNT(*) as snaps
            FROM funding_rate_snapshots
            WHERE captured_at >= $1
            GROUP BY symbol
        )
        SELECT 
            t.symbol,
            rt.trades,
            rt.total_pnl,
            rt.winrate,
            f.avg_rate,
            f.std_rate,
            f.avg_vol,
            f.avg_volat
        FROM traded t
        JOIN (
            SELECT symbol, COUNT(*) as trades, SUM(total_pnl) as total_pnl,
                   ROUND(COUNT(*) FILTER (WHERE total_pnl > 0)::numeric / NULLIF(COUNT(*), 0) * 100, 1) as winrate
            FROM real_trades WHERE close_time IS NOT NULL AND close_time != '' GROUP BY symbol
        ) rt ON rt.symbol = t.symbol
        LEFT JOIN funding f ON f.symbol = t.symbol
        ORDER BY rt.total_pnl ASC
    """, two_days_ago)

    for r in cross:
        avg_rate = float(r['avg_rate'] or 0)
        std_rate = float(r['std_rate'] or 0)
        avg_vol = float(r['avg_vol'] or 0)
        avg_volat = float(r['avg_volat'] or 0)
        p(f"  {r['symbol']:15s} | {r['trades']:3d} trades | WR: {float(r['winrate'] or 0):.0f}% | PnL: ${float(r['total_pnl']):+.4f} | AvgFR: {avg_rate:+.4f}% | StdFR: {std_rate:.4f} | Vol24h: ${avg_vol:,.0f} | Volat: {avg_volat:.2f}%")

    # ============================================================
    # 13. ANÁLISE TEMPORAL (PnL por dia)
    # ============================================================
    p("\n" + "=" * 60)
    p("13. PnL POR DIA")
    p("=" * 60)

    by_day = await conn.fetch("""
        SELECT 
            LEFT(open_time, 10) as dia,
            COUNT(*) as trades,
            SUM(total_pnl) as pnl,
            COUNT(*) FILTER (WHERE total_pnl > 0) as wins
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
        GROUP BY LEFT(open_time, 10)
        ORDER BY dia DESC
        LIMIT 14
    """)
    for r in by_day:
        trades = r['trades']
        wr = (r['wins'] / trades * 100) if trades > 0 else 0
        p(f"  {r['dia']} | {trades:4d} trades | WR: {wr:.0f}% | PnL: ${float(r['pnl']):+.4f}")

    # ============================================================
    # 14. ANÁLISE DE FEES vs LUCROS
    # ============================================================
    p("\n" + "=" * 60)
    p("14. ANÁLISE DE FEES vs LUCROS")
    p("=" * 60)

    fee_analysis = await conn.fetchrow("""
        SELECT 
            SUM(fee_cost) as total_fees,
            SUM(funding_pnl) as total_funding,
            SUM(price_pnl) as total_price,
            SUM(total_pnl) as total_pnl,
            AVG(fee_cost) as avg_fee,
            AVG(funding_pnl) as avg_funding
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
    """)
    if fee_analysis:
        total_fees = float(fee_analysis['total_fees'] or 0)
        total_funding = float(fee_analysis['total_funding'] or 0)
        total_price = float(fee_analysis['total_price'] or 0)
        p(f"  Total Fees Pagos:       ${total_fees:.4f}")
        p(f"  Total Funding Recebido: ${total_funding:+.4f}")
        p(f"  Total Variação Preço:   ${total_price:+.4f}")
        if total_funding != 0:
            p(f"  Ratio Fees/Funding:     {abs(total_fees/total_funding)*100:.1f}% (% do funding que vai pra fees)")
        p(f"  Fee Médio por Trade:    ${float(fee_analysis['avg_fee'] or 0):.6f}")
        p(f"  Funding Médio por Trade:${float(fee_analysis['avg_funding'] or 0):+.6f}")

    # ============================================================
    # 15. PnL POR FAIXA DE PRICE_PNL_PCT (entender onde perdem mais)
    # ============================================================
    p("\n" + "=" * 60)
    p("15. DISTRIBUIÇÃO DE VARIAÇÃO DE PREÇO (PricePnL%)")
    p("=" * 60)

    pnl_dist = await conn.fetch("""
        SELECT 
            CASE 
                WHEN price_pnl_pct < -2 THEN '< -2%'
                WHEN price_pnl_pct < -1 THEN '-2% a -1%'
                WHEN price_pnl_pct < -0.5 THEN '-1% a -0.5%'
                WHEN price_pnl_pct < 0 THEN '-0.5% a 0%'
                WHEN price_pnl_pct < 0.5 THEN '0% a +0.5%'
                WHEN price_pnl_pct < 1 THEN '+0.5% a +1%'
                WHEN price_pnl_pct < 2 THEN '+1% a +2%'
                ELSE '> +2%'
            END as faixa,
            COUNT(*) as trades,
            SUM(total_pnl) as total_pnl,
            AVG(total_pnl) as avg_pnl
        FROM real_trades
        WHERE close_time IS NOT NULL AND close_time != ''
        GROUP BY faixa
        ORDER BY MIN(price_pnl_pct)
    """)
    for r in pnl_dist:
        p(f"  {str(r['faixa']):15s} | {r['trades']:4d} trades | PnL Total: ${float(r['total_pnl']):+.4f} | PnL Médio: ${float(r['avg_pnl']):+.6f}")

    # ============================================================
    # 16. TRADES ABERTOS (posições ativas agora)
    # ============================================================
    p("\n" + "=" * 60)
    p("16. TRADES ABERTOS (POSIÇÕES ATIVAS AGORA)")
    p("=" * 60)

    open_trades = await conn.fetch("""
        SELECT symbol, direction, entry_price, funding_pnl, price_pnl, fee_cost, total_pnl, open_time, config_id
        FROM real_trades
        WHERE close_time IS NULL OR close_time = ''
        ORDER BY open_time DESC
    """)
    if open_trades:
        for r in open_trades:
            p(f"  {r['symbol']:15s} | Dir: {str(r['direction']):5s} | Entry: {float(r['entry_price']):.6f} | PnL: ${float(r['total_pnl'] or 0):+.4f} | Fund: ${float(r['funding_pnl'] or 0):+.4f} | Open: {r['open_time']} | Bot #{r['config_id']}")
    else:
        p("  Nenhuma posição aberta no momento.")

    # Salvar em arquivo
    report_path = os.path.join(os.path.dirname(__file__), "trade_analysis_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    p(f"\nRelatório salvo em: {report_path}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
