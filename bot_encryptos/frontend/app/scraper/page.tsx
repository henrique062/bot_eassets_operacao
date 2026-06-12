"use client"

import { useState } from "react"
import Link from "next/link"
import { RefreshCw, Loader2, CheckCircle, XCircle, Clock } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { usePolling } from "@/hooks/use-polling"
import { api, ApiError } from "@/lib/api"
import { formatTimeBRT } from "@/lib/utils"

export default function ScraperPage() {
  const { data: status, error, mutate } = usePolling("scraper-status", api.getScraperStatus, 5000)
  const { data: snapshots, mutate: mutateSnaps } = usePolling(
    "scraper-history",
    api.getPanelSnapshots,
    30000
  )
  const [triggering, setTriggering] = useState(false)
  const [triggerResult, setTriggerResult] = useState<"ok" | "running" | "error" | null>(null)

  async function handleTrigger() {
    setTriggering(true)
    setTriggerResult(null)
    try {
      await api.triggerScrape()
      setTriggerResult("ok")
      mutate()
      mutateSnaps()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setTriggerResult("running")
      } else {
        setTriggerResult("error")
      }
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          Erro ao carregar status do scraper.
        </div>
      )}

      {triggerResult === "ok" && (
        <div
          role="status"
          className="rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 text-sm text-green-400 flex items-center gap-2"
        >
          <CheckCircle className="h-4 w-4" aria-hidden="true" />
          Captura iniciada com sucesso.
        </div>
      )}

      {triggerResult === "error" && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400 flex items-center gap-2"
        >
          <XCircle className="h-4 w-4" aria-hidden="true" />
          Erro ao iniciar captura.
        </div>
      )}

      {triggerResult === "running" && (
        <div
          role="status"
          className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300 flex items-center gap-2"
        >
          <Clock className="h-4 w-4" aria-hidden="true" />
          Ja existe uma captura em andamento.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Status do Scraper</CardTitle>
          </CardHeader>
          <CardContent>
            {!status ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <div key={i} className="h-4 w-full animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge variant={status.running ? "success" : "muted"}>
                    {status.running ? "Running" : "Idle"}
                  </Badge>
                </div>
                <div className="space-y-1.5 text-sm">
                  <div className="flex items-center gap-2 text-[#6b7280]">
                    <CheckCircle className="h-3.5 w-3.5 text-green-400 shrink-0" aria-hidden="true" />
                    <span>Última OK:</span>
                    <span className="text-white">{formatTimeBRT(status.last_ok)}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[#6b7280]">
                    <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" aria-hidden="true" />
                    <span>Último erro:</span>
                    <span className="text-white truncate max-w-[200px]" title={status.last_error ?? ""}>
                      {status.last_error ?? "—"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[#6b7280]">
                    <Clock className="h-3.5 w-3.5 text-amber-400 shrink-0" aria-hidden="true" />
                    <span>Próxima execução:</span>
                    <span className="text-white">{formatTimeBRT(status.next_run_at)}</span>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Ação Manual</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[#6b7280] mb-4">
              Dispara uma captura imediata dos dados eAssets, independente do intervalo automático.
            </p>
            <Button
              onClick={handleTrigger}
              disabled={triggering || status?.running}
              aria-label="Iniciar captura manual"
            >
              {triggering ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Capturando...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Capturar Agora
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Histórico de Capturas</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {!snapshots ? (
            <div className="space-y-2 p-5">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-9 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
              ))}
            </div>
          ) : snapshots.length === 0 ? (
            <p className="p-5 text-sm text-[#6b7280]">Nenhuma captura registrada ainda.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-[#2a2d3a]">
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">Data da captura</th>
                    <th className="px-4 py-3 text-right text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">Ativos</th>
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">Exchange</th>
                    <th className="px-4 py-3 text-center text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">BTC Reset</th>
                    <th className="px-4 py-3 text-right text-[10px] font-semibold uppercase tracking-wide text-[#6b7280]">Ver painel</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshots.map((s) => (
                    <tr key={s.id} className="border-b border-[#23262f] hover:bg-[#20232d]">
                      <td className="px-4 py-2.5 text-left text-sm text-[#d1d5db] tabular-nums">{s.timestamp_brt}</td>
                      <td className="px-4 py-2.5 text-right text-sm text-[#9ca3af] tabular-nums">{s.symbols ?? "—"}</td>
                      <td className="px-4 py-2.5 text-left text-sm text-[#9ca3af]">{s.exchange ?? "—"}</td>
                      <td className="px-4 py-2.5 text-center">
                        <Badge variant={s.btc_reset ? "danger" : "muted"}>
                          {s.btc_reset ? "Em reset" : "Normal"}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <Link href={`/analise/snapshot/${s.id}`} className="text-sm font-semibold text-[#818cf8] hover:underline">
                          Abrir
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
