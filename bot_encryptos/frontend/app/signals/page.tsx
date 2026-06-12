"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { SignalsTable } from "@/components/signals/signals-table"
import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api"

export default function SignalsPage() {
  const { data: signals, error: signalsError } = usePolling(
    "signals",
    api.getSignals,
    5000
  )

  const { data: btc, error: btcError } = usePolling(
    "btc-status",
    api.getBtcStatus,
    5000
  )

  const hasError = signalsError || btcError

  return (
    <div className="space-y-4">
      {hasError && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar sinais de mercado.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>BTC RSI 30m</CardTitle>
          </CardHeader>
          <CardContent>
            {btc ? (
              <p className="text-2xl font-bold font-mono text-white">
                {btc.btc_rsi_30m.toFixed(1)}
              </p>
            ) : (
              <div className="h-8 w-20 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>BTC RSI 1h</CardTitle>
          </CardHeader>
          <CardContent>
            {btc ? (
              <p className="text-2xl font-bold font-mono text-white">
                {btc.btc_rsi_1h.toFixed(1)}
              </p>
            ) : (
              <div className="h-8 w-20 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Status Reset</CardTitle>
          </CardHeader>
          <CardContent>
            {btc ? (
              <Badge variant={btc.is_reset ? "danger" : "success"}>
                {btc.is_reset ? "EM RESET" : "NORMAL"}
              </Badge>
            ) : (
              <div className="h-6 w-20 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-0">
          <SignalsTable signals={signals} />
        </CardContent>
      </Card>
    </div>
  )
}
