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
import { AlphaBadge } from "@/components/ui/alpha-badge"

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
    <div className="flex flex-col gap-4">
      {error ? (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar o painel. Verifique se já existe algum snapshot capturado.
        </div>
      ) : null}

      <MacroBanner btc={data?.btc} />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch">
        <div className="grid flex-1 grid-cols-2 gap-4 sm:grid-cols-4">
          <KpiCard label="Top Score" value={kpis?.byScore?.asset ?? "—"} sub={`score ${kpis?.byScore?.score ?? "—"}`} valueIsAlpha={kpis?.byScore?.is_alpha} />
          <KpiCard label="Maior EXP 1D" value={fmtNum(kpis?.byExp1d?.exp1d, 2, true)} sub={kpis?.byExp1d?.asset ?? "—"} positive subIsAlpha={kpis?.byExp1d?.is_alpha} />
          <KpiCard label="Maior EXP 4H" value={fmtNum(kpis?.byExp4h?.exp4h, 2, true)} sub={kpis?.byExp4h?.asset ?? "—"} positive subIsAlpha={kpis?.byExp4h?.is_alpha} />
          <KpiCard label="Ativos" value={String(data?.meta?.symbols ?? rows.length)} sub={data?.meta?.exchange ?? "eassets"} />
        </div>
        {selector}
      </div>

      <div className="overflow-hidden rounded-xl border border-[#2a2d3a] bg-[#1a1d27]">
        <div className="overflow-x-auto">
          <PanelTable rows={visible} loading={Boolean(isLoading)} />
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-[#2a2d3a] bg-[#15171f] px-5 py-3">
          <span className="mr-auto text-xs text-[#6b7280]">
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
                  : { backgroundColor: "#1a1d27", borderColor: "#2a2d3a", color: "#9ca3af" }
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
  valueIsAlpha,
  subIsAlpha,
}: {
  label: string
  value: string
  sub: string
  positive?: boolean
  valueIsAlpha?: boolean
  subIsAlpha?: boolean
}) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[#6b7280]">{label}</p>
      <div className="mt-1 flex items-center gap-2">
        <p className="text-xl font-semibold tabular-nums" style={{ color: positive ? "#4ade80" : "#f3f4f6" }}>
          {value}
        </p>
        <AlphaBadge isAlpha={valueIsAlpha} />
      </div>
      <div className="flex items-center gap-2">
        <p className="text-xs text-[#6b7280]">{sub}</p>
        <AlphaBadge isAlpha={subIsAlpha} />
      </div>
    </div>
  )
}

const TH = ({ children, left }: { children: ReactNode; left?: boolean }) => (
  <th
    className={`whitespace-nowrap px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#6b7280] ${
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
          <div key={i} className="h-9 animate-pulse rounded-lg bg-[#2a2d3a]" aria-hidden="true" />
        ))}
      </div>
    )
  }

  if (!rows.length) {
    return (
      <div className="px-5 py-12 text-center text-sm text-[#6b7280]">
        Nenhum dado no snapshot. Dispare uma captura na aba Scraper.
      </div>
    )
  }

  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-[#2a2d3a]">
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
            <tr key={r.symbol} className="border-b border-[#23262f] hover:bg-[#20232d]">
              <td className="px-3 py-2.5 text-left text-sm font-semibold text-[#6b7280] tabular-nums">
                {String(r.rank ?? "").padStart(2, "0")}
              </td>
              <td className="px-3 py-2.5 text-left">
                <div className="flex items-center gap-2">
                  <Link href={`/analise/historico/${r.symbol}`} className="text-sm font-semibold text-[#f3f4f6] hover:text-[#818cf8]">
                    {r.asset}
                  </Link>
                  <AlphaBadge isAlpha={r.is_alpha} />
                </div>
              </td>
              <td className="px-3 py-2.5 text-right text-sm text-[#d1d5db] tabular-nums">{fmtPrice(r.price)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.change) }}>
                {fmtNum(r.change, 2, true)}%
              </td>
              <td className="px-3 py-2.5">
                <div className="flex items-center justify-end gap-2">
                  <span className="text-sm font-semibold text-[#f3f4f6] tabular-nums">{r.score ?? "—"}</span>
                  <span className="h-1.5 w-16 overflow-hidden rounded-full bg-[#2a2d3a]">
                    <span className="block h-full rounded-full" style={{ width: `${scoreW}%`, backgroundColor: "#6366f1" }} />
                  </span>
                </div>
              </td>
              <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: (r.entry_score ?? 0) >= 5 ? "#4ade80" : "#9ca3af" }}>
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
              <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">
                {r.trades == null ? "—" : Math.round(r.trades)}
              </td>
              <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: colorToi(r.toi) }}>
                {fmtCompact(r.toi)}
              </td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.exp1d) }}>{fmtNum(r.exp1d, 2, true)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.exp4h) }}>{fmtNum(r.exp4h, 2, true)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.exp1h) }}>{fmtNum(r.exp1h, 2, true)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.oitrend) }}>{fmtNum(r.oitrend, 2, true)}</td>
              <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtNum(r.lsr, 3)}</td>
              <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: "#fbbf24" }}>{fmtNum(r.rsi4h, 2)}</td>
              <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtUsd(r.oiusd)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
