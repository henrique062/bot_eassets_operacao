import { Badge } from "@/components/ui/badge"

export function AlphaBadge({ isAlpha }: { isAlpha?: boolean | null }) {
  if (!isAlpha) return null

  return (
    <Badge
      variant="outline"
      className="border-[#facc15]/40 bg-[#facc15]/10 px-1.5 py-0 text-[9px] uppercase tracking-wide text-[#facc15]"
    >
      Alpha
    </Badge>
  )
}
