"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Flame,
  LayoutDashboard,
  TrendingUp,
  History,
  Zap,
  Eye,
  RefreshCw,
  Settings,
} from "lucide-react"
import { cn } from "@/lib/utils"

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/positions", label: "Posições", icon: TrendingUp },
  { href: "/trades", label: "Trades", icon: History },
  { href: "/signals", label: "Sinais", icon: Zap },
  { href: "/watchlist", label: "Watchlist", icon: Eye },
  { href: "/scraper", label: "Scraper", icon: RefreshCw },
  { href: "/config", label: "Config", icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="hidden md:flex flex-col w-56 min-h-screen bg-[#1a1d27] border-r border-[#2a2d3a] py-6">
      <div className="flex items-center gap-2 px-5 mb-8">
        <Flame className="h-6 w-6 text-[#6366f1]" aria-hidden="true" />
        <span className="text-lg font-bold text-white tracking-widest">PHOENIX</span>
      </div>

      <nav aria-label="Navegação principal">
        <ul className="flex flex-col gap-1 px-3">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/")
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                    active
                      ? "bg-[#6366f1]/20 text-[#818cf8]"
                      : "text-[#6b7280] hover:bg-[#2a2d3a] hover:text-white"
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {label}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
    </aside>
  )
}
