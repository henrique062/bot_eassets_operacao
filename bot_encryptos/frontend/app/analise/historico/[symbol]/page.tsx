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
  const realTarget = data?.real_target
  const paperModeEnabled = latestConfig?.paper_trading !== false
  const botRunning = Boolean(activeSessions?.length)
  const [busyMode, setBusyMode] = useState<"paper" | "real" | null>(null)

  async function toggleTarget(mode: "paper" | "real") {
    if (busyMode) return
    const active = mode === "paper" ? paperTarget?.active : realTarget?.active
    setBusyMode(mode)
    setTargetError(null)
    setTargetMsg(null)
    try {
      if (active) {
        await api.deactivateTradeTarget(mode, symbol)
        setTargetMsg(`Moeda desarmada (${mode}).`)
      } else {
        await api.activateTradeTarget(mode, symbol)
        setTargetMsg(
          mode === "paper"
            ? "Moeda armada no robô (paper). Ela será forçada na próxima janela."
            : "Moeda armada na CONTA REAL. Só opera quando o bot estiver em modo real."
        )
      }
      await mutate()
    } catch (err) {
      if (err instanceof ApiError && err.detail) setTargetError(err.detail)
      else setTargetError("Falha ao atualizar o alvo do robô.")
    } finally {
      setBusyMode(null)
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
        <div className="space-y-1.5">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-[#f3f4f6]">
            Armar moeda no robô
          </h3>
          <p className="text-sm text-[#9ca3af]">
            Armar <b className="text-[#f3f4f6]">força a entrada</b> nesta moeda assim que houver sinal mínimo
            (força relativa positiva), sem precisar do Setup de Ouro completo. O robô <b className="text-[#f3f4f6]">continua
            operando as outras moedas</b> normalmente, respeitando o limite de posições.
          </p>
          <p className="text-xs text-[#6b7280]">
            Bot: {botRunning ? "rodando" : "parado"} · Config atual: {paperModeEnabled ? "paper" : "real"} ·
            Cada conta tem sua lista de moedas armadas.
          </p>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {/* Paper */}
          <div className="flex items-center justify-between rounded-lg border border-[#2a2d3a] bg-[#15171f] px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white">Robô paper</span>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${paperTarget?.active ? "border-green-500/30 bg-green-500/10 text-green-300" : "border-[#2a2d3a] text-[#6b7280]"}`}>
                {paperTarget?.active ? "Armada" : "Inativa"}
              </span>
            </div>
            <button
              type="button"
              onClick={() => toggleTarget("paper")}
              disabled={busyMode !== null}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-60 ${paperTarget?.active ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-[#6366f1] bg-[#6366f1] text-white hover:bg-[#5855eb]"}`}
            >
              {busyMode === "paper" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : paperTarget?.active ? <ShieldOff className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              {paperTarget?.active ? "Desarmar" : "Armar paper"}
            </button>
          </div>

          {/* Real */}
          <div className="flex items-center justify-between rounded-lg border border-[#2a2d3a] bg-[#15171f] px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white">Conta real</span>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${realTarget?.active ? "border-amber-500/40 bg-amber-500/10 text-amber-300" : "border-[#2a2d3a] text-[#6b7280]"}`}>
                {realTarget?.active ? "Armada" : "Inativa"}
              </span>
            </div>
            <button
              type="button"
              onClick={() => toggleTarget("real")}
              disabled={busyMode !== null}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-60 ${realTarget?.active ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/15"}`}
            >
              {busyMode === "real" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : realTarget?.active ? <ShieldOff className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              {realTarget?.active ? "Desarmar" : "Armar real"}
            </button>
          </div>
        </div>

        {realTarget?.active && paperModeEnabled ? (
          <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-300">
            Armada na conta real, mas o bot está em modo paper. Ela só será operada quando você trocar o bot para real (aba Config).
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
