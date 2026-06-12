"use client"

import { useEffect, useState } from "react"
import { CheckCircle, Loader2, RefreshCw, Save } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { InfoTooltip } from "@/components/ui/tooltip"
import { api, ApiError } from "@/lib/api"
import type { BotConfig, BybitBalance } from "@/lib/types"

// Defaults alinhados à metodologia Encryptos (ver Manuais/):
// Reset do BTC = RSI 30m/1h <= ~50 · TPM combustão >= 800 · LSR favorável < 1.0
const DEFAULT_CONFIG: BotConfig = {
  session_name: "Padrão Encryptos",
  capital: 1000,
  balance: 1000,
  leverage: 5,
  min_tpm: 800,
  max_lsr: 1.0,
  max_rsi_btc: 50,
  min_score: 65,
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
  return { ...config, capital: bybitBalance.capital, balance: bybitBalance.balance }
}

function FormField({
  label,
  id,
  value,
  onChange,
  tooltip,
  type = "number",
  step,
  placeholder,
  readOnly = false,
}: {
  label: string
  id: string
  value: string | number | null
  onChange: (v: string) => void
  tooltip?: string
  type?: string
  step?: string
  placeholder?: string
  readOnly?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <Label htmlFor={id}>{label}</Label>
        {tooltip && <InfoTooltip text={tooltip} />}
      </div>
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
        setError("Erro ao carregar a configuração salva.")
      }

      if (bybitResult.status === "fulfilled") {
        setBybitBalance(bybitResult.value)
        nextConfig = applyBybitBalance(nextConfig, bybitResult.value)
        if (!bybitResult.value.connected) {
          setError((prev) => prev ?? bybitResult.value.error ?? "Saldo da Bybit indisponível.")
        }
      } else {
        setError((prev) => prev ?? "Saldo da Bybit indisponível. Verifique a chave/segredo da API.")
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
        "capital", "balance", "leverage", "min_tpm", "max_lsr", "max_rsi_btc",
        "min_score", "max_positions", "stop_loss_pct", "take_profit_pct",
        "trailing_stop_pct", "trailing_start_pct", "pcl_cooldown_minutes", "pcl_max_attempts",
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
        setError(freshBalance.error ?? "Erro ao consultar o saldo da Bybit.")
      }
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail)
      else setError("Erro ao consultar o saldo da Bybit.")
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
      setError("Erro ao salvar a configuração. Verifique a API.")
    } finally {
      setLoading(false)
    }
  }

  if (fetchLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-48 w-full animate-pulse rounded-xl bg-[#1a1d27]" aria-hidden="true" />
        ))}
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] px-5 py-4 text-sm leading-relaxed text-[#9ca3af]">
        <span className="font-semibold text-[#f3f4f6]">Como o bot decide: </span>
        ele só procura entrada quando o <b className="text-[#818cf8]">Bitcoin está em Reset</b> (sem alta vertical) e
        escolhe as moedas direto do <b className="text-[#818cf8]">Painel de Moedas</b> que batem o Setup de Ouro.
        Os campos abaixo controlam o rigor desses filtros e a gestão de risco.
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {saved && (
        <div role="status" className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 text-sm text-green-400">
          <CheckCircle className="h-4 w-4" aria-hidden="true" />
          Configuração salva com sucesso.
        </div>
      )}

      {/* Capital e Risco */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle>Capital e Risco</CardTitle>
            <Button variant="outline" size="sm" onClick={handleSyncBalance} disabled={syncingBalance}>
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
            label="Nome da configuração"
            id="session_name"
            type="text"
            value={config.session_name}
            onChange={(v) => setField("session_name", v)}
            tooltip="Apenas um rótulo para identificar este conjunto de parâmetros."
          />
          <FormField
            label="Valor por operação (USD)"
            id="capital"
            step="0.01"
            value={config.capital}
            readOnly={hasLiveBybitBalance(bybitBalance)}
            onChange={(v) => setField("capital", v)}
            tooltip="Quanto de capital (margem) o bot usa em cada moeda. Quando a Bybit está conectada, vem do saldo real da conta."
          />
          <FormField
            label="Saldo disponível (USD)"
            id="balance"
            step="0.01"
            value={config.balance}
            readOnly={hasLiveBybitBalance(bybitBalance)}
            onChange={(v) => setField("balance", v)}
            tooltip="Saldo livre para abrir novas posições. Sincronizado da Bybit quando conectada."
          />
          <FormField
            label="Alavancagem (x)"
            id="leverage"
            value={config.leverage}
            onChange={(v) => setField("leverage", v)}
            tooltip="Multiplicador da posição. A metodologia recomenda alavancagem moderada: moedas fortes sobem 'liquidando' (dão pavios pra baixo para tirar quem está muito alavancado). Sugerido: 5x."
          />
          {hasLiveBybitBalance(bybitBalance) && (
            <p className="sm:col-span-2 text-xs text-[#6b7280]">
              Bybit conectada: capital {bybitBalance.capital.toFixed(2)} USD, disponível {bybitBalance.balance.toFixed(2)} USD.
            </p>
          )}
          {bybitBalance && !bybitBalance.connected && (
            <p className="sm:col-span-2 text-xs text-amber-300">
              Bybit indisponível: {bybitBalance.error ?? "falha ao consultar o saldo."}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Filtro do Bitcoin */}
      <Card>
        <CardHeader>
          <CardTitle>Filtro do Bitcoin (Reset)</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label="RSI máximo do BTC"
            id="max_rsi_btc"
            step="1"
            value={config.max_rsi_btc}
            onChange={(v) => setField("max_rsi_btc", v)}
            tooltip="O bot só libera entradas quando o RSI do Bitcoin (30m ou 1h) está IGUAL OU ABAIXO deste valor — ou seja, em Reset (neutralidade/sobrevenda). Acima disso o mercado está 'quente' e operar é arriscado. Encryptos: ~50."
          />
        </CardContent>
      </Card>

      {/* Filtros de Entrada */}
      <Card>
        <CardHeader>
          <CardTitle>Filtros de Entrada (Setup de Ouro)</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label="Trades por minuto mínimo"
            id="min_tpm"
            value={config.min_tpm}
            onChange={(v) => setField("min_tpm", v)}
            tooltip="Velocidade de negociação que indica 'robôs ligados' (combustão). É o gatilho de ignição que tira a moeda do acúmulo. Encryptos: a partir de 800–1000 trades/min."
          />
          <FormField
            label="Proporção Long/Short máxima"
            id="max_lsr"
            step="0.01"
            value={config.max_lsr}
            onChange={(v) => setField("max_lsr", v)}
            tooltip="LSR = quanto o varejo está comprado vs vendido. Abaixo de 1.0 significa mais gente vendida (short) — combustível para o preço subir liquidando esses shorts (short squeeze). Encryptos: 1.0."
          />
          <FormField
            label="Pontuação mínima do painel"
            id="min_score"
            value={config.min_score}
            onChange={(v) => setField("min_score", v)}
            tooltip="Nota estrutural (0–100) calculada no Painel de Moedas (força no Exponencial BTC + atividade + OI + LSR). O bot só entra em moedas com nota igual ou acima deste valor. Sugerido: 65."
          />
          <FormField
            label="Máximo de posições simultâneas"
            id="max_positions"
            value={config.max_positions}
            onChange={(v) => setField("max_positions", v)}
            tooltip="Quantas moedas o bot pode manter abertas ao mesmo tempo. Limita a exposição total. Sugerido: 3."
          />
        </CardContent>
      </Card>

      {/* Gestão de Saída */}
      <Card>
        <CardHeader>
          <CardTitle>Gestão de Saída</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label="Stop / perda máxima (%)"
            id="stop_loss_pct"
            step="0.01"
            placeholder="Ex: 2"
            value={config.stop_loss_pct}
            onChange={(v) => setField("stop_loss_pct", v)}
            tooltip="Perda máxima aceita por operação antes de encerrar automaticamente. Protege o capital — o principal KPI da metodologia. Ex: 2%."
          />
          <FormField
            label="Alvo de lucro (%)"
            id="take_profit_pct"
            step="0.01"
            placeholder="Opcional"
            value={config.take_profit_pct}
            onChange={(v) => setField("take_profit_pct", v)}
            tooltip="Lucro alvo para encerrar a posição. Opcional — deixe vazio para deixar o lucro correr usando apenas o stop móvel."
          />
          <FormField
            label="Stop móvel — distância (%)"
            id="trailing_stop_pct"
            step="0.01"
            placeholder="Ex: 1.5"
            value={config.trailing_stop_pct}
            onChange={(v) => setField("trailing_stop_pct", v)}
            tooltip="Quando ativado, o stop 'segue' o preço a esta distância do topo, travando lucro conforme a moeda sobe. Ex: 1.5%."
          />
          <FormField
            label="Stop móvel — gatilho (%)"
            id="trailing_start_pct"
            step="0.01"
            placeholder="Ex: 1"
            value={config.trailing_start_pct}
            onChange={(v) => setField("trailing_start_pct", v)}
            tooltip="Lucro mínimo que a posição precisa atingir para o stop móvel ligar. Antes disso, vale o stop fixo. Ex: 1%."
          />
        </CardContent>
      </Card>

      {/* Reentrada após stop (PCL) */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-1.5">
            <CardTitle>Reentrada após Stop</CardTitle>
            <InfoTooltip text="Se uma moeda bate o stop mas a estrutura continua boa, o bot pode esperar um tempo e tentar entrar de novo (a tese pode continuar válida após a varredura de stops do varejo)." />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="pcl_enabled">Permitir reentrada</Label>
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
              label="Tempo de espera (minutos)"
              id="pcl_cooldown_minutes"
              value={config.pcl_cooldown_minutes}
              onChange={(v) => setField("pcl_cooldown_minutes", v)}
              tooltip="Quanto o bot espera após um stop antes de considerar reentrar na mesma moeda. Evita recomprar no susto. Ex: 60 min."
            />
            <FormField
              label="Máximo de tentativas"
              id="pcl_max_attempts"
              value={config.pcl_max_attempts}
              onChange={(v) => setField("pcl_max_attempts", v)}
              tooltip="Quantas reentradas o bot tenta na mesma moeda antes de desistir dela. Evita insistir num ativo que perdeu a estrutura. Ex: 3."
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
            Salvar Configuração
          </>
        )}
      </Button>
    </div>
  )
}
