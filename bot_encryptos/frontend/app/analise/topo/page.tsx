"use client"

import useSWR from "swr"
import Link from "next/link"
import { api } from "@/lib/api"
import { fmtNum } from "@/lib/panel-format"
import { AlphaBadge } from "@/components/ui/alpha-badge"

export default function TopoPage() {
  const { data, error, isLoading } = useSWR("panel-topo", api.getPanelTopo, {
    revalidateOnFocus: false,
  })

  const rows = data ?? []

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          Erro ao carregar o Topo Recorrente.
        </div>
      )}

      <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-6 py-4 text-sm leading-relaxed text-[#9ca3af]">
        <span className="font-semibold text-[#f3f4f6]">Topo Recorrente: </span>
        moedas que mais apareceram no TOP 10 nos últimos snapshots. Recorrência indica força estrutural persistente
        (não foi pico isolado de um único scan).
      </div>

      <div className="overflow-hidden rounded-xl border border-[#2a2d3a] bg-[#1a1d27]">
        <div className="overflow-x-auto">
          {isLoading && !rows.length ? (
            <div className="space-y-2 p-5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-9 animate-pulse rounded-lg bg-[#2a2d3a]" aria-hidden="true" />
              ))}
            </div>
          ) : !rows.length ? (
            <div className="px-5 py-12 text-center text-sm text-[#6b7280]">
              Sem histórico suficiente ainda. Capture mais snapshots ao longo dos dias.
            </div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#2a2d3a]">
                  {["#", "Ativo", "Aparições TOP 10", "Melhor rank", "Rank médio", "Score máx", "Score médio"].map((h, i) => (
                    <th
                      key={h}
                      className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#6b7280] ${i < 2 ? "text-left" : "text-right"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.symbol} className="border-b border-[#23262f] hover:bg-[#20232d]">
                    <td className="px-3 py-2.5 text-left text-sm text-[#6b7280] tabular-nums">{i + 1}</td>
                    <td className="px-3 py-2.5 text-left">
                      <div className="flex items-center gap-2">
                        <Link href={`/analise/historico/${r.symbol}`} className="text-sm font-semibold text-[#f3f4f6] hover:text-[#818cf8]">
                          {r.asset}
                        </Link>
                        <AlphaBadge isAlpha={r.is_alpha} />
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#f3f4f6] tabular-nums">{r.appearances}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{r.best_rank ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtNum(r.avg_rank, 1)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{r.max_score ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtNum(r.avg_score, 1)}</td>
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
