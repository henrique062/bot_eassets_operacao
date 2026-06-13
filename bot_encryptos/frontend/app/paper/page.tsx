"use client"

import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api"
import type { BotOpenPosition, BotClosedTrade } from "@/lib/types"
import { fmtPrice, fmtNum, colorPN } from "@/lib/panel-format"

export default function PaperPage() {
  const { data, error } = usePolling("paper-results", () => api.getBotResults("paper"), 5000)
  const s = data?.summary
  const open = data?.open_positions ?? []
  const closed = data?.closed_trades ?? []

  return (
    <div className="space-y-4">
      {error && (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          Erro ao carregar os resultados do paper.
        </div>
      )}

      <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-5 py-4 text-sm leading-relaxed text-[#9ca3af]">
        <span className="font-semibold text-[#f3f4f6]">Resultados Paper (simulado): </span>
        operações que o robô abriu em modo de teste. O P&L não realizado usa o preço ao vivo da Bybit
        (onde o robô real executaria), atualizando a cada 5s.
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Kpi label="Posições abertas" value={String(s?.open_count ?? "—")} />
        <Kpi label="P&L não realizado" value={s ? `$${fmtNum(s.unrealised_pnl, 2, true)}` : "—"} color={colorPN(s?.unrealised_pnl ?? null)} />
        <Kpi label="P&L realizado" value={s ? `$${fmtNum(s.realised_pnl, 2, true)}` : "—"} color={colorPN(s?.realised_pnl ?? null)} />
        <Kpi label="Taxa de acerto" value={s?.win_rate != null ? `${fmtNum(s.win_rate, 0)}%` : "—"} sub={`${s?.closed_count ?? 0} fechados`} />
      </div>

      {/* Abertas */}
      <div className="overflow-hidden rounded-xl border border-[#2a2d3a] bg-[#1a1d27]">
        <div className="border-b border-[#2a2d3a] px-5 py-3 text-sm font-semibold text-[#f3f4f6]">Posições abertas</div>
        <div className="overflow-x-auto">
          {!data ? (
            <Skeleton />
          ) : open.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-[#6b7280]">
              Nenhuma posição paper aberta. O robô abre quando uma moeda bate o setup (ou quando você arma uma moeda).
            </p>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#2a2d3a]">
                  {["Ativo", "Lado", "Qtd", "Entrada", "Atual", "P&L $", "P&L %", "Stop", "Alvo", "Aberta em"].map((h, i) => (
                    <th key={h} className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#6b7280] ${i === 0 || i === 1 ? "text-left" : "text-right"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {open.map((p: BotOpenPosition) => (
                  <tr key={p.symbol} className="border-b border-[#23262f] hover:bg-[#20232d]">
                    <td className="px-3 py-2.5 text-left text-sm font-semibold text-[#f3f4f6]">{p.asset}</td>
                    <td className="px-3 py-2.5 text-left text-sm text-[#9ca3af]">{p.side}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{fmtNum(p.qty, 4)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#d1d5db] tabular-nums">{fmtPrice(p.entry_price)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#d1d5db] tabular-nums">{fmtPrice(p.cur_price)}</td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: colorPN(p.pnl_usd) }}>{p.pnl_usd == null ? "—" : `$${fmtNum(p.pnl_usd, 2, true)}`}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(p.pnl_pct) }}>{fmtNum(p.pnl_pct, 2, true)}%</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#6b7280] tabular-nums">{fmtPrice(p.stop_loss)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#6b7280] tabular-nums">{p.take_profit ? fmtPrice(p.take_profit) : "—"}</td>
                    <td className="px-3 py-2.5 text-right text-xs text-[#6b7280]">{p.opened_at_brt ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Fechadas */}
      <div className="overflow-hidden rounded-xl border border-[#2a2d3a] bg-[#1a1d27]">
        <div className="border-b border-[#2a2d3a] px-5 py-3 text-sm font-semibold text-[#f3f4f6]">Operações fechadas</div>
        <div className="overflow-x-auto">
          {!data ? (
            <Skeleton />
          ) : closed.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-[#6b7280]">Nenhuma operação paper fechada ainda.</p>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[#2a2d3a]">
                  {["Ativo", "Lado", "Entrada", "Saída", "P&L $", "P&L %", "Motivo", "Fechada em"].map((h, i) => (
                    <th key={h} className={`px-3 py-3 text-[10px] font-semibold uppercase tracking-wide text-[#6b7280] ${i === 0 || i === 1 || i === 6 ? "text-left" : "text-right"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {closed.map((t: BotClosedTrade, i: number) => (
                  <tr key={`${t.symbol}-${i}`} className="border-b border-[#23262f] hover:bg-[#20232d]">
                    <td className="px-3 py-2.5 text-left text-sm font-semibold text-[#f3f4f6]">{t.asset}</td>
                    <td className="px-3 py-2.5 text-left text-sm text-[#9ca3af]">{t.side}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#d1d5db] tabular-nums">{fmtPrice(t.entry_price)}</td>
                    <td className="px-3 py-2.5 text-right text-sm text-[#d1d5db] tabular-nums">{fmtPrice(t.close_price)}</td>
                    <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums" style={{ color: colorPN(t.pnl_usd) }}>{t.pnl_usd == null ? "—" : `$${fmtNum(t.pnl_usd, 2, true)}`}</td>
                    <td className="px-3 py-2.5 text-right text-sm tabular-nums" style={{ color: colorPN(t.pnl_pct) }}>{fmtNum(t.pnl_pct, 2, true)}%</td>
                    <td className="px-3 py-2.5 text-left text-xs text-[#9ca3af]">{t.close_reason ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right text-xs text-[#6b7280]">{t.closed_at_brt ?? "—"}</td>
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

function Kpi({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[#6b7280]">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums" style={{ color: color ?? "#f3f4f6" }}>{value}</p>
      {sub && <p className="text-xs text-[#6b7280]">{sub}</p>}
    </div>
  )
}

function Skeleton() {
  return (
    <div className="space-y-2 p-5">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-9 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
      ))}
    </div>
  )
}
