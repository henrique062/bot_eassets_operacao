"use client"

import { useEffect, useState } from "react"
import { CheckCircle, Loader2, RefreshCw, Save } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { api, ApiError } from "@/lib/api"
import type { BotConfig, BybitBalance } from "@/lib/types"

const DEFAULT_CONFIG: BotConfig = {
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

function hasLiveBybitBalance(
  bybitBalance: BybitBalance | null
): bybitBalance is BybitBalance & { connected: true; capital: number; balance: number } {
  return Boolean(
    bybitBalance?.connected &&
      typeof bybitBalance.capital === "number" &&
      typeof bybitBalance.balance === "number"
  )
}

function applyBybitBalance(config: BotConfig, bybitBalance: BybitBalance | null): BotConfig {
  if (!hasLiveBybitBalance(bybitBalance)) return config

  return {
    ...config,
    capital: bybitBalance.capital,
    balance: bybitBalance.balance,
  }
}

function FormField({
  label,
  id,
  value,
  onChange,
  type = "number",
  step,
  placeholder,
  readOnly = false,
}: {
  label: string
  id: string
  value: string | number | null
  onChange: (v: string) => void
  type?: string
  step?: string
  placeholder?: string
  readOnly?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        step={step}
        placeholder={placeholder}
        value={value ?? ""}
        readOnly={readOnly}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

export default function ConfigPage() {
  const [config, setConfig] = useState<BotConfig>(DEFAULT_CONFIG)
  const [loading, setLoading] = useState(false)
  const [fetchLoading, setFetchLoading] = useState(true)
  const [syncingBalance, setSyncingBalance] = useState(false)
  const [saved, setSaved] = useState(false)
  const [configId, setConfigId] = useState<number | undefined>(undefined)
  const [bybitBalance, setBybitBalance] = useState<BybitBalance | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadConfig() {
      setFetchLoading(true)

      const [configResult, bybitResult] = await Promise.allSettled([
        api.getLatestConfig(),
        api.getBybitBalance(),
      ])

      if (cancelled) return

      let nextConfig = DEFAULT_CONFIG

      if (configResult.status === "fulfilled") {
        if (configResult.value) {
          nextConfig = configResult.value
          setConfigId(configResult.value.id)
        }
      } else {
        setError("Erro ao carregar configuracao salva.")
      }

      if (bybitResult.status === "fulfilled") {
        setBybitBalance(bybitResult.value)
        nextConfig = applyBybitBalance(nextConfig, bybitResult.value)
        if (!bybitResult.value.connected) {
          setError((prev) => prev ?? bybitResult.value.error ?? "Saldo Bybit indisponivel.")
        }
      } else {
        setError((prev) => prev ?? "Saldo Bybit indisponivel. Verifique API key/secret.")
      }

      setConfig(nextConfig)
      setFetchLoading(false)
    }

    loadConfig()

    return () => {
      cancelled = true
    }
  }, [])

  function setField<K extends keyof BotConfig>(key: K, raw: string) {
    setConfig((prev) => {
      const numFields: (keyof BotConfig)[] = [
        "capital",
        "balance",
        "leverage",
        "min_tpm",
        "max_lsr",
        "max_rsi_btc",
        "min_score",
        "max_positions",
        "stop_loss_pct",
        "take_profit_pct",
        "trailing_stop_pct",
        "trailing_start_pct",
        "pcl_cooldown_minutes",
        "pcl_max_attempts",
      ]

      if (numFields.includes(key)) {
        const value = raw === "" ? null : parseFloat(raw)
        return { ...prev, [key]: value }
      }

      return { ...prev, [key]: raw }
    })
  }

  async function handleSyncBalance() {
    setSyncingBalance(true)
    setError(null)
    try {
      const freshBalance = await api.getBybitBalance()
      setBybitBalance(freshBalance)
      if (hasLiveBybitBalance(freshBalance)) {
        setConfig((prev) => applyBybitBalance(prev, freshBalance))
      } else {
        setError(freshBalance.error ?? "Erro ao consultar saldo da Bybit.")
      }
    } catch (err) {
      if (err instanceof ApiError && err.detail) {
        setError(err.detail)
      } else {
        setError("Erro ao consultar saldo da Bybit.")
      }
    } finally {
      setSyncingBalance(false)
    }
  }

  async function handleSave() {
    setLoading(true)
    setError(null)
    setSaved(false)

    const payload = applyBybitBalance(config, bybitBalance)

    try {
      if (configId) {
        await api.updateConfig(configId, payload)
      } else {
        const created = (await api.saveConfig(payload)) as { config_id: number }
        setConfigId(created.config_id)
        setConfig((prev) => ({ ...prev, id: created.config_id }))
      }

      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch {
      setError("Erro ao salvar configuracao. Verifique a API.")
    } finally {
      setLoading(false)
    }
  }

  if (fetchLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-48 w-full animate-pulse rounded-xl bg-[#1a1d27]"
            aria-hidden="true"
          />
        ))}
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-6">
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          {error}
        </div>
      )}

      {saved && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 text-sm text-green-400"
        >
          <CheckCircle className="h-4 w-4" aria-hidden="true" />
          Configuracao salva com sucesso.
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle>Capital e Risco</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={handleSyncBalance}
              disabled={syncingBalance}
            >
              {syncingBalance ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Atualizando saldo...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Sincronizar Bybit
                </>
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label="Nome da Sessao"
            id="session_name"
            type="text"
            value={config.session_name}
            onChange={(v) => setField("session_name", v)}
          />
          <FormField
            label="Capital (USD)"
            id="capital"
            step="0.01"
            value={config.capital}
            readOnly={hasLiveBybitBalance(bybitBalance)}
            onChange={(v) => setField("capital", v)}
          />
          <FormField
            label="Balance Disponivel (USD)"
            id="balance"
            step="0.01"
            value={config.balance}
            readOnly={hasLiveBybitBalance(bybitBalance)}
            onChange={(v) => setField("balance", v)}
          />
          <FormField
            label="Alavancagem (x)"
            id="leverage"
            value={config.leverage}
            onChange={(v) => setField("leverage", v)}
          />
          {hasLiveBybitBalance(bybitBalance) && (
            <p className="sm:col-span-2 text-xs text-[#6b7280]">
              Bybit sincronizada: capital {bybitBalance.capital.toFixed(2)} USD, disponivel{" "}
              {bybitBalance.balance.toFixed(2)} USD.
            </p>
          )}
          {bybitBalance && !bybitBalance.connected && (
            <p className="sm:col-span-2 text-xs text-amber-300">
              Bybit indisponivel: {bybitBalance.error ?? "falha ao consultar saldo."}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Filtros de Entrada</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label="TPM Minimo"
            id="min_tpm"
            value={config.min_tpm}
            onChange={(v) => setField("min_tpm", v)}
          />
          <FormField
            label="LSR Maximo"
            id="max_lsr"
            step="0.01"
            value={config.max_lsr}
            onChange={(v) => setField("max_lsr", v)}
          />
          <FormField
            label="RSI BTC Maximo"
            id="max_rsi_btc"
            step="0.1"
            value={config.max_rsi_btc}
            onChange={(v) => setField("max_rsi_btc", v)}
          />
          <FormField
            label="Score Minimo"
            id="min_score"
            value={config.min_score}
            onChange={(v) => setField("min_score", v)}
          />
          <FormField
            label="Max. Posicoes"
            id="max_positions"
            value={config.max_positions}
            onChange={(v) => setField("max_positions", v)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Gestao de Risco</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label="Stop Loss (%)"
            id="stop_loss_pct"
            step="0.01"
            placeholder="Ex: 2"
            value={config.stop_loss_pct}
            onChange={(v) => setField("stop_loss_pct", v)}
          />
          <FormField
            label="Take Profit (%)"
            id="take_profit_pct"
            step="0.01"
            placeholder="Opcional"
            value={config.take_profit_pct}
            onChange={(v) => setField("take_profit_pct", v)}
          />
          <FormField
            label="Trailing Stop (%)"
            id="trailing_stop_pct"
            step="0.01"
            placeholder="Ex: 1.5"
            value={config.trailing_stop_pct}
            onChange={(v) => setField("trailing_stop_pct", v)}
          />
          <FormField
            label="Trailing Start (%)"
            id="trailing_start_pct"
            step="0.01"
            placeholder="Ex: 1"
            value={config.trailing_start_pct}
            onChange={(v) => setField("trailing_start_pct", v)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>PCL (Position Cycle Limit)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="pcl_enabled">Habilitar PCL</Label>
            <button
              id="pcl_enabled"
              role="switch"
              aria-checked={config.pcl_enabled}
              onClick={() => setConfig((prev) => ({ ...prev, pcl_enabled: !prev.pcl_enabled }))}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6366f1] ${
                config.pcl_enabled ? "bg-[#6366f1]" : "bg-[#2a2d3a]"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  config.pcl_enabled ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>
          <Separator />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              label="Cooldown PCL (minutos)"
              id="pcl_cooldown_minutes"
              value={config.pcl_cooldown_minutes}
              onChange={(v) => setField("pcl_cooldown_minutes", v)}
            />
            <FormField
              label="Max. Tentativas PCL"
              id="pcl_max_attempts"
              value={config.pcl_max_attempts}
              onChange={(v) => setField("pcl_max_attempts", v)}
            />
          </div>
        </CardContent>
      </Card>

      <Button onClick={handleSave} disabled={loading} className="w-full sm:w-auto">
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Salvando...
          </>
        ) : (
          <>
            <Save className="h-4 w-4" aria-hidden="true" />
            Salvar Configuracao
          </>
        )}
      </Button>
    </div>
  )
}
