import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ScoreBar } from "./score-bar"
import type { SignalData } from "@/lib/types"
import { cn } from "@/lib/utils"

interface SignalsTableProps {
  signals: SignalData[] | undefined
}

export function SignalsTable({ signals }: SignalsTableProps) {
  if (!signals) {
    return (
      <div className="space-y-3 p-5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-8 w-full animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
        ))}
      </div>
    )
  }

  if (signals.length === 0) {
    return <p className="p-5 text-sm text-[#6b7280]">Nenhum sinal disponível.</p>
  }

  const sorted = [...signals].sort((a, b) => b.score - a.score)

  return (
    <Table aria-label="Sinais de mercado">
      <TableHeader>
        <TableRow>
          <TableHead>Símbolo</TableHead>
          <TableHead>Score</TableHead>
          <TableHead>Exp BTC 1h</TableHead>
          <TableHead>Exp BTC 1d</TableHead>
          <TableHead>TPM</TableHead>
          <TableHead>OI Trend</TableHead>
          <TableHead>LSR</TableHead>
          <TableHead>Filtros</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((signal) => (
          <TableRow key={signal.symbol}>
            <TableCell className="font-mono font-medium">{signal.symbol}</TableCell>
            <TableCell>
              <ScoreBar score={signal.score} />
            </TableCell>
            <TableCell
              className={cn(
                "font-mono",
                signal.exp_btc_1h >= 0 ? "text-green-400" : "text-red-400"
              )}
            >
              {signal.exp_btc_1h >= 0 ? "+" : ""}
              {signal.exp_btc_1h.toFixed(2)}%
            </TableCell>
            <TableCell
              className={cn(
                "font-mono",
                signal.exp_btc_1d >= 0 ? "text-green-400" : "text-red-400"
              )}
            >
              {signal.exp_btc_1d >= 0 ? "+" : ""}
              {signal.exp_btc_1d.toFixed(2)}%
            </TableCell>
            <TableCell className="font-mono">{signal.trades_min.toFixed(0)}</TableCell>
            <TableCell className="font-mono">{signal.oi_trend.toFixed(2)}</TableCell>
            <TableCell className="font-mono">{signal.lsr.toFixed(2)}</TableCell>
            <TableCell>
              {signal.filter_passed ? (
                <span
                  className="text-green-400 text-base"
                  aria-label="Filtros aprovados"
                  title="Todos os filtros aprovados"
                >
                  ✅
                </span>
              ) : (
                <span
                  className="text-red-400 text-base cursor-help"
                  aria-label={`Filtros reprovados: ${signal.failed_reasons.join(", ")}`}
                  title={signal.failed_reasons.join(" | ")}
                >
                  ❌
                </span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
