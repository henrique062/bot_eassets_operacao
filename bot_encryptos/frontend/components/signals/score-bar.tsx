import { cn } from "@/lib/utils"

interface ScoreBarProps {
  score: number
}

export function ScoreBar({ score }: ScoreBarProps) {
  const pct = Math.min(100, Math.max(0, score))
  const color =
    pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500"

  return (
    <div className="flex items-center gap-2" aria-label={`Score: ${score}`}>
      <div className="h-2 w-24 rounded-full bg-[#2a2d3a] overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-white w-8">{score.toFixed(0)}</span>
    </div>
  )
}
