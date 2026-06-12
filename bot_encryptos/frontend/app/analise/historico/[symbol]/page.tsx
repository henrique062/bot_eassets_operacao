"use client"

import { use } from "react"
import Link from "next/link"
import useSWR from "swr"
import { ArrowLeft } from "lucide-react"
import { api } from "@/lib/api"
import type { HistoryPoint } from "@/lib/types"
import { fmtPrice, fmtNum, fmtUsd, colorPN } from "@/lib/panel-format"
import { ScoreChart } from "@/components/panel/score-chart"
import { AlphaBadge } from "@/components/ui/alpha-badge"

export default function HistoricoPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params)

  const { data, error, isLoading } = useSWR(
    symbol ? `panel-history-${symbol}` : null,
    () => api.getPanelHistory(symbol),
    { revalidateOnFocus: false }
  )

  const history = data?.history ?? []
  // série cronológica (antigo -> novo); o backend devolve do mais novo ao mais antigo
  const chrono = [...history].reverse()

  return (
    <div className="flex flex-col gap-4">
      <Link href="/analise" className="flex w-fit items-center gap-2 text-sm font-semibold text-[#818cf8] hover:underline">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Voltar ao painel
      </Link>

      <div className="flex items-baseline gap-3">
        <h2 className="text-xl font-semibold text-[#f3f4f6]">{data?.asset ?? symbol.replace("USDT", "")}</h2>
        <AlphaBadge isAlpha={data?.is_alpha} />
        <span className="text-sm text-[#6b7280]">{symbol.toUpperCase()} · {history.length} registros</span>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          Sem histórico para esse símbolo ainda.
        </div>
      )}

      {chrono.length > 1 && (
        <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-5 py-5">
          <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-[#6b7280]">Score ao longo do tempo (0-100)</p>
          <ScoreChart points={chrono} />
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-[#2a2d3a] bg-[#1a1d27]">
        <div className="overflow-x-auto">
          {isLoading && !history.length ? (
            <div className="space-y-2 p-5">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-9 animate-pulse rounded-lg bg-[#2a2d3a]" aria-hidden="true" />
              ))}
            </div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#2a2d3a]">
                  {["Data", "Rank", "Score", "Setup", "Preço", "1D %", "EXP 1D", "EXP 4H", "EXP 1H", "OI Trend", "RSI 4H", "OI USD"].map((h, i) => (
                    <th
                      key={h}
                      className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#6b7280] ${i === 0 || i === 3 ? "text-left" : "text-right"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.snapshot_id} className="border-b border-[#23262f] hover:bg-[#20232d]">
                    <td className="px-3 py-2.5 text-left">
                      <Link href={`/analise/snapshot/${h.snapshot_id}`} className="text-sm text-[#9ca3af] hover:text-[#818cf8]">
                        {h.timestamp_brt}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#6b7280] tabular-nums">{h.rank ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#f3f4f6] tabular-nums">{h.score ?? "—"}</td>
                    <td className="px-3 py-2.5 text-left text-sm text-[#9ca3af]">{h.setup ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#d1d5db] tabular-nums">{fmtPrice(h.price)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.change) }}>{fmtNum(h.change, 2, true)}%</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.exp1d) }}>{fmtNum(h.exp1d, 2, true)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.exp4h) }}>{fmtNum(h.exp4h, 2, true)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.exp1h) }}>{fmtNum(h.exp1h, 2, true)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(h.oitrend) }}>{fmtNum(h.oitrend, 2, true)}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: "#fbbf24" }}>{fmtNum(h.rsi4h, 2)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtUsd(h.oiusd)}</td>
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

export type { HistoryPoint }
