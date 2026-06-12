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
    <div className="flex flex-col gap-6">
      {error && (
        <div role="alert" className="rounded-2xl border border-[#FECDCA] bg-[#FEF3F2] px-6 py-4 text-sm text-[#B42318]">
          Erro ao carregar o Radar de Acumulação.
        </div>
      )}

      <div className="rounded-2xl border border-[#EAECF0] bg-white px-6 py-4 text-sm leading-relaxed text-[#667085] shadow-[0_8px_24px_rgba(16,24,40,0.06)]">
        <span className="font-semibold text-[#344054]">Como ler: </span>
        <span style={{ color: "#7F56D9" }} className="font-semibold">T/OI alto</span> = moeda com OI baixo recebendo
        trades demais → SM trabalhando o ativo de forma focada, algo sendo preparado.{" "}
        <span className="font-semibold text-[#344054]">Dias no topo</span> = em quantos snapshots recentes a moeda ficou
        entre as 30 maiores em T/OI. Persistência = acumulação em andamento.
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
            <div className="px-5 py-12 text-center text-sm text-[#667085]">Sem dados no snapshot atual.</div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#EAECF0]">
                  {["#", "Ativo", "T/OI", "OI USD", "Trades 1D", "Dias no topo", "Rank", "Score", "Setup", "1D %"].map((h, i) => (
                    <th
                      key={h}
                      className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3] ${i < 2 || i === 8 ? "text-left" : "text-right"}`}
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
                    <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: colorToi(r.toi) }}>
                      {fmtCompact(r.toi)}
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#475467] tabular-nums">{fmtUsd(r.oiusd)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#667085] tabular-nums">{fmtCompact(r.trades1d)}</td>
                    <td className="px-3 py-2.5 text-right">
                      {r.days_top > 1 ? (
                        <span className="rounded-md border border-[#D9D6FE] bg-[#F4F3FF] px-2 py-0.5 text-[10px] font-semibold text-[#5925DC]">
                          {r.days_top}/{r.total_snaps} dias
                        </span>
                      ) : (
                        <span className="text-sm text-[#98A2B3] tabular-nums">
                          {r.days_top}/{r.total_snaps}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#98A2B3] tabular-nums">{r.rank ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#344054] tabular-nums">{r.score ?? "—"}</td>
                    <td className="px-3 py-2.5 text-left text-sm text-[#667085]">{r.setup ?? "—"}</td>
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
