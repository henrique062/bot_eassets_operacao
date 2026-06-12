"use client"

import useSWR from "swr"
import Link from "next/link"
import { api } from "@/lib/api"
import { fmtNum } from "@/lib/panel-format"

export default function TopoPage() {
  const { data, error, isLoading } = useSWR("panel-topo", api.getPanelTopo, {
    revalidateOnFocus: false,
  })

  const rows = data ?? []

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <div role="alert" className="rounded-2xl border border-[#FECDCA] bg-[#FEF3F2] px-6 py-4 text-sm text-[#B42318]">
          Erro ao carregar o Topo Recorrente.
        </div>
      )}

      <div className="rounded-2xl border border-[#EAECF0] bg-white px-6 py-4 text-sm leading-relaxed text-[#667085] shadow-[0_8px_24px_rgba(16,24,40,0.06)]">
        <span className="font-semibold text-[#344054]">Topo Recorrente: </span>
        moedas que mais apareceram no TOP 10 nos últimos snapshots. Recorrência indica força estrutural persistente
        (não foi pico isolado de um único scan).
      </div>

      <div className="overflow-hidden rounded-2xl border border-[#EAECF0] bg-white shadow-[0_8px_24px_rgba(16,24,40,0.06)]">
        <div className="overflow-x-auto">
          {isLoading && !rows.length ? (
            <div className="space-y-2 p-5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-9 animate-pulse rounded-lg bg-[#F2F4F7]" aria-hidden="true" />
              ))}
            </div>
          ) : !rows.length ? (
            <div className="px-5 py-12 text-center text-sm text-[#667085]">
              Sem histórico suficiente ainda. Capture mais snapshots ao longo dos dias.
            </div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#EAECF0]">
                  {["#", "Ativo", "Aparições TOP 10", "Melhor rank", "Rank médio", "Score máx", "Score médio"].map((h, i) => (
                    <th
                      key={h}
                      className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3] ${i < 2 ? "text-left" : "text-right"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.symbol} className="border-b border-[#F2F4F7] hover:bg-[#FCFCFD]">
                    <td className="px-3 py-2.5 text-left text-sm text-[#98A2B3] tabular-nums">{i + 1}</td>
                    <td className="px-3 py-2.5 text-left">
                      <Link href={`/analise/historico/${r.symbol}`} className="text-sm font-semibold text-[#344054] hover:text-[#6366f1]">
                        {r.asset}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#344054] tabular-nums">{r.appearances}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#475467] tabular-nums">{r.best_rank ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#475467] tabular-nums">{fmtNum(r.avg_rank, 1)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#475467] tabular-nums">{r.max_score ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#475467] tabular-nums">{fmtNum(r.avg_score, 1)}</td>
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
