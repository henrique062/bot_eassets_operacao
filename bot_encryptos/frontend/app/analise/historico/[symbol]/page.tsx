"use client"

import { use, useMemo } from "react"
import Link from "next/link"
import useSWR from "swr"
import { ArrowLeft } from "lucide-react"
import { api } from "@/lib/api"
import type { HistoryPoint } from "@/lib/types"
import { fmtPrice, fmtNum, fmtUsd, fmtCompact, colorPN } from "@/lib/panel-format"

export default function HistoricoPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params)

  const { data, error, isLoading } = useSWR(
    symbol ? `panel-history-${symbol}` : null,
    () => api.getPanelHistory(symbol),
    { revalidateOnFocus: false }
  )

  const history = data?.history ?? []

  return (
    <div className="flex flex-col gap-6">
      <Link href="/analise" className="flex w-fit items-center gap-2 text-sm font-semibold text-[#6366f1] hover:underline">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Voltar ao painel
      </Link>

      <div className="flex items-baseline gap-3">
        <h2 className="text-xl font-semibold text-[#344054]">{data?.asset ?? symbol.replace("USDT", "")}</h2>
        <span className="text-sm text-[#667085]">{symbol.toUpperCase()} · {history.length} registros</span>
      </div>

      {error && (
        <div role="alert" className="rounded-2xl border border-[#FECDCA] bg-[#FEF3F2] px-6 py-4 text-sm text-[#B42318]">
          Sem histórico para esse símbolo ainda.
        </div>
      )}

      {history.length > 1 && (
        <div className="rounded-2xl border border-[#EAECF0] bg-white px-6 py-5 shadow-[0_8px_24px_rgba(16,24,40,0.06)]">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[#98A2B3]">Score (cronológico, 0-100)</p>
          <Sparkline points={history} />
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-[#EAECF0] bg-white shadow-[0_8px_24px_rgba(16,24,40,0.06)]">
        <div className="overflow-x-auto">
          {isLoading && !history.length ? (
            <div className="space-y-2 p-5">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-9 animate-pulse rounded-lg bg-[#F2F4F7]" aria-hidden="true" />
              ))}
            </div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#EAECF0]">
                  {["Data", "Rank", "Score", "Setup", "Preço", "1D %", "EXP 1D", "EXP 4H", "EXP 1H", "OI Trend", "RSI 4H", "OI USD"].map((h, i) => (
                    <th
                      key={h}
                      className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3] ${i === 0 || i === 3 ? "text-left" : "text-right"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.snapshot_id} className="border-b border-[#F2F4F7] hover:bg-[#FCFCFD]">
                    <td className="px-3 py-2.5 text-left">
                      <Link href={`/analise/snapshot/${h.snapshot_id}`} className="text-sm text-[#475467] hover:text-[#6366f1]">
                        {h.timestamp_brt}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#98A2B3] tabular-nums">{h.rank ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#344054] tabular-nums">{h.score ?? "—"}</td>
                    <td className="px-3 py-2.5 text-left text-sm text-[#667085]">{h.setup ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums">{fmtPrice(h.price)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.change) }}>{fmtNum(h.change, 2, true)}%</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.exp1d) }}>{fmtNum(h.exp1d, 2, true)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.exp4h) }}>{fmtNum(h.exp4h, 2, true)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.exp1h) }}>{fmtNum(h.exp1h, 2, true)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.oitrend) }}>{fmtNum(h.oitrend, 2, true)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: "#DC6803" }}>{fmtNum(h.rsi4h, 2)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#475467] tabular-nums">{fmtUsd(h.oiusd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function Sparkline({ points }: { points: HistoryPoint[] }) {
  const { poly, dots } = useMemo(() => {
    // série cronológica (antigo -> novo); o backend devolve do mais novo ao mais antigo
    const scores = [...points].reverse().map((p) => p.score).filter((s): s is number => s != null)
    const w = 800
    const h = 120
    if (scores.length < 2) return { poly: "", dots: [] as { x: number; y: number }[] }
    const dx = w / (scores.length - 1)
    const coords = scores.map((v, i) => ({ x: i * dx, y: h - (v / 100) * h }))
    return {
      poly: coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" "),
      dots: coords,
    }
  }, [points])

  if (!poly) return <p className="text-sm text-[#98A2B3]">Série insuficiente.</p>

  return (
    <svg viewBox="0 0 800 120" width="100%" height="120" preserveAspectRatio="none" role="img" aria-label="Evolução do score">
      <polyline points={poly} fill="none" stroke="#6366f1" strokeWidth={2} />
      {dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={2.5} fill="#6366f1" />
      ))}
    </svg>
  )
}
