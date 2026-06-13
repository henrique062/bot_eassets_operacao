"use client"

import { useState } from "react"
import Link from "next/link"
import { Loader2, X, Plus, TrendingUp, TrendingDown, Target } from "lucide-react"
import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api"
import type { MonitoredCoin, FundingFlip } from "@/lib/types"
import { fmtPrice, fmtNum, colorPN } from "@/lib/panel-format"

export default function MonitoracaoPage() {
  const { data, error, mutate } = usePolling("monitored", api.getMonitored, 30000)
  const [symbolInput, setSymbolInput] = useState("")
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)

  const rows = data ?? []

  async function handleAdd() {
    const sym = symbolInput.trim().toUpperCase()
    if (!sym) return
    setAdding(true)
    try {
      await api.monitorSymbol(sym.endsWith("USDT") ? sym : `${sym}USDT`)
      setSymbolInput("")
      mutate()
    } catch {
    } finally {
      setAdding(false)
    }
  }

  async function handleRemove(symbol: string) {
    setRemoving(symbol)
    try {
      await api.unmonitorSymbol(symbol)
      mutate()
    } catch {
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          Erro ao carregar a monitoração.
        </div>
      )}

      <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-5 py-4 text-sm leading-relaxed text-[#9ca3af]">
        <span className="font-semibold text-[#f3f4f6]">Monitoração: </span>
        marque qualquer moeda (aqui ou pelo botão <Target className="inline h-3.5 w-3.5" /> no Painel) para acompanhar.
        A tabela mostra a variação de preço desde o momento da marcação, as métricas atuais e a virada do funding.
      </div>

      {/* Adicionar manualmente */}
      <div className="flex items-center gap-2">
        <input
          value={symbolInput}
          onChange={(e) => setSymbolInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="Ex: SOL ou SOLUSDT"
          className="h-10 w-56 rounded-lg border border-[#2a2d3a] bg-[#15171f] px-3 text-sm text-[#d1d5db] outline-none focus:border-[#6366f1]"
        />
        <button
          type="button"
          onClick={handleAdd}
          disabled={adding}
          className="flex h-10 items-center gap-2 rounded-lg bg-[#6366f1] px-4 text-sm font-semibold text-white hover:bg-[#5457e5] disabled:opacity-60"
        >
          {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Monitorar
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-[#2a2d3a] bg-[#1a1d27]">
        <div className="overflow-x-auto">
          {!data ? (
            <div className="space-y-2 p-5">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-9 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <p className="p-8 text-center text-sm text-[#6b7280]">
              Nenhuma moeda monitorada. Adicione acima ou marque pelo Painel de Moedas.
            </p>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#2a2d3a]">
                  {["Ativo", "Marcada em", "Preço marcado", "Preço atual", "Variação", "Var %", "Score", "Setup", "Funding (virada)", ""].map((h, i) => (
                    <th key={h} className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#6b7280] ${i === 0 || i === 1 || i === 7 || i === 8 ? "text-left" : "text-right"}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <MonitoredRow key={r.id} r={r} onRemove={handleRemove} removing={removing === r.symbol} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function MonitoredRow({ r, onRemove, removing }: { r: MonitoredCoin; onRemove: (s: string) => void; removing: boolean }) {
  return (
    <tr className="border-b border-[#23262f] hover:bg-[#20232d]">
      <td className="px-3 py-2.5 text-left">
        <Link href={`/analise/historico/${r.symbol}`} className="text-sm font-semibold text-[#f3f4f6] hover:text-[#818cf8]">
          {r.asset}
        </Link>
        {r.cur_rank != null && <span className="ml-2 text-xs text-[#6b7280]">#{r.cur_rank}</span>}
      </td>
      <td className="px-3 py-2.5 text-left text-xs text-[#9ca3af]">{r.marked_at_brt ?? "—"}</td>
      <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtPrice(r.mark_price)}</td>
      <td className="px-3 py-2.5 text-right text-sm text-[#d1d5db] tabular-nums">{fmtPrice(r.cur_price)}</td>
      <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(r.delta_abs) }}>
        {r.delta_abs == null ? "—" : fmtPrice(r.delta_abs)}
      </td>
      <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: colorPN(r.delta_pct) }}>
        {fmtNum(r.delta_pct, 2, true)}%
      </td>
      <td className="px-3 py-2.5 text-right text-sm font-semibold text-[#f3f4f6] tabular-nums">{r.cur_score ?? "—"}</td>
      <td className="px-3 py-2.5 text-left text-sm text-[#9ca3af]">{r.cur_setup ?? "—"}</td>
      <td className="px-3 py-2.5 text-left"><FundingCell f={r.funding} /></td>
      <td className="px-3 py-2.5 text-right">
        <button
          type="button"
          onClick={() => onRemove(r.symbol)}
          disabled={removing}
          aria-label={`Parar de monitorar ${r.symbol}`}
          className="text-[#6b7280] hover:text-red-400"
        >
          {removing ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
        </button>
      </td>
    </tr>
  )
}

function FundingCell({ f }: { f: FundingFlip }) {
  if (f.current_fr == null) return <span className="text-sm text-[#6b7280]">—</span>
  const negative = f.current_sign === "neg"
  const frColor = negative ? "#4ade80" : f.current_sign === "pos" ? "#f87171" : "#9ca3af"
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm font-semibold tabular-nums" style={{ color: frColor }}>
        {fmtNum(f.current_fr * 100, 4, true)}%
      </span>
      {f.flipped && f.snapshots_since_flip != null && (
        <span
          className="flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold"
          style={
            f.direction === "to_negative"
              ? { backgroundColor: "rgba(52,211,153,0.12)", color: "#4ade80", borderColor: "rgba(52,211,153,0.35)" }
              : { backgroundColor: "rgba(248,113,113,0.12)", color: "#f87171", borderColor: "rgba(248,113,113,0.35)" }
          }
          title={f.direction === "to_negative" ? "Virou negativo (munição p/ alta)" : "Virou positivo"}
        >
          {f.direction === "to_negative" ? <TrendingDown className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
          virou há {f.snapshots_since_flip} snaps
        </span>
      )}
    </div>
  )
}
