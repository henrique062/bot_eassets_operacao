"use client"

import { useMemo, useId } from "react"
import type { HistoryPoint } from "@/lib/types"

// Gráfico de área do score (0-100) ao longo dos snapshots. SVG responsivo,
// com gradiente, grade horizontal, marcadores de mín/máx e ponto atual.
export function ScoreChart({ points }: { points: HistoryPoint[] }) {
  const gid = useId().replace(/:/g, "")

  const chart = useMemo(() => {
    const W = 960
    const H = 240
    const padL = 36
    const padR = 16
    const padT = 16
    const padB = 28

    const series = points
      .map((p, i) => ({ i, score: p.score, label: p.timestamp_brt }))
      .filter((p): p is { i: number; score: number; label: string } => p.score != null)

    if (series.length < 2) return null

    const innerW = W - padL - padR
    const innerH = H - padT - padB
    const n = series.length
    const x = (i: number) => padL + (innerW * i) / (n - 1)
    const y = (v: number) => padT + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH

    const pts = series.map((s, idx) => ({ x: x(idx), y: y(s.score), v: s.score, label: s.label }))

    const line = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")
    const area =
      `${padL},${padT + innerH} ` +
      pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") +
      ` ${(padL + innerW).toFixed(1)},${padT + innerH}`

    const maxPt = pts.reduce((a, b) => (b.v > a.v ? b : a))
    const minPt = pts.reduce((a, b) => (b.v < a.v ? b : a))
    const lastPt = pts[pts.length - 1]

    const grid = [0, 25, 50, 75, 100].map((v) => ({ v, y: y(v) }))

    // rótulos de tempo: primeiro, meio, último
    const ticks = [0, Math.floor((n - 1) / 2), n - 1].map((idx) => ({
      x: x(idx),
      label: series[idx].label,
    }))

    return { W, H, padL, innerW, padT, innerH, line, area, grid, ticks, maxPt, minPt, lastPt }
  }, [points])

  if (!chart) return <p className="text-sm text-[#6b7280]">Série insuficiente para o gráfico.</p>

  const { W, H, padL, innerW, padT, innerH, line, area, grid, ticks, maxPt, minPt, lastPt } = chart

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="Evolução do score ao longo do tempo">
      <defs>
        <linearGradient id={`fill-${gid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6366f1" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* grade horizontal + rótulos do eixo Y */}
      {grid.map((g) => (
        <g key={g.v}>
          <line x1={padL} y1={g.y} x2={padL + innerW} y2={g.y} stroke="#2a2d3a" strokeWidth={1} strokeDasharray="3 4" />
          <text x={padL - 8} y={g.y + 3} textAnchor="end" fontSize="10" fill="#6b7280">
            {g.v}
          </text>
        </g>
      ))}

      {/* rótulos do eixo X */}
      {ticks.map((t, i) => (
        <text
          key={i}
          x={t.x}
          y={padT + innerH + 18}
          textAnchor={i === 0 ? "start" : i === ticks.length - 1 ? "end" : "middle"}
          fontSize="10"
          fill="#6b7280"
        >
          {t.label}
        </text>
      ))}

      {/* área + linha */}
      <polygon points={area} fill={`url(#fill-${gid})`} />
      <polyline points={line} fill="none" stroke="#818cf8" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

      {/* marcadores mín/máx */}
      <circle cx={maxPt.x} cy={maxPt.y} r={3.5} fill="#4ade80" />
      <text x={maxPt.x} y={maxPt.y - 8} textAnchor="middle" fontSize="10" fontWeight="600" fill="#4ade80">
        {maxPt.v}
      </text>
      <circle cx={minPt.x} cy={minPt.y} r={3.5} fill="#f87171" />
      <text x={minPt.x} y={minPt.y + 16} textAnchor="middle" fontSize="10" fontWeight="600" fill="#f87171">
        {minPt.v}
      </text>

      {/* ponto atual */}
      <circle cx={lastPt.x} cy={lastPt.y} r={4.5} fill="#6366f1" stroke="#0f1117" strokeWidth={2} />
    </svg>
  )
}
