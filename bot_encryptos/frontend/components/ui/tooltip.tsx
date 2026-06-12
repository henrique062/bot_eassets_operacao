"use client"

import { useState, useId } from "react"
import { HelpCircle } from "lucide-react"

// Tooltip simples e acessível: ícone de ajuda que revela uma explicação ao
// passar o mouse ou focar via teclado. Tema escuro.
export function InfoTooltip({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const id = useId()

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label="Ajuda"
        aria-describedby={open ? id : undefined}
        className="text-[#6b7280] transition-colors hover:text-[#818cf8] focus:text-[#818cf8] focus:outline-none"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        <HelpCircle className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2 rounded-lg border border-[#2a2d3a] bg-[#0f1117] px-3 py-2 text-xs leading-relaxed text-[#d1d5db] shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  )
}
