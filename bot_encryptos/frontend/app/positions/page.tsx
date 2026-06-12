"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { formatCurrency, formatTimeBRT, minutesAgo } from "@/lib/utils"
import type { LivePosition } from "@/lib/types"
import { AlphaBadge } from "@/components/ui/alpha-badge"

function fmtUsd(value: number | null | undefined): string {
  return typeof value === "number" ? formatCurrency(value) : "-"
}

function fmtNum(value: number | null | undefined, digits = 4): string {
  return typeof value === "number" ? value.toLocaleString("pt-BR", { maximumFractionDigits: digits }) : "-"
}

function fmtPct(value: number | null | undefined): string {
  if (typeof value !== "number") return "-"
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
}

function openedAt(value: number | null): string {
  return value ? minutesAgo(value) : "-"
}

function pnlClass(value: number | null): string {
  if (typeof value !== "number") return "text-[#6b7280]"
  return value >= 0 ? "text-green-400" : "text-red-400"
}

function PositionsTable({
  title,
  description,
  positions,
  emptyLabel,
}: {
  title: string
  description: string
  positions: LivePosition[]
  emptyLabel: string
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <p className="text-sm text-[#6b7280]">{description}</p>
      </CardHeader>
      <CardContent className="p-0">
        {positions.length === 0 ? (
          <p className="p-8 text-center text-sm text-[#6b7280]">{emptyLabel}</p>
        ) : (
          <Table aria-label={title}>
            <TableHeader>
              <TableRow>
                <TableHead>Simbolo</TableHead>
                <TableHead>Direcao</TableHead>
                <TableHead>Entrada</TableHead>
                <TableHead>Marcacao</TableHead>
                <TableHead>Tamanho</TableHead>
                <TableHead>Valor</TableHead>
                <TableHead>PnL</TableHead>
                <TableHead>Aberta ha</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((pos) => (
                <TableRow
                  key={pos.id}
                  className={
                    pos.direction === "LONG"
                      ? "border-l-2 border-l-green-500/40"
                      : "border-l-2 border-l-red-500/40"
                  }
                >
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold">{pos.symbol}</span>
                        <AlphaBadge isAlpha={pos.is_alpha} />
                      </div>
                      <span className="text-xs text-[#6b7280]">
                        {pos.source === "BOT" ? `config #${pos.source_config_id ?? "-"}` : "aberta fora do bot"}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={pos.direction === "LONG" ? "success" : "danger"}>
                      {pos.direction}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono">{fmtUsd(pos.entry_price)}</TableCell>
                  <TableCell className="font-mono">{fmtUsd(pos.mark_price)}</TableCell>
                  <TableCell className="font-mono text-[#9ca3af]">{fmtNum(pos.size)}</TableCell>
                  <TableCell className="font-mono">{fmtUsd(pos.value)}</TableCell>
                  <TableCell className={`font-mono ${pnlClass(pos.unrealised_pnl)}`}>
                    <div className="flex flex-col">
                      <span>{fmtUsd(pos.unrealised_pnl)}</span>
                      <span className="text-xs">{fmtPct(pos.pnl_pct)}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-[#6b7280]">{openedAt(pos.open_timestamp)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

export default function PositionsPage() {
  const { data, error } = usePolling("live-positions", () => api.getLivePositions(), 3000)
  const positions = data?.positions ?? []
  const botPositions = positions.filter((pos) => pos.source === "BOT")
  const manualPositions = positions.filter((pos) => pos.source !== "BOT")
  const totalValue = positions.reduce((sum, pos) => sum + (pos.value || 0), 0)
  const totalPnl = positions.reduce((sum, pos) => sum + (pos.unrealised_pnl || 0), 0)

  return (
    <div className="space-y-4">
      {(error || data?.error) && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          {data?.error ?? "Erro ao carregar posicoes em tempo real. Verifique a conexao com a API."}
        </div>
      )}

      {!data ? (
        <Card>
          <CardContent className="space-y-3 p-5">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]"
                aria-hidden="true"
              />
            ))}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <Card>
              <CardContent className="p-4">
                <p className="text-xs uppercase tracking-wide text-[#6b7280]">Total aberto</p>
                <p className="mt-1 text-2xl font-semibold text-white">{positions.length}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs uppercase tracking-wide text-[#6b7280]">Pelo bot</p>
                <p className="mt-1 text-2xl font-semibold text-green-400">{data.bot_count}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs uppercase tracking-wide text-[#6b7280]">Por fora</p>
                <p className="mt-1 text-2xl font-semibold text-amber-300">{data.manual_count}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs uppercase tracking-wide text-[#6b7280]">PnL aberto</p>
                <p className={`mt-1 text-2xl font-semibold ${pnlClass(totalPnl)}`}>{fmtUsd(totalPnl)}</p>
                <p className="mt-1 text-xs text-[#6b7280]">Valor: {fmtUsd(totalValue)}</p>
              </CardContent>
            </Card>
          </div>

          <div className="rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-4 py-3 text-sm text-[#6b7280]">
            Fonte: Bybit em tempo real. Ultima leitura:{" "}
            <span className="text-white">{formatTimeBRT(data.fetched_at)}</span>
          </div>

          <PositionsTable
            title="Posicoes abertas pelo bot"
            description="Posicoes da conta que batem com registros abertos do motor no banco."
            positions={botPositions}
            emptyLabel="Nenhuma posicao aberta pelo bot no momento."
          />

          <PositionsTable
            title="Posicoes abertas por fora"
            description="Posicoes reais na Bybit sem registro aberto correspondente no bot."
            positions={manualPositions}
            emptyLabel="Nenhuma posicao manual aberta no momento."
          />
        </>
      )}
    </div>
  )
}
