"use client"

import { Badge } from "@/components/ui/badge"
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
import { formatCurrency, minutesAgo } from "@/lib/utils"

export default function PositionsPage() {
  const { data: activeSessions, error: sessionsError } = usePolling(
    "active-sessions",
    api.listActiveSessions,
    3000
  )

  const activeConfigId = activeSessions?.[0]?.id

  const { data: positions, error } = usePolling(
    activeConfigId ? `positions-full-${activeConfigId}` : null,
    () => api.getPositions(activeConfigId!),
    2000
  )

  const hasError = Boolean(sessionsError) || Boolean(error)

  return (
    <div className="space-y-4">
      {hasError && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar posicoes. Verifique a conexao com a API.
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {!activeSessions ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3, 4].map((i) => (
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
          ) : !positions ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : positions.length === 0 ? (
            <p className="p-8 text-center text-sm text-[#6b7280]">
              Nenhuma posicao aberta no momento.
            </p>
          ) : (
            <Table aria-label="Posicoes abertas detalhadas">
              <TableHeader>
                <TableRow>
                  <TableHead>Simbolo</TableHead>
                  <TableHead>Direcao</TableHead>
                  <TableHead>Preco Entrada</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>TPM</TableHead>
                  <TableHead>LSR</TableHead>
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
                    <TableCell className="font-mono font-semibold">{pos.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={pos.direction === "LONG" ? "success" : "danger"}>
                        {pos.direction}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono">{formatCurrency(pos.entry_price)}</TableCell>
                    <TableCell className="font-mono">{formatCurrency(pos.value)}</TableCell>
                    <TableCell className="font-mono text-[#6b7280]">
                      {pos.entry_score?.toFixed(1) ?? "-"}
                    </TableCell>
                    <TableCell className="font-mono text-[#6b7280]">
                      {pos.entry_tpm?.toFixed(0) ?? "-"}
                    </TableCell>
                    <TableCell className="font-mono text-[#6b7280]">
                      {pos.entry_lsr?.toFixed(2) ?? "-"}
                    </TableCell>
                    <TableCell className="text-[#6b7280]">{minutesAgo(pos.open_timestamp)}</TableCell>
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
