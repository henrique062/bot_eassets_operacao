import type { BtcMacro } from "@/lib/types"
import { fmtNum } from "@/lib/panel-format"

// Banner do gate macro do BTC — define se a janela de entrada está aberta.
export function MacroBanner({ btc }: { btc: BtcMacro | undefined }) {
  if (!btc) {
    return (
      <div className="h-[60px] animate-pulse rounded-2xl bg-[#F2F4F7]" aria-hidden="true" />
    )
  }

  const safe = btc.safe
  const bg = safe ? "#ECFDF3" : "#FFFAEB"
  const border = safe ? "#A6F4C5" : "#FEDF89"
  const stateColor = safe ? "#039855" : "#DC6803"

  return (
    <div
      className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border px-6 py-4"
      style={{ backgroundColor: bg, borderColor: border }}
      role="status"
    >
      <span className="text-sm font-semibold tracking-wide" style={{ color: stateColor }}>
        BTC {btc.state}
      </span>
      <span className="text-sm text-[#667085]">
        RSI 30m {fmtNum(btc.rsi_30m, 1)} · 1h {fmtNum(btc.rsi_1h, 1)} · 5m {fmtNum(btc.rsi_5m, 1)}
      </span>
      <span className="text-sm text-[#475467]">
        {safe
          ? "Janela aberta — caçar Setup de Ouro"
          : "Sem reset — evitar entradas, aguardar"}
      </span>
    </div>
  )
}
