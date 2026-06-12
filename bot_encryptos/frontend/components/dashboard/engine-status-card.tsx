"use client"

import { useState } from "react"
import { Power, PowerOff, Loader2 } from "lucide-react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import type { BotStatus, BotConfig } from "@/lib/types"

interface EngineStatusCardProps {
  status: BotStatus | undefined
  activeConfigId?: number
  onAction: () => void
}

export function EngineStatusCard({ status, activeConfigId, onAction }: EngineStatusCardProps) {
  const [loading, setLoading] = useState(false)

  async function handleStop() {
    if (!activeConfigId) return
    setLoading(true)
    try {
      await api.stopBot(activeConfigId)
      onAction()
    } catch {
    } finally {
      setLoading(false)
    }
  }

  async function handleStart() {
    setLoading(true)
    try {
      const defaultConfig: BotConfig = {
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
      await api.startBot(defaultConfig)
      onAction()
    } catch {
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
      <CardContent className="flex items-center justify-between gap-4">
        {status ? (
          <>
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
          </>
        ) : (
          <div className="h-6 w-32 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
        )}
      </CardContent>
    </Card>
  )
}
