"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { LayoutGrid, Trophy, Radar, Star } from "lucide-react"

const tabs = [
  { href: "/analise", label: "Painel", icon: LayoutGrid },
  { href: "/analise/setup", label: "Setup de Ouro", icon: Trophy },
  { href: "/analise/radar", label: "Radar Acumulação", icon: Radar },
  { href: "/analise/topo", label: "Topo Recorrente", icon: Star },
]

export function PanelTabs() {
  const pathname = usePathname()

  return (
    <nav aria-label="Seções da análise" className="flex flex-wrap gap-2">
      {tabs.map(({ href, label, icon: Icon }) => {
        const active = href === "/analise" ? pathname === "/analise" : pathname.startsWith(href)
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className="flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition-colors"
            style={
              active
                ? { backgroundColor: "#6366f1", borderColor: "#6366f1", color: "#FFFFFF" }
                : { backgroundColor: "#1a1d27", borderColor: "#2a2d3a", color: "#9ca3af" }
            }
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            {label}
          </Link>
        )
      })}
    </nav>
  )
}
