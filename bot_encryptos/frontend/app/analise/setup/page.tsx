"use client"

import useSWR from "swr"
import Link from "next/link"
import { Check } from "lucide-react"
import { api } from "@/lib/api"
import type { SetupChecklist } from "@/lib/types"
import { fmtNum, colorPN } from "@/lib/panel-format"
import { MacroBanner } from "@/components/panel/macro-banner"
import { AlphaBadge } from "@/components/ui/alpha-badge"

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
    <div className="flex flex-col gap-4">
      {error && (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          Erro ao carregar o Setup de Ouro.
        </div>
      )}

      <MacroBanner btc={data?.btc} />

      <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-6 py-4 text-sm leading-relaxed text-[#9ca3af]">
        <span className="font-semibold text-[#f3f4f6]">Critérios (★ = núcleo): </span>
        <b className="text-[#4ade80]">EXP★</b> força vs BTC verde em 5m/15m/1h ·{" "}
        <b className="text-[#4ade80]">TPM★</b> trades acelerando (≥800 ou salto) ·{" "}
        <b className="text-[#4ade80]">LSR</b> &lt;1 ou caindo · <b className="text-[#4ade80]">OI</b> subindo ·{" "}
        <b className="text-[#4ade80]">RSI</b> quente sem exaustão · <b className="text-[#4ade80]">ACUM</b> range comprimido ·{" "}
        <b className="text-[#4ade80]">FUND</b> funding negativo. Setup de Ouro = BTC em janela + EXP + TPM + ≥5/7.
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
                  <th className="px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">#</th>
                  <th className="px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">Ativo</th>
                  <th className="px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">Grau</th>
                  <th className="px-3 py-3 text-right text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">✓/7</th>
                  {CRITERIA.map((c) => (
                    <th key={c.key} className="px-2 py-3 text-center text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">
                      {c.label}
                    </th>
                  ))}
                  <th className="px-3 py-3 text-right text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">Score</th>
                  <th className="px-3 py-3 text-right text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">1D %</th>
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
                      {r.trap && (
                        <span className="ml-2 rounded-md border border-red-500/40 bg-red-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-red-400">
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
                              ? { backgroundColor: "rgba(52,211,153,0.12)", color: "#4ade80", borderColor: "rgba(52,211,153,0.4)" }
                              : { backgroundColor: "rgba(251,191,36,0.12)", color: "#fbbf24", borderColor: "rgba(251,191,36,0.4)" }
                          }
                        >
                          {r.setup_grade}
                        </span>
                      ) : (
                        <span className="text-sm text-[#6b7280]">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#f3f4f6] tabular-nums">{r.setup_score}/7</td>
                    {CRITERIA.map((c) => (
                      <td key={c.key} className="px-2 py-2.5 text-center">
                        {r.checklist[c.key] ? (
                          <Check className="mx-auto h-4 w-4" style={{ color: "#4ade80" }} aria-label="atende" />
                        ) : (
                          <span className="text-[#3a3d4a]" aria-label="não atende">·</span>
                        )}
                      </td>
                    ))}
                    <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#f3f4f6] tabular-nums">{r.score ?? "—"}</td>
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
