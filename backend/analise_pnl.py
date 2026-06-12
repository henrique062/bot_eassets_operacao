"""
Script standalone de análise de PnL: compara trades do banco de dados com dados reais da Binance.

Uso:
    python analise_pnl.py

Dependências: psycopg2, requests (stdlib: hashlib, hmac, time, json)
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

import psycopg2
import psycopg2.extras
import requests

# Força UTF-8 no stdout para evitar UnicodeEncodeError no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
# Configurações
# ─────────────────────────────────────────────

DB_URL = "postgres://vorxia:91318244@69.62.92.189:5432/vorxia?sslmode=disable"
BINANCE_BASE_URL = "https://fapi.binance.com"
SLEEP_BETWEEN_CALLS = 0.2  # segundos entre chamadas à API

# Chaves de fallback — usadas quando o user_id não tem chaves cadastradas no banco
FALLBACK_API_KEYS: dict[str, str] = {
    "apiKey": "8gFLT1X1O5aKss3Fv4G9CrukHokBfjuJ2acnoT7trO4FbZKDHmQFGFHPYQdUG0Sa",
    "apiSecret": "jI31erxM0TeRJN0V5OM3NEEXp6dEOSRr3DBSEuWNT1GSQcHRKZQ0EooY1T9nT3rF",
}

BRT = timezone(timedelta(hours=-3))

# Threshold para marcar divergência no relatório
DIVERGENCE_THRESHOLD_USD = 0.05


# ─────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────

@dataclass
class TradeRow:
    """Linha da tabela real_trades enriquecida com dados do real_config."""

    id: int
    config_id: int
    user_id: int
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    funding_rate: float
    funding_pnl: float
    price_pnl: float
    price_pnl_pct: float
    fee_cost: float
    total_pnl: float
    total_pnl_pct: float
    balance_after: float
    open_time: str | None
    close_time: str | None
    trade_timestamp: int
    exchange: str
    close_reason: str | None
    reconciled_at: Any | None
    leverage: int
    capital: float


@dataclass
class BinanceIncome:
    """Dados consolidados do income history da Binance para um trade."""

    realized_pnl: float = 0.0
    commission: float = 0.0
    funding_fee: float = 0.0

    @property
    def total(self) -> float:
        return self.realized_pnl - abs(self.commission) + self.funding_fee


@dataclass
class TradeDelta:
    """Diferença entre DB e Binance para cada campo."""

    price_pnl: float = 0.0
    fee_cost: float = 0.0
    funding_pnl: float = 0.0
    total_pnl: float = 0.0

    @property
    def has_divergence(self) -> bool:
        return abs(self.total_pnl) > DIVERGENCE_THRESHOLD_USD


@dataclass
class AnalysisResult:
    """Resultado da análise de um único trade."""

    trade: TradeRow
    binance: BinanceIncome
    delta: TradeDelta
    error: str | None = None


@dataclass
class Summary:
    """Resumo agregado de toda a análise."""

    total_trades: int = 0
    reconciled: int = 0
    not_reconciled: int = 0
    with_divergence: int = 0
    skipped_no_keys: int = 0
    skipped_api_error: int = 0
    sum_delta_total: float = 0.0
    results: list[AnalysisResult] = field(default_factory=list)


# ─────────────────────────────────────────────
# Utilitários de tempo
# ─────────────────────────────────────────────

def parse_brt_to_ms(value: str | None) -> int | None:
    """Converte string 'DD/MM/YYYY HH:MM:SS' em BRT para timestamp ms UTC."""
    if not value:
        return None
    text = str(value).strip()
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%y %H:%M:%S"):
        try:
            dt = datetime.strptime(text, pattern).replace(tzinfo=BRT)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return None


def ms_to_brt_str(ts_ms: int | None) -> str:
    """Converte timestamp ms para string legível em BRT."""
    if not ts_ms:
        return "N/A"
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=BRT)
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def fmt_dt(raw: str | None) -> str:
    """Formata coluna open_time/close_time para exibição."""
    return raw if raw else "N/A"


# ─────────────────────────────────────────────
# Banco de dados
# ─────────────────────────────────────────────

def connect_db() -> psycopg2.extensions.connection:
    """Abre conexão síncrona com o PostgreSQL."""
    # Converte URL postgres:// para parâmetros psycopg2
    url = DB_URL.replace("postgres://", "postgresql://")
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    return conn


def fetch_trades(conn: psycopg2.extensions.connection) -> list[TradeRow]:
    """Busca todos os trades reais da Binance com dados do config."""
    sql = """
        SELECT
            rt.id,
            rt.config_id,
            rc.user_id,
            rt.symbol,
            rt.direction,
            rt.entry_price::float,
            rt.exit_price::float,
            rt.funding_rate::float,
            rt.funding_pnl::float,
            rt.price_pnl::float,
            COALESCE(rt.price_pnl_pct, 0)::float AS price_pnl_pct,
            rt.fee_cost::float,
            rt.total_pnl::float,
            rt.total_pnl_pct::float,
            rt.balance_after::float,
            rt.open_time,
            rt.close_time,
            rt.trade_timestamp,
            rt.exchange,
            rt.close_reason,
            rt.reconciled_at,
            rc.leverage,
            rc.capital::float
        FROM real_trades rt
        JOIN real_config rc ON rc.id = rt.config_id
        WHERE rt.exchange = 'binance'
        ORDER BY rt.trade_timestamp ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    trades: list[TradeRow] = []
    for r in rows:
        trades.append(TradeRow(
            id=int(r["id"]),
            config_id=int(r["config_id"]),
            user_id=int(r["user_id"]),
            symbol=str(r["symbol"]),
            direction=str(r["direction"]),
            entry_price=float(r["entry_price"]),
            exit_price=float(r["exit_price"]),
            funding_rate=float(r["funding_rate"]),
            funding_pnl=float(r["funding_pnl"]),
            price_pnl=float(r["price_pnl"]),
            price_pnl_pct=float(r["price_pnl_pct"]),
            fee_cost=float(r["fee_cost"]),
            total_pnl=float(r["total_pnl"]),
            total_pnl_pct=float(r["total_pnl_pct"]),
            balance_after=float(r["balance_after"]),
            open_time=r["open_time"],
            close_time=r["close_time"],
            trade_timestamp=int(r["trade_timestamp"]),
            exchange=str(r["exchange"]),
            close_reason=r["close_reason"],
            reconciled_at=r["reconciled_at"],
            leverage=int(r["leverage"]),
            capital=float(r["capital"]),
        ))
    return trades


