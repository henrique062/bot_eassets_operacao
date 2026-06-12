"use client"

import { useMemo, useState, type ReactNode } from "react"
import Link from "next/link"
import type { PanelData, PanelRow } from "@/lib/types"
import {
  fmtPrice,
  fmtNum,
  fmtCompact,
  fmtUsd,
  colorPN,
  colorToi,
  setupBadgeStyle,
} from "@/lib/panel-format"
import { MacroBanner } from "@/components/panel/macro-banner"

const VIEW_OPTIONS = [10, 25, 50, 0] as const

export function PanelView({
  data,
  error,
  isLoading,
  selector,
}: {
  data: PanelData | undefined
  error?: unknown
  isLoading?: boolean
  selector?: ReactNode
}) {
  const [limit, setLimit] = useState<number>(25)
  const rows = useMemo(() => data?.rows ?? [], [data])
  const visible = limit === 0 ? rows : rows.slice(0, limit)

  const kpis = useMemo(() => {
    if (!rows.length) return null
    const byScore = [...rows].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0]
    const byExp1d = [...rows].filter((r) => r.exp1d != null).sort((a, b) => (b.exp1d ?? 0) - (a.exp1d ?? 0))[0]
    const byExp4h = [...rows].filter((r) => r.exp4h != null).sort((a, b) => (b.exp4h ?? 0) - (a.exp4h ?? 0))[0]
    return { byScore, byExp1d, byExp4h }
  }, [rows])

  return (
    <div className="flex flex-col gap-6">
      {error ? (
        <div
          role="alert"
          className="rounded-2xl border border-[#FECDCA] bg-[#FEF3F2] px-6 py-4 text-sm text-[#B42318]"
        >
          Erro ao carregar o painel. Verifique se já existe algum snapshot capturado.
        </div>
      ) : null}

      <MacroBanner btc={data?.btc} />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch">
        <div className="grid flex-1 grid-cols-2 gap-4 sm:grid-cols-4">
          <KpiCard label="Top Score" value={kpis?.byScore?.asset ?? "—"} sub={`score ${kpis?.byScore?.score ?? "—"}`} />
          <KpiCard label="Maior EXP 1D" value={fmtNum(kpis?.byExp1d?.exp1d, 2, true)} sub={kpis?.byExp1d?.asset ?? "—"} positive />
          <KpiCard label="Maior EXP 4H" value={fmtNum(kpis?.byExp4h?.exp4h, 2, true)} sub={kpis?.byExp4h?.asset ?? "—"} positive />
          <KpiCard label="Ativos" value={String(data?.meta?.symbols ?? rows.length)} sub={data?.meta?.exchange ?? "eassets"} />
        </div>
        {selector}
      </div>

      <div className="overflow-hidden rounded-2xl border border-[#EAECF0] bg-white shadow-[0_8px_24px_rgba(16,24,40,0.06)]">
        <div className="overflow-x-auto">
          <PanelTable rows={visible} loading={Boolean(isLoading)} />
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-[#EAECF0] bg-[#FCFCFD] px-5 py-3">
          <span className="mr-auto text-xs text-[#667085]">
            Exibindo {limit === 0 ? "todos os" : `TOP ${limit} de`} {rows.length} ativos
          </span>
          {VIEW_OPTIONS.map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setLimit(n)}
              className="rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors"
              style={
                limit === n
                  ? { backgroundColor: "#6366f1", borderColor: "#6366f1", color: "#FFFFFF" }
                  : { backgroundColor: "#FFFFFF", borderColor: "#D0D5DD", color: "#475467" }
              }
            >
              {n === 0 ? `TODOS (${rows.length})` : `TOP ${n}`}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export function KpiCard({
  label,
  value,
  sub,
  positive,
}: {
  label: string
  value: string
  sub: string
  positive?: boolean
}) {
  return (
    <div className="rounded-2xl border border-[#EAECF0] bg-white px-5 py-4 shadow-[0_8px_24px_rgba(16,24,40,0.06)]">
      <p className="text-xs font-medium uppercase tracking-wide text-[#98A2B3]">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums" style={{ color: positive ? "#039855" : "#344054" }}>
        {value}
      </p>
      <p className="text-xs text-[#667085]">{sub}</p>
    </div>
  )
}

const TH = ({ children, left }: { children: ReactNode; left?: boolean }) => (
  <th
    className={`whitespace-nowrap px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3] ${
      left ? "text-left" : "text-right"
    }`}
  >
    {children}
  </th>
)

export function PanelTable({ rows, loading }: { rows: PanelRow[]; loading: boolean }) {
  if (loading && !rows.length) {
    return (
      <div className="space-y-2 p-5">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-9 animate-pulse rounded-lg bg-[#F2F4F7]" aria-hidden="true" />
        ))}
      </div>
    )
  }

  if (!rows.length) {
    return (
      <div className="px-5 py-12 text-center text-sm text-[#667085]">
        Nenhum dado no snapshot. Dispare uma captura na aba Scraper.
      </div>
    )
  }

  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-[#EAECF0]">
          <TH left>#</TH>
          <TH left>Ativo</TH>
          <TH>Preço</TH>
          <TH>1D %</TH>
          <TH>Score</TH>
          <TH>Entrada</TH>
          <TH left>Setup</TH>
          <TH>Trades/m</TH>
          <TH>T/OI</TH>
          <TH>EXP 1D</TH>
          <TH>EXP 4H</TH>
          <TH>EXP 1H</TH>
          <TH>OI Trend</TH>
          <TH>LSR</TH>
          <TH>RSI 4H</TH>
          <TH>OI USD</TH>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const badge = setupBadgeStyle(r.setup)
          const scoreW = Math.max(4, Math.min(100, r.score ?? 0))
          return (
            <tr key={r.symbol} className="border-b border-[#F2F4F7] hover:bg-[#FCFCFD]">
              <td className="px-3 py-2.5 text-left text-sm font-semibold text-[#98A2B3] tabular-nums">
                {String(r.rank ?? "").padStart(2, "0")}
              </td>
              <td className="px-3 py-2.5 text-left">
                <Link href={`/analise/historico/${r.symbol}`} className="text-sm font-semibold text-[#344054] hover:text-[#6366f1]">
                  {r.asset}
                </Link>
              </td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums">{fmtPrice(r.price)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.change) }}>
                {fmtNum(r.change, 2, true)}%
              </td>
              <td className="px-3 py-2.5">
                <div className="flex items-center justify-end gap-2">
                  <span className="text-sm font-semibold text-[#344054] tabular-nums">{r.score ?? "—"}</span>
                  <span className="h-1.5 w-16 overflow-hidden rounded-full bg-[#F2F4F7]">
                    <span className="block h-full rounded-full" style={{ width: `${scoreW}%`, backgroundColor: "#6366f1" }} />
                  </span>
                </div>
              </td>
              <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: (r.entry_score ?? 0) >= 5 ? "#039855" : "#475467" }}>
                {r.entry_grade === "SETUP DE OURO" ? "★ " : ""}{r.entry_score ?? 0}/7
              </td>
              <td className="px-3 py-2.5 text-left">
                <span
                  className="inline-block whitespace-nowrap rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase"
                  style={{ backgroundColor: badge.bg, color: badge.color, borderColor: badge.border }}
                >
                  {r.setup ?? "—"}
                </span>
              </td>
              <td className="px-3 py-2.5 text-right text-sm text-[#667085] tabular-nums">
                {r.trades == null ? "—" : Math.round(r.trades)}
              </td>
              <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: colorToi(r.toi) }}>
                {fmtCompact(r.toi)}
              </td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.exp1d) }}>{fmtNum(r.exp1d, 2, true)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.exp4h) }}>{fmtNum(r.exp4h, 2, true)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.exp1h) }}>{fmtNum(r.exp1h, 2, true)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.oitrend) }}>{fmtNum(r.oitrend, 2, true)}</td>
              <td className="px-3 py-2.5 text-right text-sm text-[#667085] tabular-nums">{fmtNum(r.lsr, 3)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: "#DC6803" }}>{fmtNum(r.rsi4h, 2)}</td>
              <td className="px-3 py-2.5 text-right text-sm text-[#475467] tabular-nums">{fmtUsd(r.oiusd)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
