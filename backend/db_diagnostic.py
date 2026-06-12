"""
Diagnóstico profundo:
1. Investigar por que funding_rate_snapshots está vazio para moedas operadas
2. Auditar TODAS as tabelas do banco de dados
3. Verificar indexes, constraints, foreign keys, views
"""
import asyncio
import asyncpg
import os
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB_URL)
    output = []
    
    def p(text=""):
        output.append(str(text))
        print(text)

    p("=" * 100)
    p("DIAGNÓSTICO PROFUNDO DO BANCO DE DADOS")
    p(f"Data: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    p("=" * 100)

    # ============================================================
    # PARTE 1: INVESTIGAR FUNDING RATE SNAPSHOTS
    # ============================================================
    p("\n" + "=" * 80)
    p("PARTE 1: INVESTIGAÇÃO DOS SNAPSHOTS DE FUNDING RATE")
    p("=" * 80)

    # 1a. Total de registros
    total_snaps = await conn.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots")
    p(f"\n  1a. Total de registros em funding_rate_snapshots: {total_snaps}")

    # 1b. Range temporal dos snapshots
    snap_range = await conn.fetchrow("""
        SELECT MIN(captured_at) as oldest, MAX(captured_at) as newest, COUNT(DISTINCT DATE(captured_at)) as days
        FROM funding_rate_snapshots
    """)
    if snap_range:
        p(f"  1b. Oldest snapshot: {snap_range['oldest']}")
        p(f"      Newest snapshot: {snap_range['newest']}")
        p(f"      Distinct days:   {snap_range['days']}")

    # 1c. Contagem por exchange
    by_exchange = await conn.fetch("SELECT exchange, COUNT(*) as cnt FROM funding_rate_snapshots GROUP BY exchange ORDER BY cnt DESC")
    p(f"\n  1c. Registros por exchange:")
    for r in by_exchange:
        p(f"      {r['exchange']}: {r['cnt']}")

    # 1d. Symbols únicos
    sym_count = await conn.fetchval("SELECT COUNT(DISTINCT symbol) FROM funding_rate_snapshots")
    p(f"\n  1d. Symbols únicos nos snapshots: {sym_count}")

    # 1e. Amostra de symbols nos snapshots
    sample_syms = await conn.fetch("SELECT DISTINCT symbol FROM funding_rate_snapshots ORDER BY symbol LIMIT 30")
    p(f"  1e. Amostra de symbols nos snapshots:")
    for s in sample_syms:
        p(f"      {s['symbol']}")

    # 1f. Symbols operados nos trades
    traded_syms = await conn.fetch("SELECT DISTINCT symbol FROM real_trades ORDER BY symbol")
    p(f"\n  1f. Symbols operados nos trades ({len(traded_syms)}):")
    for s in traded_syms:
        p(f"      {s['symbol']}")

    # 1g. Cruzamento: quais symbols operados existem nos snapshots?
    p(f"\n  1g. Cruzamento symbol (trades vs snapshots):")
    for s in traded_syms:
        sym = s['symbol']
        cnt = await conn.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots WHERE symbol = $1", sym)
        # Tentar variações
        cnt_bybit = await conn.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots WHERE symbol = $1 AND exchange = 'bybit'", sym)
        cnt_binance = await conn.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots WHERE symbol = $1 AND exchange = 'binance'", sym)
        p(f"      {sym:20s} -> Total: {cnt:6d} | Bybit: {cnt_bybit:6d} | Binance: {cnt_binance:6d}")

    # 1h. Verificar se snapshots têm dados com funding_rate_pct != 0
    non_zero = await conn.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots WHERE funding_rate_pct != 0")
    p(f"\n  1h. Snapshots com funding_rate_pct != 0: {non_zero}")

    # 1i. Amostra de dados dos snapshots (últimas entradas)
    recent_snaps = await conn.fetch("""
        SELECT exchange, symbol, funding_rate, funding_rate_pct, volume_24h, price_24h_pcnt, captured_at
        FROM funding_rate_snapshots
        ORDER BY captured_at DESC
        LIMIT 10
    """)
    p(f"\n  1i. 10 snapshots mais recentes:")
    for r in recent_snaps:
        p(f"      {r['exchange']:8s} | {r['symbol']:15s} | FR: {float(r['funding_rate'] or 0):.6f} | FR%: {float(r['funding_rate_pct'] or 0):.4f}% | Vol: ${float(r['volume_24h'] or 0):,.0f} | Volat: {float(r['price_24h_pcnt'] or 0):.2f}% | {r['captured_at']}")

    # 1j. Snapshots dos últimos 2 dias especificamente
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    recent_count = await conn.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots WHERE captured_at >= $1", two_days_ago)
    p(f"\n  1j. Snapshots nos últimos 2 dias: {recent_count}")

    # Se existem dados nos últimos 2 dias, pegar amostra das moedas operadas
    if recent_count > 0:
        p(f"      Amostra de moedas operadas com dados recentes:")
        for s in traded_syms:
            sym = s['symbol']
            sample = await conn.fetchrow("""
                SELECT AVG(funding_rate_pct) as avg_fr, AVG(volume_24h) as avg_vol, COUNT(*) as cnt
                FROM funding_rate_snapshots 
                WHERE symbol = $1 AND captured_at >= $2
            """, sym, two_days_ago)
            if sample and sample['cnt'] > 0:
                p(f"      {sym:15s} | Cnt: {sample['cnt']} | AvgFR: {float(sample['avg_fr'] or 0):+.4f}% | AvgVol: ${float(sample['avg_vol'] or 0):,.0f}")

    # ============================================================
    # PARTE 2: AUDITORIA COMPLETA DO BANCO DE DADOS
    # ============================================================
    p("\n\n" + "=" * 80)
    p("PARTE 2: AUDITORIA COMPLETA DO BANCO DE DADOS")
    p("=" * 80)

    # 2a. TODAS as tabelas
    all_tables = await conn.fetch("""
        SELECT table_name, 
               (SELECT COUNT(*) FROM information_schema.columns c WHERE c.table_name = t.table_name AND c.table_schema = 'public') as col_count
        FROM information_schema.tables t
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    p(f"\n  2a. Todas as tabelas no schema public ({len(all_tables)}):")
    for t in all_tables:
        row_count = await conn.fetchval(f"SELECT COUNT(*) FROM \"{t['table_name']}\"")
        p(f"      {t['table_name']:40s} | Colunas: {t['col_count']:3d} | Registros: {row_count}")

    # 2b. Colunas de CADA tabela
    p(f"\n  2b. Detalhamento de colunas por tabela:")
    for t in all_tables:
        tname = t['table_name']
        cols = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = $1 AND table_schema = 'public'
            ORDER BY ordinal_position
        """, tname)
        p(f"\n      === {tname} ===")
        for c in cols:
            nullable = "NULL" if c['is_nullable'] == 'YES' else "NOT NULL"
            default = f" DEFAULT {c['column_default']}" if c['column_default'] else ""
            p(f"          {c['column_name']:35s} {c['data_type']:25s} {nullable:8s}{default}")

    # 2c. INDEXES existentes
    p(f"\n  2c. Indexes existentes:")
    indexes = await conn.fetch("""
        SELECT indexname, tablename, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
    """)
    for idx in indexes:
        p(f"      [{idx['tablename']}] {idx['indexname']}")
        p(f"          {idx['indexdef']}")

    # 2d. FOREIGN KEYS
    p(f"\n  2d. Foreign Keys:")
    fks = await conn.fetch("""
        SELECT 
            tc.table_name, 
            kcu.column_name, 
            ccu.table_name AS foreign_table,
            ccu.column_name AS foreign_column,
            tc.constraint_name
        FROM information_schema.table_constraints AS tc 
        JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
        ORDER BY tc.table_name
    """)
    for fk in fks:
        p(f"      {fk['table_name']}.{fk['column_name']} -> {fk['foreign_table']}.{fk['foreign_column']} ({fk['constraint_name']})")

    # 2e. UNIQUE CONSTRAINTS
    p(f"\n  2e. Unique Constraints:")
    uq = await conn.fetch("""
        SELECT tc.table_name, tc.constraint_name, string_agg(kcu.column_name, ', ') as columns
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
        WHERE tc.constraint_type = 'UNIQUE' AND tc.table_schema = 'public'
        GROUP BY tc.table_name, tc.constraint_name
        ORDER BY tc.table_name
    """)
    for u in uq:
        p(f"      [{u['table_name']}] {u['constraint_name']} ON ({u['columns']})")

    # 2f. VIEWS
    p(f"\n  2f. Views:")
    views = await conn.fetch("""
        SELECT table_name, view_definition
        FROM information_schema.views
        WHERE table_schema = 'public'
    """)
    if views:
        for v in views:
            p(f"      {v['table_name']}: {v['view_definition'][:200]}...")
    else:
        p("      Nenhuma view encontrada.")

    # 2g. SEQUENCES
    p(f"\n  2g. Sequences:")
    seqs = await conn.fetch("""
        SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public'
    """)
    for s in seqs:
        p(f"      {s['sequence_name']}")

    # Salvar
    report_path = os.path.join(os.path.dirname(__file__), "db_diagnostic_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    p(f"\nRelatório salvo em: {report_path}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