def fetch_api_keys_by_user(
    conn: psycopg2.extensions.connection,
    user_ids: list[int],
) -> dict[int, dict[str, str]]:
    """Retorna {user_id: {"apiKey": ..., "apiSecret": ...}} para todos os user_ids fornecidos."""
    if not user_ids:
        return {}

    placeholders = ",".join(["%s"] * len(user_ids))
    sql = f"""
        SELECT user_id, value
        FROM user_settings
        WHERE key = 'api_keys_binance'
          AND user_id IN ({placeholders})
    """
    with conn.cursor() as cur:
        cur.execute(sql, user_ids)
        rows = cur.fetchall()

    result: dict[int, dict[str, str]] = {}
    for r in rows:
        uid = int(r["user_id"])
        raw = r["value"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                continue
        if isinstance(raw, dict) and raw.get("apiKey") and raw.get("apiSecret"):
            result[uid] = {"apiKey": str(raw["apiKey"]), "apiSecret": str(raw["apiSecret"])}
    return result


# ─────────────────────────────────────────────
# Binance Futures API
# ─────────────────────────────────────────────

def _binance_sign(params: dict[str, Any], secret: str) -> str:
    """Gera assinatura HMAC-SHA256 para a query string da Binance."""
    query = urllib.parse.urlencode(params)
    signature = hmac.new(
        secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def binance_income(
    api_key: str,
    api_secret: str,
    symbol: str,
    income_type: str,
    start_time: int,
    end_time: int,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    Consulta GET /fapi/v1/income na Binance Futures.

    Retorna lista de registros de income ou lista vazia em caso de erro.
    """
    endpoint = f"{BINANCE_BASE_URL}/fapi/v1/income"
    params: dict[str, Any] = {
        "symbol": symbol,
        "incomeType": income_type,
        "startTime": start_time,
        "endTime": end_time,
        "limit": limit,
        "timestamp": int(time.time() * 1000),
        "recvWindow": 10000,
    }
    params["signature"] = _binance_sign(params, api_secret)

    headers = {"X-MBX-APIKEY": api_key}

    try:
        resp = requests.get(endpoint, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        # Rate limit ou erro de API — registrar e retornar vazio
        print(
            f"    [Binance API] {income_type} {symbol} -> HTTP {resp.status_code}: {resp.text[:120]}"
        )
        return []
    except requests.RequestException as exc:
        print(f"    [Binance API] Erro de rede para {income_type} {symbol}: {exc}")
        return []


def fetch_binance_income_for_trade(
    api_key: str,
    api_secret: str,
    trade: TradeRow,
) -> BinanceIncome:
    """
    Busca os três tipos de income da Binance para um trade específico.

    Janela para REALIZED_PNL / COMMISSION: [trade_timestamp - 60s, trade_timestamp + 300s]
    Janela para FUNDING_FEE: [open_time_ms - 1s, close_time_ms + 300s]
    """
    result = BinanceIncome()

    close_ts = trade.trade_timestamp
    price_start = close_ts - 60_000
    price_end = close_ts + 300_000

    # ── REALIZED_PNL ──
    time.sleep(SLEEP_BETWEEN_CALLS)
    pnl_records = binance_income(
        api_key, api_secret,
        symbol=trade.symbol,
        income_type="REALIZED_PNL",
        start_time=price_start,
        end_time=price_end,
    )
    for rec in pnl_records:
        try:
            result.realized_pnl += float(rec.get("income", 0))
        except (TypeError, ValueError):
            pass

    # ── COMMISSION ──
    time.sleep(SLEEP_BETWEEN_CALLS)
    commission_records = binance_income(
        api_key, api_secret,
        symbol=trade.symbol,
        income_type="COMMISSION",
        start_time=price_start,
        end_time=price_end,
    )
    for rec in commission_records:
        try:
            result.commission += float(rec.get("income", 0))
        except (TypeError, ValueError):
            pass

    # ── FUNDING_FEE ──
    open_ts = parse_brt_to_ms(trade.open_time) if trade.open_time else None
    close_ts_from_col = parse_brt_to_ms(trade.close_time) if trade.close_time else None

    # Fallback: usar trade_timestamp como close e abrir 1h antes caso não tenhamos open_time
    funding_start = (open_ts - 1_000) if open_ts else (close_ts - 3_600_000)
    funding_end = (close_ts_from_col + 300_000) if close_ts_from_col else (close_ts + 300_000)

    time.sleep(SLEEP_BETWEEN_CALLS)
    funding_records = binance_income(
        api_key, api_secret,
        symbol=trade.symbol,
        income_type="FUNDING_FEE",
        start_time=funding_start,
        end_time=funding_end,
    )
    for rec in funding_records:
        try:
            result.funding_fee += float(rec.get("income", 0))
        except (TypeError, ValueError):
            pass

    return result


# ─────────────────────────────────────────────
# Cálculo de delta
# ─────────────────────────────────────────────

def compute_delta(trade: TradeRow, binance: BinanceIncome) -> TradeDelta:
    """
    Calcula diferença entre valores do DB e valores reais da Binance.

    Convenção de sinal:
      - positivo = Binance reportou MAIS do que o DB registrou
      - negativo = Binance reportou MENOS do que o DB registrou

    A Binance reporta COMMISSION como valor negativo (custo).
    O DB armazena fee_cost como valor positivo.
    O DB armazena funding_pnl como valor positivo (sempre ganho no modelo atual).
    """
    # price_pnl: DB é positivo para lucro, Binance REALIZED_PNL também
    delta_price = binance.realized_pnl - trade.price_pnl

    # fee_cost: DB é positivo (custo), Binance é negativo (comissão paga)
    # Normalizamos para custo positivo antes de comparar
    db_fee_abs = abs(trade.fee_cost)
    binance_fee_abs = abs(binance.commission)
    delta_fee = binance_fee_abs - db_fee_abs

    # funding_pnl: DB é positivo (ganho do funding), Binance pode ser pos ou neg
    delta_funding = binance.funding_fee - trade.funding_pnl

    # total: DB total vs Binance total calculado
    binance_total = binance.realized_pnl - binance_fee_abs + binance.funding_fee
    delta_total = binance_total - trade.total_pnl

    return TradeDelta(
        price_pnl=delta_price,
        fee_cost=delta_fee,
        funding_pnl=delta_funding,
        total_pnl=delta_total,
    )


# ─────────────────────────────────────────────
# Relatório de saída
# ─────────────────────────────────────────────

def fmt_usd(value: float) -> str:
    """Formata valor em USD com sinal."""
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:.4f}"


def fmt_usd_plain(value: float) -> str:
    """Formata valor em USD sem sinal explícito."""
    return f"${value:.4f}"


def print_trade_result(result: AnalysisResult, index: int) -> None:
    """Imprime análise detalhada de um único trade."""
    t = result.trade
    b = result.binance
    d = result.delta

    open_label = fmt_dt(t.open_time)
    close_label = fmt_dt(t.close_time)
    reconciled_label = "reconciliado" if t.reconciled_at else "sem reconciliação"
    divergence_marker = "  <-- DIVERGENCIA" if d.has_divergence else ""

    print(f"\nTrade #{t.id} | {t.symbol} {t.direction} | {open_label} -> {close_label} [{reconciled_label}]")

    if result.error:
        print(f"  ERRO: {result.error}")
        return

    print(
        f"  DB:      price_pnl={fmt_usd_plain(t.price_pnl)}"
        f"  fee={fmt_usd_plain(t.fee_cost)}"
        f"  funding={fmt_usd_plain(t.funding_pnl)}"
        f"  total={fmt_usd_plain(t.total_pnl)}"
    )
    print(
        f"  Binance: price_pnl={fmt_usd_plain(b.realized_pnl)}"
        f"  fee={fmt_usd_plain(abs(b.commission))}"
        f"  funding={fmt_usd_plain(b.funding_fee)}"
        f"  total={fmt_usd_plain(b.total)}"
    )
    print(
        f"  DELTA:   price_pnl={fmt_usd(d.price_pnl)}"
        f"  fee={fmt_usd(d.fee_cost)}"
        f"  funding={fmt_usd(d.funding_pnl)}"
        f"  total={fmt_usd(d.total_pnl)}"
        f"{divergence_marker}"
    )


def print_summary(summary: Summary) -> None:
    """Imprime resumo agregado da análise."""
    print("\n" + "=" * 60)
    print("=== RESUMO ===")
    print("=" * 60)
    print(f"Total trades analisados:          {summary.total_trades}")
    print(f"Com reconciliacao no DB:          {summary.reconciled}")
    print(f"Sem reconciliacao:                {summary.not_reconciled}")
    print(f"Ignorados (sem chaves API):       {summary.skipped_no_keys}")
    print(f"Ignorados (erro de API):          {summary.skipped_api_error}")
    print(
        f"Trades com |delta total| > ${DIVERGENCE_THRESHOLD_USD:.2f}: "
        f"{summary.with_divergence}"
    )
    print(f"Soma total delta:                 {fmt_usd(summary.sum_delta_total)}")

    if summary.results:
        divergent = [r for r in summary.results if r.delta.has_divergence and not r.error]
        if divergent:
            print(f"\nTrades com divergencia (|delta| > ${DIVERGENCE_THRESHOLD_USD:.2f}):")
            for r in divergent:
                t = r.trade
                print(
                    f"  Trade #{t.id} {t.symbol} {t.direction} "
                    f"delta_total={fmt_usd(r.delta.total_pnl)}"
                )


# ─────────────────────────────────────────────
# Ponto de entrada principal
# ─────────────────────────────────────────────

def main() -> None:
    """Executa análise completa de PnL: DB vs Binance."""
    print("=" * 60)
    print("=== ANALISE PnL DB vs BINANCE ===")
    print("=" * 60)

    # ── Conectar ao banco ──
    print("\nConectando ao banco de dados...")
    try:
        conn = connect_db()
    except Exception as exc:
        print(f"ERRO ao conectar ao banco: {exc}")
        return

    # ── Buscar trades ──
    print("Buscando trades da tabela real_trades...")
    try:
        trades = fetch_trades(conn)
    except Exception as exc:
        print(f"ERRO ao buscar trades: {exc}")
        conn.close()
        return

    if not trades:
        print("Nenhum trade encontrado na tabela real_trades com exchange='binance'.")
        conn.close()
        return

    print(f"Encontrados {len(trades)} trade(s) para analisar.")

    # ── Buscar chaves API por user_id único ──
    unique_user_ids = list({t.user_id for t in trades})
    print(f"Buscando chaves de API para {len(unique_user_ids)} usuario(s)...")
    try:
        keys_by_user = fetch_api_keys_by_user(conn, unique_user_ids)
    except Exception as exc:
        print(f"ERRO ao buscar chaves de API: {exc}")
        conn.close()
        return

    users_with_keys = set(keys_by_user.keys())
    users_without_keys = set(unique_user_ids) - users_with_keys
    if users_without_keys:
        print(
            f"AVISO: user_id(s) sem chaves no DB: {sorted(users_without_keys)}"
            " -- usando chaves de fallback para esses usuarios."
        )

    conn.close()

    # ── Analisar cada trade ──
    print("\n" + "=" * 60)
    summary = Summary(total_trades=len(trades))

    for i, trade in enumerate(trades):
        if trade.reconciled_at:
            summary.reconciled += 1
        else:
            summary.not_reconciled += 1

        keys = keys_by_user.get(trade.user_id) or (FALLBACK_API_KEYS if FALLBACK_API_KEYS.get("apiKey") else None)
        if not keys:
            summary.skipped_no_keys += 1
            result = AnalysisResult(
                trade=trade,
                binance=BinanceIncome(),
                delta=TradeDelta(),
                error=f"Sem chaves de API para user_id={trade.user_id}",
            )
            summary.results.append(result)
            print_trade_result(result, i)
            continue

        # Chamar Binance
        try:
            binance_data = fetch_binance_income_for_trade(
                api_key=keys["apiKey"],
                api_secret=keys["apiSecret"],
                trade=trade,
            )
        except Exception as exc:
            summary.skipped_api_error += 1
            result = AnalysisResult(
                trade=trade,
                binance=BinanceIncome(),
                delta=TradeDelta(),
                error=f"Erro ao consultar Binance: {exc}",
            )
            summary.results.append(result)
            print_trade_result(result, i)
            continue

        delta = compute_delta(trade, binance_data)
        result = AnalysisResult(trade=trade, binance=binance_data, delta=delta)
        summary.results.append(result)

        if delta.has_divergence:
            summary.with_divergence += 1

        summary.sum_delta_total += delta.total_pnl
        print_trade_result(result, i)

    print_summary(summary)
    print()


if __name__ == "__main__":
    main()
