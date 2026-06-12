import type {
  BotStatus,
  BotConfig,
  Position,
  Trade,
  SignalData,
  WatchlistEntry,
  ScraperStatus,
} from "./types"

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? ""

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

export const api = {
  getBotStatus: () => apiFetch<BotStatus>("/api/eassets/bot/status"),
  startBot: (config: BotConfig) =>
    apiFetch("/api/eassets/bot/start", { method: "POST", body: JSON.stringify(config) }),
  stopBot: (configId: number) =>
    apiFetch(`/api/eassets/bot/stop/${configId}`, { method: "POST" }),

  getPositions: () => apiFetch<Position[]>("/api/eassets/positions"),
  getTrades: (skip = 0, limit = 50) =>
    apiFetch<Trade[]>(`/api/eassets/trades?skip=${skip}&limit=${limit}`),
  getTradesBySymbol: (symbol: string) =>
    apiFetch<Trade[]>(`/api/eassets/trades/${symbol}`),

  getSignals: () => apiFetch<SignalData[]>("/api/eassets/market/signals"),
  getBtcStatus: () =>
    apiFetch<{ btc_rsi_30m: number; btc_rsi_1h: number; is_reset: boolean }>(
      "/api/eassets/market/btc-status"
    ),

  getWatchlist: () => apiFetch<WatchlistEntry[]>("/api/eassets/watchlist"),
  removeFromWatchlist: (symbol: string) =>
    apiFetch(`/api/eassets/watchlist/${symbol}`, { method: "DELETE" }),

  getScraperStatus: () => apiFetch<ScraperStatus>("/api/eassets/scraper/status"),
  triggerScrape: () => apiFetch("/api/eassets/scraper/capture", { method: "POST" }),

  getConfig: (configId: number) =>
    apiFetch<BotConfig>(`/api/eassets/config/${configId}`),
  saveConfig: (config: BotConfig) =>
    apiFetch("/api/eassets/config", { method: "POST", body: JSON.stringify(config) }),
}
