"use client"

import { useState } from "react"
import { Check, Loader2, Target } from "lucide-react"
import { api } from "@/lib/api"

export function MonitorButton({ symbol }: { symbol: string }) {
  const [state, setState] = useState<"idle" | "loading" | "done">("idle")

  async function mark() {
    if (state !== "idle") return
    setState("loading")
    try {
      await api.monitorSymbol(symbol)
      setState("done")
    } catch {
      setState("idle")
    }
  }

  return (
    <button
      type="button"
      onClick={mark}
      title={state === "done" ? "Monitorando" : "Monitorar esta moeda"}
      aria-label={`Monitorar ${symbol}`}
      className="text-[#6b7280] transition-colors hover:text-[#818cf8]"
    >
      {state === "loading" ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : state === "done" ? (
        <Check className="h-3.5 w-3.5 text-[#4ade80]" />
      ) : (
        <Target className="h-3.5 w-3.5" />
      )}
    </button>
  )
}
