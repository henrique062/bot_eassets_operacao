"use client"

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import type { Trade } from "@/lib/types"
import { formatCurrency, formatTimeBRT } from "@/lib/utils"

interface PnlChartProps {
  trades: Trade[]
}

interface ChartPoint {
  date: string
  cumPnl: number
}

function buildChartData(trades: Trade[]): ChartPoint[] {
  const sorted = [...trades]
    .filter((t) => t.close_time)
    .sort((a, b) => new Date(a.close_time!).getTime() - new Date(b.close_time!).getTime())

  let cum = 0
  return sorted.map((t) => {
    cum += t.total_pnl
    return {
      date: formatTimeBRT(t.close_time),
      cumPnl: parseFloat(cum.toFixed(2)),
    }
  })
}

export function PnlChart({ trades }: PnlChartProps) {
  const data = buildChartData(trades)

  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-[#6b7280] text-sm">
        Sem dados de PnL para exibir.
      </div>
    )
  }

  const lastPnl = data[data.length - 1]?.cumPnl ?? 0
  const lineColor = lastPnl >= 0 ? "#22c55e" : "#ef4444"

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
        <XAxis
          dataKey="date"
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#2a2d3a" }}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#2a2d3a" }}
          tickFormatter={(v) => `$${v}`}
        />
        <Tooltip
          contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8 }}
          labelStyle={{ color: "#9ca3af", fontSize: 11 }}
          formatter={(value: number) => [formatCurrency(value), "PnL Acumulado"]}
        />
        <Line
          type="monotone"
          dataKey="cumPnl"
          stroke={lineColor}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: lineColor }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
