"use client"

import useSWR from "swr"
import Link from "next/link"
import { Check } from "lucide-react"
import { api } from "@/lib/api"
import type { SetupChecklist } from "@/lib/types"
import { fmtNum, colorPN } from "@/lib/panel-format"
import { MacroBanner } from "@/components/panel/macro-banner"

const CRITERIA: { key: keyof SetupChecklist; label: string }[] = [
  { key: "exp_pos", label: "EXP" },
  { key: "tpm_hot", label: "TPM" },
  { key: "lsr_fuel", label: "LSR" },
  { key: "oi_in", label: "OI" },
  { key: "rsi_runway", label: "RSI" },
  { key: "accumulation", label: "ACUM" },
  { key: "funding_neg", label: "FUND" },
]

export default function SetupPage() {
  const { data, error, isLoading } = useSWR("panel-setup", () => api.getPanelSetup(), {
    refreshInterval: 60_000,
    revalidateOnFocus: false,
  })

  const rows = data?.rows ?? []

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <div role="alert" className="rounded-2xl border border-[#FECDCA] bg-[#FEF3F2] px-6 py-4 text-sm text-[#B42318]">
          Erro ao carregar o Setup de Ouro.
        </div>
      )}

      <MacroBanner btc={data?.btc} />

      <div className="rounded-2xl border border-[#EAECF0] bg-white px-6 py-4 text-sm leading-relaxed text-[#667085] shadow-[0_8px_24px_rgba(16,24,40,0.06)]">
        <span className="font-semibold text-[#344054]">Critérios (★ = núcleo): </span>
        <b className="text-[#039855]">EXP★</b> força vs BTC verde em 5m/15m/1h ·{" "}
        <b className="text-[#039855]">TPM★</b> trades acelerando (≥800 ou salto) ·{" "}
        <b className="text-[#039855]">LSR</b> &lt;1 ou caindo · <b className="text-[#039855]">OI</b> subindo ·{" "}
        <b className="text-[#039855]">RSI</b> quente sem exaustão · <b className="text-[#039855]">ACUM</b> range comprimido ·{" "}
        <b className="text-[#039855]">FUND</b> funding negativo. Setup de Ouro = BTC em janela + EXP + TPM + ≥5/7.
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
                  <th className="px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3]">#</th>
                  <th className="px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3]">Ativo</th>
                  <th className="px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3]">Grau</th>
                  <th className="px-3 py-3 text-right text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3]">✓/7</th>
                  {CRITERIA.map((c) => (
                    <th key={c.key} className="px-2 py-3 text-center text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3]">
                      {c.label}
                    </th>
                  ))}
                  <th className="px-3 py-3 text-right text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3]">Score</th>
                  <th className="px-3 py-3 text-right text-[10px] font-semibold uppercase tracking-wide text-[#98A2B3]">1D %</th>
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
                      {r.trap && (
                        <span className="ml-2 rounded-md border border-[#FECDCA] bg-[#FEF3F2] px-1.5 py-0.5 text-[9px] font-semibold uppercase text-[#B42318]">
                          Armadilha
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-left">
                      {r.setup_grade ? (
                        <span
                          className="rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase"
                          style={
                            r.setup_grade === "SETUP DE OURO"
                              ? { backgroundColor: "#ECFDF3", color: "#027A48", borderColor: "#A6F4C5" }
                              : { backgroundColor: "#FFFAEB", color: "#B54708", borderColor: "#FEDF89" }
                          }
                        >
                          {r.setup_grade}
                        </span>
                      ) : (
                        <span className="text-sm text-[#98A2B3]">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#344054] tabular-nums">{r.setup_score}/7</td>
                    {CRITERIA.map((c) => (
                      <td key={c.key} className="px-2 py-2.5 text-center">
                        {r.checklist[c.key] ? (
                          <Check className="mx-auto h-4 w-4" style={{ color: "#039855" }} aria-label="atende" />
                        ) : (
                          <span className="text-[#D0D5DD]" aria-label="não atende">·</span>
                        )}
                      </td>
                    ))}
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#344054] tabular-nums">{r.score ?? "—"}</td>
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
