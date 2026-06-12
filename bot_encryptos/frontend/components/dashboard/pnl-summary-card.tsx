import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { formatCurrency } from "@/lib/utils"
import type { Trade } from "@/lib/types"
import { cn } from "@/lib/utils"

interface PnlSummaryCardProps {
  trades: Trade[] | undefined
}

function getTodayPnl(trades: Trade[]): number {
  const today = new Date().toDateString()
  return trades
    .filter((t) => t.close_time && new Date(t.close_time).toDateString() === today)
    .reduce((sum, t) => sum + t.total_pnl, 0)
}

export function PnlSummaryCard({ trades }: PnlSummaryCardProps) {
  const todayPnl = trades ? getTodayPnl(trades) : null

  return (
    <Card>
      <CardHeader>
        <CardTitle>PnL Hoje</CardTitle>
      </CardHeader>
      <CardContent>
        {todayPnl !== null ? (
          <p
            className={cn(
              "text-2xl font-bold font-mono",
              todayPnl >= 0 ? "text-green-400" : "text-red-400"
            )}
            aria-label={`PnL hoje: ${formatCurrency(todayPnl)}`}
          >
            {formatCurrency(todayPnl)}
          </p>
        ) : (
          <div className="h-8 w-36 animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
        )}
      </CardContent>
    </Card>
  )
}
