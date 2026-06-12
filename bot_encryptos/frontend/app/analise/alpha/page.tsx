"use client"

import { useMemo, useState } from "react"
import useSWR from "swr"
import { Loader2, Plus, Trash2 } from "lucide-react"
import { api, ApiError } from "@/lib/api"
import { AlphaBadge } from "@/components/ui/alpha-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function parseSymbols(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\s,;]+/)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  )
}

export default function AlphaPage() {
  const { data, error, isLoading, mutate } = useSWR("alpha-symbols", api.getAlphaSymbols, {
    revalidateOnFocus: false,
  })
  const [input, setInput] = useState("")
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const symbols = data?.symbols ?? []
  const pending = useMemo(() => parseSymbols(input), [input])

  async function handleAdd() {
    if (!pending.length) return
    setSaving(true)
    setMessage(null)
    try {
      const result = await api.addAlphaSymbols(pending)
      setInput("")
      setMessage(`${result.added.length} moeda(s) marcada(s) como Alpha.`)
      await mutate()
    } catch (err) {
      setMessage(err instanceof ApiError && err.detail ? err.detail : "Erro ao salvar moedas Alpha.")
    } finally {
      setSaving(false)
    }
  }

  async function handleRemove(symbol: string) {
    setRemoving(symbol)
    setMessage(null)
    try {
      await api.removeAlphaSymbol(symbol)
      setMessage(`${symbol} removida da lista Alpha.`)
      await mutate()
    } catch (err) {
      setMessage(err instanceof ApiError && err.detail ? err.detail : "Erro ao remover moeda Alpha.")
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          Erro ao carregar lista Binance Alpha.
        </div>
      )}

      {message && (
        <div role="status" className="rounded-lg border border-[#2a2d3a] bg-[#1a1d27] px-4 py-3 text-sm text-[#d1d5db]">
          {message}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Moedas Binance Alpha</CardTitle>
          <p className="text-sm text-[#6b7280]">
            Cole simbolos no formato do painel ou TradingView. Exemplo: BINANCE:TOSHIUSDT.P vira TOSHIUSDT.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            rows={5}
            placeholder={"BINANCE:TOSHIUSDT.P\nSQDUSDT\nMYXUSDT"}
            className="w-full resize-y rounded-lg border border-[#2a2d3a] bg-[#15171f] px-3 py-2 text-sm text-[#d1d5db] outline-none focus:border-[#6366f1]"
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={handleAdd} disabled={saving || !pending.length}>
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Plus className="h-4 w-4" aria-hidden="true" />
              )}
              Adicionar Alpha
            </Button>
            <span className="text-sm text-[#6b7280]">
              {pending.length ? `${pending.length} simbolo(s) prontos para adicionar` : "Nenhum simbolo pendente"}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Lista atual</CardTitle>
          <p className="text-sm text-[#6b7280]">{data?.count ?? symbols.length} moedas marcadas como Alpha.</p>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading && !symbols.length ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-10 w-full animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
              ))}
            </div>
          ) : !symbols.length ? (
            <p className="p-8 text-center text-sm text-[#6b7280]">Nenhuma moeda Alpha cadastrada.</p>
          ) : (
            <Table aria-label="Moedas Binance Alpha">
              <TableHeader>
                <TableRow>
                  <TableHead>Simbolo</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead>Origem</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {symbols.map((item) => (
                  <TableRow key={item.symbol}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold">{item.symbol}</span>
                        <AlphaBadge isAlpha />
                      </div>
                    </TableCell>
                    <TableCell className="font-semibold text-[#f3f4f6]">{item.asset}</TableCell>
                    <TableCell className="text-sm text-[#6b7280]">{item.source ?? "-"}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleRemove(item.symbol)}
                        disabled={removing === item.symbol}
                        aria-label={`Remover ${item.symbol} da lista Alpha`}
                      >
                        {removing === item.symbol ? (
                          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                        ) : (
                          <Trash2 className="h-4 w-4 text-red-400" aria-hidden="true" />
                        )}
                      </Button>
                    </TableCell>
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
