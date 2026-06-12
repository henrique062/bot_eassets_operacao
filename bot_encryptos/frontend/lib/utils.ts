import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number): string {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "USD" })
}

export function formatPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
}

export function formatTimeBRT(iso: string | null | undefined): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function minutesAgo(timestamp: number): string {
  const diff = Math.floor((Date.now() / 1000 - timestamp) / 60)
  if (diff < 1) return "< 1 min"
  if (diff < 60) return `${diff} min`
  const h = Math.floor(diff / 60)
  const m = diff % 60
  return m > 0 ? `${h}h ${m}min` : `${h}h`
}

export function cooldownRemaining(until: string | null): string {
  if (!until) return "—"
  const diff = new Date(until).getTime() - Date.now()
  if (diff <= 0) return "Expirado"
  const m = Math.floor(diff / 60000)
  if (m < 60) return `${m} min`
  return `${Math.floor(m / 60)}h ${m % 60}min`
}
