"use client"

import useSWR from "swr"
import Link from "next/link"
import { api } from "@/lib/api"
import { fmtNum, fmtUsd, fmtCompact, colorPN, colorToi } from "@/lib/panel-format"

export default function RadarPage() {
  const { data, error, isLoading } = useSWR("panel-radar", () => api.getPanelRadar(), {
    refreshInterval: 60_000,
    revalidateOnFocus: false,
  })

  const rows = data?.rows ?? []

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          Erro ao carregar o Radar de Acumulação.
        </div>
      )}

      <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-6 py-4 text-sm leading-relaxed text-[#9ca3af]">
        <span className="font-semibold text-[#f3f4f6]">Como ler: </span>
        <span style={{ color: "#c084fc" }} className="font-semibold">T/OI alto</span> = moeda com OI baixo recebendo
        trades demais → SM trabalhando o ativo de forma focada, algo sendo preparado.{" "}
        <span className="font-semibold text-[#f3f4f6]">Dias no topo</span> = em quantos snapshots recentes a moeda ficou
        entre as 30 maiores em T/OI. Persistência = acumulação em andamento.
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
            <div className="px-5 py-12 text-center text-sm text-[#6b7280]">Sem dados no snapshot atual.</div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#2a2d3a]">
                  {["#", "Ativo", "T/OI", "OI USD", "Trades 1D", "Dias no topo", "Rank", "Score", "Setup", "1D %"].map((h, i) => (
                    <th
                      key={h}
                      className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#6b7280] ${i < 2 || i === 8 ? "text-left" : "text-right"}`}
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
                      <Link href={`/analise/historico/${r.symbol}`} className="text-sm font-semibold text-[#f3f4f6] hover:text-[#818cf8]">
                        {r.asset}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: colorToi(r.toi) }}>
                      {fmtCompact(r.toi)}
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtUsd(r.oiusd)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtCompact(r.trades1d)}</td>
                    <td className="px-3 py-2.5 text-right">
                      {r.days_top > 1 ? (
                        <span className="rounded-md border border-[#a78bfa]/40 bg-[#a78bfa]/10 px-2 py-0.5 text-[10px] font-semibold text-[#c084fc]">
                          {r.days_top}/{r.total_snaps} dias
                        </span>
                      ) : (
                        <span className="text-sm text-[#6b7280] tabular-nums">
                          {r.days_top}/{r.total_snaps}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#6b7280] tabular-nums">{r.rank ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#f3f4f6] tabular-nums">{r.score ?? "—"}</td>
                    <td className="px-3 py-2.5 text-left text-sm text-[#9ca3af]">{r.setup ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.change) }}>
                      {fmtNum(r.change, 2, true)}%
                    </td>
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
