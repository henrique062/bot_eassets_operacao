import type { BtcMacro } from "@/lib/types"
import { fmtNum } from "@/lib/panel-format"

// Banner do gate macro do BTC — define se a janela de entrada está aberta.
export function MacroBanner({ btc }: { btc: BtcMacro | undefined }) {
  if (!btc) {
    return (
      <div className="h-[60px] animate-pulse rounded-xl bg-[#1a1d27]" aria-hidden="true" />
    )
  }

  const safe = btc.safe
  const bg = safe ? "rgba(52,211,153,0.10)" : "rgba(251,191,36,0.10)"
  const border = safe ? "rgba(52,211,153,0.35)" : "rgba(251,191,36,0.35)"
  const stateColor = safe ? "#4ade80" : "#fbbf24"

  return (
    <div
      className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border px-6 py-4"
      style={{ backgroundColor: bg, borderColor: border }}
      role="status"
    >
      <span className="text-sm font-semibold tracking-wide" style={{ color: stateColor }}>
        BTC {btc.state}
      </span>
      <span className="text-sm text-[#9ca3af]">
        RSI 30m {fmtNum(btc.rsi_30m, 1)} · 1h {fmtNum(btc.rsi_1h, 1)} · 5m {fmtNum(btc.rsi_5m, 1)}
      </span>
      <span className="text-sm text-[#d1d5db]">
        {safe
          ? "Janela aberta — caçar Setup de Ouro"
          : "Sem reset — evitar entradas, aguardar"}
      </span>
    </div>
  )
}
