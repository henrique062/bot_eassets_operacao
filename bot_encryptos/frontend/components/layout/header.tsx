"use client"

import { usePathname } from "next/navigation"
import { Flame } from "lucide-react"

const pageTitles: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/positions": "Posições Abertas",
  "/trades": "Histórico de Trades",
  "/signals": "Sinais de Mercado",
  "/watchlist": "Watchlist PCL",
  "/scraper": "eAssets Scraper",
  "/config": "Configuração",
}

export function Header() {
  const pathname = usePathname()
  const title = pageTitles[pathname] ?? "Phoenix Bot"

  return (
    <header className="h-14 border-b border-[#2a2d3a] flex items-center justify-between px-5 bg-[#0f1117]">
      <div className="flex items-center gap-3">
        <div className="flex md:hidden items-center gap-2">
          <Flame className="h-5 w-5 text-[#6366f1]" aria-hidden="true" />
          <span className="text-sm font-bold text-white tracking-widest">PHOENIX</span>
        </div>
        <h1 className="text-sm font-semibold text-white">{title}</h1>
      </div>
      <span className="text-xs text-[#6b7280]">bot_encryptos</span>
    </header>
  )
}
