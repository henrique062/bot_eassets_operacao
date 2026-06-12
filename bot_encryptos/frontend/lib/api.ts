import type {
  ActiveBotSession,
  BtcStatus,
  BotConfig,
  Position,
  SessionStatus,
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
  listActiveSessions: () => apiFetch<ActiveBotSession[]>("/api/eassets/bot/status"),
  getBotStatus: (configId: number) => apiFetch<SessionStatus>(`/api/eassets/bot/status/${configId}`),
  startBot: (config: BotConfig) =>
    apiFetch("/api/eassets/bot/start", { method: "POST", body: JSON.stringify(config) }),
  stopBot: (configId: number) =>
    apiFetch(`/api/eassets/bot/stop/${configId}`, { method: "POST" }),

  getPositions: (configId: number) =>
    apiFetch<Position[]>(`/api/eassets/positions?config_id=${configId}`),
  getTrades: (configId: number, skip = 0, limit = 50) =>
    apiFetch<Trade[]>(`/api/eassets/trades?config_id=${configId}&skip=${skip}&limit=${limit}`),
  getTradesBySymbol: (symbol: string) =>
    apiFetch<Trade[]>(`/api/eassets/trades/${symbol}`),

  getSignals: () => apiFetch<SignalData[]>("/api/eassets/market/signals"),
  getBtcStatus: async () => {
    const data = await apiFetch<Record<string, number | boolean | null> | null>(
      "/api/eassets/market/btc-status"
    )

    const status: BtcStatus = {
      rsi_30m: typeof data?.rsi_30m === "number" ? data.rsi_30m : null,
      rsi_1h: typeof data?.rsi_1h === "number" ? data.rsi_1h : null,
      is_reset: Boolean(data?.is_reset),
    }

    return status
  },

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
