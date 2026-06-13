"use client"

import { use, useState } from "react"
import Link from "next/link"
import useSWR from "swr"
import { ArrowLeft, Loader2, ShieldCheck, ShieldOff } from "lucide-react"
import { api, ApiError } from "@/lib/api"
import type { HistoryPoint } from "@/lib/types"
import { fmtPrice, fmtNum, fmtUsd, colorPN } from "@/lib/panel-format"
import { ScoreChart } from "@/components/panel/score-chart"
import { AlphaBadge } from "@/components/ui/alpha-badge"

export default function HistoricoPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params)
  const [targetBusy, setTargetBusy] = useState(false)
  const [targetMsg, setTargetMsg] = useState<string | null>(null)
  const [targetError, setTargetError] = useState<string | null>(null)

  const { data, error, isLoading, mutate } = useSWR(
    symbol ? `panel-history-${symbol}` : null,
    () => api.getPanelHistory(symbol),
    { revalidateOnFocus: false }
  )
  const { data: latestConfig } = useSWR("latest-bot-config", api.getLatestConfig, {
    revalidateOnFocus: false,
  })
  const { data: activeSessions } = useSWR("active-bot-sessions", api.listActiveSessions, {
    revalidateOnFocus: false,
  })

  const history = data?.history ?? []
  // serie cronologica (antigo -> novo); o backend devolve do mais novo ao mais antigo
  const chrono = [...history].reverse()
  const paperTarget = data?.paper_target
  const paperModeEnabled = latestConfig?.paper_trading !== false
  const botRunning = Boolean(activeSessions?.length)

  async function handleTradeTargetToggle() {
    if (targetBusy) return
    if (!paperTarget?.active && !paperModeEnabled) {
      setTargetError("Coloque o bot em modo paper na aba Config antes de ativar um alvo manual.")
      setTargetMsg(null)
      return
    }

    setTargetBusy(true)
    setTargetError(null)
    setTargetMsg(null)
    try {
      if (paperTarget?.active) {
        await api.deactivatePaperTradeTarget(symbol)
        setTargetMsg("Moeda removida do robo manual em paper.")
      } else {
        await api.activatePaperTradeTarget(symbol)
        setTargetMsg("Moeda ativada no robo manual em paper.")
      }
      await mutate()
    } catch (err) {
      if (err instanceof ApiError && err.detail) {
        setTargetError(err.detail)
      } else {
        setTargetError("Falha ao atualizar o alvo manual do robo.")
      }
    } finally {
      setTargetBusy(false)
    }
  }

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
          Sem historico para esse simbolo ainda.
        </div>
      )}

      <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-5 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-[#f3f4f6]">
                Robo de recompra automatica
              </h3>
              <span
                className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                  paperTarget?.active
                    ? "border-green-500/30 bg-green-500/10 text-green-300"
                    : "border-[#2a2d3a] bg-[#15171f] text-[#9ca3af]"
                }`}
              >
                {paperTarget?.active ? "Paper ativo" : "Paper inativo"}
              </span>
            </div>
            <p className="text-sm text-[#9ca3af]">
              Ative esta moeda como alvo manual. Enquanto existir alvo manual paper ativo, o motor considera apenas essas moedas.
            </p>
            <p className="text-xs text-[#6b7280]">
              Bot: {botRunning ? "rodando" : "parado"} · Configuracao: {paperModeEnabled ? "paper" : "real"}
            </p>
          </div>

          <button
            type="button"
            onClick={handleTradeTargetToggle}
            disabled={targetBusy}
            className={`inline-flex items-center justify-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition-colors ${
              paperTarget?.active
                ? "border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/15"
                : "border-[#6366f1] bg-[#6366f1] text-white hover:bg-[#5855eb]"
            } disabled:cursor-not-allowed disabled:opacity-60`}
          >
            {targetBusy ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : paperTarget?.active ? (
              <ShieldOff className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            )}
            {paperTarget?.active ? "Desativar no robo paper" : "Ativar no robo paper"}
          </button>
        </div>

        {!paperModeEnabled && !paperTarget?.active ? (
          <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-300">
            O modo real esta bloqueando novas ativacoes manuais. Troque para paper na aba Config.
          </div>
        ) : null}

        {targetMsg ? <p className="mt-3 text-xs text-green-300">{targetMsg}</p> : null}
        {targetError ? <p className="mt-3 text-xs text-red-400">{targetError}</p> : null}
      </div>

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
                  {["Data", "Rank", "Score", "Setup", "Preco", "1D %", "EXP 1D", "EXP 4H", "EXP 1H", "OI Trend", "RSI 4H", "OI USD"].map((h, i) => (
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
