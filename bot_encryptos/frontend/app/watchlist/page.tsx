"use client"

import { useMemo, useState } from "react"
import { Loader2, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api"
import type { WatchlistEntry } from "@/lib/types"
import { cooldownRemaining, formatCurrency, formatTimeBRT } from "@/lib/utils"
import { AlphaBadge } from "@/components/ui/alpha-badge"

type WatchlistState = WatchlistEntry["state"]

const STATE_VARIANT: Record<WatchlistState, "blue" | "warning" | "success" | "danger" | "muted"> = {
  WATCHLIST: "blue",
  COOLDOWN: "warning",
  CANDIDATE: "success",
  INVALIDATED: "danger",
  COMPLETED: "muted",
}

const STATE_LABEL: Record<WatchlistState, string> = {
  WATCHLIST: "Em observação",
  COOLDOWN: "Aguardando",
  CANDIDATE: "Candidata",
  INVALIDATED: "Invalidada",
  COMPLETED: "Concluída",
}

const ENCERRADAS: WatchlistState[] = ["INVALIDATED", "COMPLETED"]

export default function WatchlistPage() {
  const { data: activeSessions } = usePolling("active-sessions", api.listActiveSessions, 5000)
  const activeConfigId = activeSessions?.[0]?.id

  // Carrega a watchlist mesmo sem sessão ativa (backend cai no último config).
  const { data: watchlist, error, mutate } = usePolling(
    "watchlist",
    () => api.getWatchlist(activeConfigId),
    5000
  )
  const [removing, setRemoving] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)

  const rows = useMemo(() => {
    const all = watchlist ?? []
    return showHistory ? all : all.filter((e) => !ENCERRADAS.includes(e.state))
  }, [watchlist, showHistory])

  async function handleRemove(symbol: string) {
    setRemoving(symbol)
    try {
      await api.removeFromWatchlist(activeConfigId ?? 0, symbol)
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
          Erro ao carregar a watchlist.
        </div>
      )}

      <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-5 py-4 text-sm leading-relaxed text-[#9ca3af]">
        <span className="font-semibold text-[#f3f4f6]">O que é a Watchlist: </span>
        quando uma moeda bate o stop mas a estrutura segue boa, ela entra aqui para possível reentrada (após a varredura
        de stops do varejo). Estados encerrados (<b className="text-[#f87171]">Invalidada</b> /{" "}
        <b className="text-[#9ca3af]">Concluída</b>) ficam guardados — ative o histórico para vê-los.
      </div>

      <div className="flex items-center justify-between">
        <span className="text-sm text-[#6b7280]">
          {rows.length} {showHistory ? "registros (histórico)" : "em acompanhamento"}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={showHistory ? "true" : "false"}
          onClick={() => setShowHistory((v) => !v)}
          className="flex items-center gap-2 text-sm font-medium text-[#9ca3af] hover:text-white"
        >
          <span
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${showHistory ? "bg-[#6366f1]" : "bg-[#2a2d3a]"}`}
          >
            <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${showHistory ? "translate-x-4" : "translate-x-1"}`} />
          </span>
          Mostrar histórico
        </button>
      </div>

      <Card>
        <CardContent className="p-0">
          {!watchlist ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <p className="p-8 text-center text-sm text-[#6b7280]">
              {showHistory
                ? "Nenhum registro na watchlist ainda. Ela é preenchida quando o bot está operando e uma posição bate o stop."
                : "Nenhuma moeda em acompanhamento. (Histórico desligado — ligue acima para ver encerradas.)"}
            </p>
          ) : (
            <Table aria-label="Watchlist de reentrada">
              <TableHeader>
                <TableRow>
                  <TableHead>Símbolo</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Tentativas</TableHead>
                  <TableHead>PnL acumulado</TableHead>
                  <TableHead>Espera restante</TableHead>
                  <TableHead>Adicionada em</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold">{entry.symbol}</span>
                        <AlphaBadge isAlpha={entry.is_alpha} />
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATE_VARIANT[entry.state]}>{STATE_LABEL[entry.state] ?? entry.state}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-[#6b7280]">
                      {entry.attempt_count}/{entry.max_attempts}
                    </TableCell>
                    <TableCell className={entry.total_pnl_so_far >= 0 ? "font-mono text-green-400" : "font-mono text-red-400"}>
                      {formatCurrency(entry.total_pnl_so_far)}
                    </TableCell>
                    <TableCell className="text-xs text-[#6b7280]">
                      {entry.state === "COOLDOWN" ? cooldownRemaining(entry.cooldown_until) : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-[#6b7280]">{formatTimeBRT(entry.added_at)}</TableCell>
                    <TableCell>
                      {!ENCERRADAS.includes(entry.state) && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleRemove(entry.symbol)}
                          disabled={removing === entry.symbol}
                          aria-label={`Remover ${entry.symbol} da watchlist`}
                        >
                          {removing === entry.symbol ? (
                            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                          ) : (
                            <Trash2 className="h-4 w-4 text-red-400" aria-hidden="true" />
                          )}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
