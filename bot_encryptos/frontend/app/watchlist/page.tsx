"use client"

import { useState } from "react"
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

type WatchlistState = WatchlistEntry["state"]

const STATE_VARIANT: Record<WatchlistState, "blue" | "warning" | "success" | "danger" | "muted"> =
  {
    WATCHLIST: "blue",
    COOLDOWN: "warning",
    CANDIDATE: "success",
    INVALIDATED: "danger",
    COMPLETED: "muted",
  }

export default function WatchlistPage() {
  const { data: activeSessions, error: sessionsError } = usePolling(
    "active-sessions",
    api.listActiveSessions,
    3000
  )
  const activeConfigId = activeSessions?.[0]?.id

  const { data: watchlist, error, mutate } = usePolling(
    activeConfigId ? `watchlist-${activeConfigId}` : null,
    () => api.getWatchlist(activeConfigId!),
    5000
  )
  const [removing, setRemoving] = useState<string | null>(null)

  async function handleRemove(symbol: string) {
    if (!activeConfigId) return

    setRemoving(symbol)
    try {
      await api.removeFromWatchlist(activeConfigId, symbol)
      mutate()
    } catch {
    } finally {
      setRemoving(null)
    }
  }

  const hasError = Boolean(sessionsError) || Boolean(error)

  return (
    <div className="space-y-4">
      {hasError && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar watchlist.
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {!activeSessions ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : !activeConfigId ? (
            <p className="p-8 text-center text-sm text-[#6b7280]">
              Nenhuma sessao ativa no momento.
            </p>
          ) : !watchlist ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : watchlist.length === 0 ? (
            <p className="p-8 text-center text-sm text-[#6b7280]">
              Nenhuma moeda na watchlist.
            </p>
          ) : (
            <Table aria-label="Watchlist PCL">
              <TableHeader>
                <TableRow>
                  <TableHead>Simbolo</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Tentativas</TableHead>
                  <TableHead>PnL Acumulado</TableHead>
                  <TableHead>Cooldown Restante</TableHead>
                  <TableHead>Ultima Verificacao</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {watchlist.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="font-mono font-semibold">{entry.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={STATE_VARIANT[entry.state]}>{entry.state}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-[#6b7280]">
                      {entry.attempt_count}/{entry.max_attempts}
                    </TableCell>
                    <TableCell
                      className={
                        entry.total_pnl_so_far >= 0
                          ? "font-mono text-green-400"
                          : "font-mono text-red-400"
                      }
                    >
                      {formatCurrency(entry.total_pnl_so_far)}
                    </TableCell>
                    <TableCell className="text-xs text-[#6b7280]">
                      {entry.state === "COOLDOWN" ? cooldownRemaining(entry.cooldown_until) : "-"}
                    </TableCell>
                    <TableCell className="text-xs text-[#6b7280]">
                      {formatTimeBRT(entry.last_check_at)}
                    </TableCell>
                    <TableCell>
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
