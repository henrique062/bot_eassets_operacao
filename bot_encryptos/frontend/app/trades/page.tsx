"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { PnlChart } from "@/components/charts/pnl-chart"
import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api"
import type { Trade } from "@/lib/types"
import { cn, formatCurrency, formatPct, formatTimeBRT } from "@/lib/utils"
import { AlphaBadge } from "@/components/ui/alpha-badge"

function TradeStats({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) return null
  const totalPnl = trades.reduce((sum, trade) => sum + trade.total_pnl, 0)
  const wins = trades.filter((trade) => trade.total_pnl > 0).length
  const winRate = ((wins / trades.length) * 100).toFixed(1)
  const averagePnl = totalPnl / trades.length

  return (
    <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
      {[
        { label: "Total Trades", value: trades.length.toString() },
        { label: "Win Rate", value: `${winRate}%` },
        {
          label: "PnL Total",
          value: formatCurrency(totalPnl),
          color: totalPnl >= 0 ? "text-green-400" : "text-red-400",
        },
        {
          label: "Media/Trade",
          value: formatCurrency(averagePnl),
          color: averagePnl >= 0 ? "text-green-400" : "text-red-400",
        },
      ].map(({ label, value, color }) => (
        <Card key={label}>
          <CardHeader>
            <CardTitle>{label}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className={cn("font-mono text-xl font-bold", color ?? "text-white")}>{value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function TradesTable({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) {
    return <p className="p-6 text-center text-sm text-[#6b7280]">Nenhum trade encontrado.</p>
  }

  return (
    <Table aria-label="Historico de trades">
      <TableHeader>
        <TableRow>
          <TableHead>Simbolo</TableHead>
          <TableHead>Direcao</TableHead>
          <TableHead>Entrada</TableHead>
          <TableHead>Saida</TableHead>
          <TableHead>PnL $</TableHead>
          <TableHead>PnL %</TableHead>
          <TableHead>Motivo</TableHead>
          <TableHead>Fechado</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {trades.map((trade) => (
          <TableRow key={trade.id}>
            <TableCell>
              <div className="flex items-center gap-2">
                <span className="font-mono font-semibold">{trade.symbol}</span>
                <AlphaBadge isAlpha={trade.is_alpha} />
              </div>
            </TableCell>
            <TableCell>
              <Badge variant={trade.direction === "LONG" ? "success" : "danger"}>
                {trade.direction}
              </Badge>
            </TableCell>
            <TableCell className="font-mono">{formatCurrency(trade.entry_price)}</TableCell>
            <TableCell className="font-mono">{formatCurrency(trade.exit_price)}</TableCell>
            <TableCell
              className={cn(
                "font-mono",
                trade.total_pnl >= 0 ? "text-green-400" : "text-red-400"
              )}
            >
              {formatCurrency(trade.total_pnl)}
            </TableCell>
            <TableCell
              className={cn(
                "font-mono",
                trade.total_pnl_pct >= 0 ? "text-green-400" : "text-red-400"
              )}
            >
              {formatPct(trade.total_pnl_pct)}
            </TableCell>
            <TableCell>
              {trade.close_reason ? (
                <Badge variant="outline">{trade.close_reason}</Badge>
              ) : (
                <span className="text-[#6b7280]">-</span>
              )}
            </TableCell>
            <TableCell className="text-xs text-[#6b7280]">
              {formatTimeBRT(trade.close_time)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export default function TradesPage() {
  const { data: activeSessions, error: sessionsError } = usePolling(
    "active-sessions",
    api.listActiveSessions,
    3000
  )

  const activeConfigId = activeSessions?.[0]?.id

  const { data: trades, error } = usePolling(
    activeConfigId ? `trades-history-${activeConfigId}` : null,
    () => api.getTrades(activeConfigId!, 0, 200),
    15000
  )

  const longTrades = trades?.filter((trade) => trade.direction === "LONG") ?? []
  const shortTrades = trades?.filter((trade) => trade.direction === "SHORT") ?? []
  const hasError = Boolean(sessionsError) || Boolean(error)

  return (
    <div className="space-y-4">
      {hasError && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar historico de trades.
        </div>
      )}

      {!activeSessions ? null : !activeConfigId ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-[#6b7280]">
            Nenhuma sessao ativa no momento.
          </CardContent>
        </Card>
      ) : (
        <>
          {trades && <TradeStats trades={trades} />}

          {trades && trades.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>PnL Acumulado</CardTitle>
              </CardHeader>
              <CardContent>
                <PnlChart trades={trades} />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="p-0">
              {!trades ? (
                <div className="space-y-3 p-5">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <div
                      key={i}
                      className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]"
                      aria-hidden="true"
                    />
                  ))}
                </div>
              ) : (
                <Tabs defaultValue="all">
                  <div className="border-b border-[#2a2d3a] p-4">
                    <TabsList>
                      <TabsTrigger value="all">Todos ({trades.length})</TabsTrigger>
                      <TabsTrigger value="long">LONG ({longTrades.length})</TabsTrigger>
                      <TabsTrigger value="short">SHORT ({shortTrades.length})</TabsTrigger>
                    </TabsList>
                  </div>
                  <TabsContent value="all">
                    <TradesTable trades={trades} />
                  </TabsContent>
                  <TabsContent value="long">
                    <TradesTable trades={longTrades} />
                  </TabsContent>
                  <TabsContent value="short">
                    <TradesTable trades={shortTrades} />
                  </TabsContent>
                </Tabs>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
