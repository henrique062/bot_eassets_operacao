"use client"

import { useState } from "react"
import { Power, PowerOff, Loader2 } from "lucide-react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api, ApiError } from "@/lib/api"
import type { BotStatus, BotConfig } from "@/lib/types"

interface EngineStatusCardProps {
  status: BotStatus | undefined
  activeConfigId?: number
  onAction: () => void
}

export function EngineStatusCard({ status, activeConfigId, onAction }: EngineStatusCardProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleStop() {
    if (!activeConfigId) return
    setLoading(true)
    setError(null)
    try {
      await api.stopBot(activeConfigId)
      onAction()
    } catch (err) {
      if (err instanceof ApiError && err.detail) {
        setError(err.detail)
      } else {
        setError("Erro ao parar o bot.")
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleStart() {
    setLoading(true)
    setError(null)
    try {
      let config: BotConfig = {
        session_name: "default",
        capital: 1000,
        balance: 1000,
        leverage: 5,
        min_tpm: 100,
        max_lsr: 1.5,
        max_rsi_btc: 70,
        min_score: 60,
        max_positions: 3,
        stop_loss_pct: 2,
        take_profit_pct: null,
        trailing_stop_pct: 1.5,
        trailing_start_pct: 1,
        pcl_enabled: true,
        pcl_cooldown_minutes: 60,
        pcl_max_attempts: 3,
      }

      try {
        config = await api.getLatestConfig()
      } catch (err) {
        if (!(err instanceof ApiError && err.status === 404)) {
          throw err
        }
      }

      const bybitBalance = await api.getBybitBalance()
      if (
        !bybitBalance.connected ||
        typeof bybitBalance.capital !== "number" ||
        typeof bybitBalance.balance !== "number"
      ) {
        throw new Error(bybitBalance.error ?? "Saldo Bybit indisponivel.")
      }

      config = {
        ...config,
        capital: bybitBalance.capital,
        balance: bybitBalance.balance,
      }

      await api.startBot(config)
      onAction()
    } catch (err) {
      if (err instanceof ApiError && err.detail) {
        setError(err.detail)
      } else if (err instanceof Error && err.message) {
        setError(err.message)
      } else {
        setError("Erro ao iniciar o bot.")
      }
    } finally {
      setLoading(false)
    }
  }

  const isRunning = status?.engine_status === "Running"

  return (
    <Card>
      <CardHeader>
        <CardTitle>Engine Status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {status ? (
          <div className="flex items-center justify-between gap-4">
            <Badge variant={isRunning ? "success" : "danger"}>
              {status.engine_status}
            </Badge>
            <Button
              variant={isRunning ? "destructive" : "success"}
              size="sm"
              onClick={isRunning ? handleStop : handleStart}
              disabled={loading || (isRunning && !activeConfigId)}
              aria-label={isRunning ? "Parar bot" : "Iniciar bot"}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : isRunning ? (
                <>
                  <PowerOff className="h-4 w-4" aria-hidden="true" />
                  Stop
                </>
              ) : (
                <>
                  <Power className="h-4 w-4" aria-hidden="true" />
                  Start
                </>
              )}
            </Button>
          </div>
        ) : (
          <div className="h-6 w-32 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
        )}
        {error && <p className="text-sm text-red-400">{error}</p>}
      </CardContent>
    </Card>
  )
}
