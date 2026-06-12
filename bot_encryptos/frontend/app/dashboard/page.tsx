"use client"

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { EngineStatusCard } from "@/components/dashboard/engine-status-card"
import { BtcResetBadge } from "@/components/dashboard/btc-reset-badge"
import { PnlSummaryCard } from "@/components/dashboard/pnl-summary-card"
import { OpenPositionsTable } from "@/components/dashboard/open-positions-table"
import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api"

export default function DashboardPage() {
  const {
    data: status,
    error: statusError,
    mutate: mutateStatus,
  } = usePolling("bot-status", api.getBotStatus, 3000)

  const { data: positions, error: positionsError } = usePolling(
    "positions",
    api.getPositions,
    3000
  )

  const { data: trades } = usePolling("trades-all", () => api.getTrades(0, 200), 10000)

  return (
    <div className="space-y-6">
      {(statusError || positionsError) && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar dados do bot. Verifique se a API está disponível.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <EngineStatusCard status={status} onAction={() => mutateStatus()} />
        <BtcResetBadge status={status} />

        <Card>
          <CardHeader>
            <CardTitle>Posições Abertas</CardTitle>
          </CardHeader>
          <CardContent>
            {status ? (
              <p className="text-2xl font-bold font-mono text-white">
                {status.open_positions}
              </p>
            ) : (
              <div className="h-8 w-16 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
            )}
          </CardContent>
        </Card>

        <PnlSummaryCard trades={trades} />
      </div>

      <OpenPositionsTable positions={positions} />
    </div>
  )
}
