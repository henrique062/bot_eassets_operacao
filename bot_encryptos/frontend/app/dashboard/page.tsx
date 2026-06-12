"use client"

import { EngineStatusCard } from "@/components/dashboard/engine-status-card"
import { BtcResetBadge } from "@/components/dashboard/btc-reset-badge"
import { PnlSummaryCard } from "@/components/dashboard/pnl-summary-card"
import { OpenPositionsTable } from "@/components/dashboard/open-positions-table"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api"
import type { BotStatus } from "@/lib/types"

export default function DashboardPage() {
  const {
    data: activeSessions,
    error: sessionsError,
    mutate: mutateSessions,
  } = usePolling("active-sessions", api.listActiveSessions, 3000)

  const activeConfigId = activeSessions?.[0]?.id

  const {
    data: sessionStatus,
    error: statusError,
    mutate: mutateStatus,
  } = usePolling(
    activeConfigId ? `bot-status-${activeConfigId}` : null,
    () => api.getBotStatus(activeConfigId!),
    3000
  )

  const { data: btcStatus, error: btcError } = usePolling("btc-status", api.getBtcStatus, 10000)

  const { data: positions, error: positionsError } = usePolling(
    activeConfigId ? `positions-${activeConfigId}` : null,
    () => api.getPositions(activeConfigId!),
    3000
  )

  const { data: trades } = usePolling(
    activeConfigId ? `trades-all-${activeConfigId}` : null,
    () => api.getTrades(activeConfigId!, 0, 200),
    10000
  )

  const status: BotStatus | undefined = btcStatus
    ? {
        engine_status: activeConfigId ? "Running" : "Stopped",
        open_positions: sessionStatus?.open_positions ?? 0,
        last_decision_at: null,
        btc_rsi_30m: btcStatus.rsi_30m ?? 0,
        btc_rsi_1h: btcStatus.rsi_1h ?? 0,
        btc_is_reset: btcStatus.is_reset,
        watchlist_count: 0,
      }
    : undefined

  const hasApiError =
    Boolean(sessionsError) ||
    Boolean(btcError) ||
    Boolean(statusError) ||
    Boolean(positionsError)

  async function handleAction() {
    await Promise.all([mutateSessions(), mutateStatus()])
  }

  return (
    <div className="space-y-6">
      {hasApiError && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar dados do bot. Verifique se a API esta disponivel.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <EngineStatusCard
          status={status}
          activeConfigId={activeConfigId}
          onAction={handleAction}
        />
        <BtcResetBadge status={status} />

        <Card>
          <CardHeader>
            <CardTitle>Posicoes Abertas</CardTitle>
          </CardHeader>
          <CardContent>
            {status ? (
              <p className="font-mono text-2xl font-bold text-white">{status.open_positions}</p>
            ) : (
              <div className="h-8 w-16 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
            )}
          </CardContent>
        </Card>

        <PnlSummaryCard trades={trades} />
      </div>

      <OpenPositionsTable positions={positions ?? []} />
    </div>
  )
}
