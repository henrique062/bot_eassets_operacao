"use client"

import { useState } from "react"
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
import { formatCurrency, formatPct, formatTimeBRT } from "@/lib/utils"
import type { Trade } from "@/lib/types"
import { cn } from "@/lib/utils"

function TradeStats({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) return null
  const totalPnl = trades.reduce((s, t) => s + t.total_pnl, 0)
  const wins = trades.filter((t) => t.total_pnl > 0).length
  const winRate = ((wins / trades.length) * 100).toFixed(1)
  const avg = totalPnl / trades.length

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
      {[
        { label: "Total Trades", value: trades.length.toString() },
        { label: "Win Rate", value: `${winRate}%` },
        {
          label: "PnL Total",
          value: formatCurrency(totalPnl),
          color: totalPnl >= 0 ? "text-green-400" : "text-red-400",
        },
        {
          label: "Média/Trade",
          value: formatCurrency(avg),
          color: avg >= 0 ? "text-green-400" : "text-red-400",
        },
      ].map(({ label, value, color }) => (
        <Card key={label}>
          <CardHeader>
            <CardTitle>{label}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className={cn("text-xl font-bold font-mono", color ?? "text-white")}>{value}</p>
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
    <Table aria-label="Histórico de trades">
      <TableHeader>
        <TableRow>
          <TableHead>Símbolo</TableHead>
          <TableHead>Direção</TableHead>
          <TableHead>Entrada</TableHead>
          <TableHead>Saída</TableHead>
          <TableHead>PnL $</TableHead>
          <TableHead>PnL %</TableHead>
          <TableHead>Motivo</TableHead>
          <TableHead>Fechado</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {trades.map((t) => (
          <TableRow key={t.id}>
            <TableCell className="font-mono font-semibold">{t.symbol}</TableCell>
            <TableCell>
              <Badge variant={t.direction === "LONG" ? "success" : "danger"}>
                {t.direction}
              </Badge>
            </TableCell>
            <TableCell className="font-mono">{formatCurrency(t.entry_price)}</TableCell>
            <TableCell className="font-mono">{formatCurrency(t.exit_price)}</TableCell>
            <TableCell
              className={cn("font-mono", t.total_pnl >= 0 ? "text-green-400" : "text-red-400")}
            >
              {formatCurrency(t.total_pnl)}
            </TableCell>
            <TableCell
              className={cn(
                "font-mono",
                t.total_pnl_pct >= 0 ? "text-green-400" : "text-red-400"
              )}
            >
              {formatPct(t.total_pnl_pct)}
            </TableCell>
            <TableCell>
              {t.close_reason ? (
                <Badge variant="outline">{t.close_reason}</Badge>
              ) : (
                <span className="text-[#6b7280]">—</span>
              )}
            </TableCell>
            <TableCell className="text-[#6b7280] text-xs">
              {formatTimeBRT(t.close_time)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export default function TradesPage() {
  const [activeSymbol] = useState("")
  const { data: trades, error } = usePolling("trades-history", () => api.getTrades(0, 200), 15000)

  const longTrades = trades?.filter((t) => t.direction === "LONG") ?? []
  const shortTrades = trades?.filter((t) => t.direction === "SHORT") ?? []

  return (
    <div className="space-y-4">
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar histórico de trades.
        </div>
      )}

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
            <div className="p-5 space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
              ))}
            </div>
          ) : (
            <Tabs defaultValue="all">
              <div className="p-4 border-b border-[#2a2d3a]">
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
    </div>
  )
}
