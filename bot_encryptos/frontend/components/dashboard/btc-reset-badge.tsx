import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { BotStatus } from "@/lib/types"

interface BtcResetBadgeProps {
  status: BotStatus | undefined
}

export function BtcResetBadge({ status }: BtcResetBadgeProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>BTC Status</CardTitle>
      </CardHeader>
      <CardContent>
        {status ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-[#6b7280]">RSI 30m</span>
              <span className="font-mono text-white">{status.btc_rsi_30m.toFixed(1)}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-[#6b7280]">RSI 1h</span>
              <span className="font-mono text-white">{status.btc_rsi_1h.toFixed(1)}</span>
            </div>
            <div className="pt-1">
              {status.btc_is_reset ? (
                <Badge variant="danger">EM RESET</Badge>
              ) : (
                <Badge variant="success">NORMAL</Badge>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-4 w-full animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
