"use client"

import { useState } from "react"
import { Trash2, Loader2 } from "lucide-react"
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
import { formatCurrency, formatTimeBRT, cooldownRemaining } from "@/lib/utils"
import type { WatchlistEntry } from "@/lib/types"

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
  const { data: watchlist, error, mutate } = usePolling("watchlist", api.getWatchlist, 5000)
  const [removing, setRemoving] = useState<string | null>(null)

  async function handleRemove(symbol: string) {
    setRemoving(symbol)
    try {
      await api.removeFromWatchlist(symbol)
      mutate()
    } catch {
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar watchlist.
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {!watchlist ? (
            <div className="p-5 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
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
                  <TableHead>Símbolo</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Tentativas</TableHead>
                  <TableHead>PnL Acumulado</TableHead>
                  <TableHead>Cooldown Restante</TableHead>
                  <TableHead>Última Verificação</TableHead>
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
                          ? "text-green-400 font-mono"
                          : "text-red-400 font-mono"
                      }
                    >
                      {formatCurrency(entry.total_pnl_so_far)}
                    </TableCell>
                    <TableCell className="text-[#6b7280] text-xs">
                      {entry.state === "COOLDOWN"
                        ? cooldownRemaining(entry.cooldown_until)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-[#6b7280] text-xs">
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
