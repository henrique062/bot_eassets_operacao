import type {
  ActiveBotSession,
  BtcStatus,
  BotConfig,
  BybitBalance,
  Position,
  SessionStatus,
  Trade,
  SignalData,
  WatchlistEntry,
  ScraperStatus,
} from "./types"

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? ""

export class ApiError extends Error {
  status: number
  detail?: string

  constructor(status: number, detail?: string) {
    super(detail ? `HTTP ${status}: ${detail}` : `HTTP ${status}`)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!res.ok) {
    let detail: string | undefined
    try {
      const json = await res.json()
      detail =
        typeof json?.detail === "string"
          ? json.detail
          : typeof json?.error === "string"
            ? json.error
            : undefined
    } catch {}

    throw new ApiError(res.status, detail)
  }
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

  getSignals: () => apiFetch<SignalData[]>("/api/eassets/bot/market/signals"),
  getBtcStatus: async () => {
    const data = await apiFetch<Record<string, number | boolean | null> | null>(
      "/api/eassets/bot/market/btc-status"
    )

    const status: BtcStatus = {
      rsi_30m: typeof data?.rsi_30m === "number" ? data.rsi_30m : null,
      rsi_1h: typeof data?.rsi_1h === "number" ? data.rsi_1h : null,
      is_reset: Boolean(data?.is_reset),
    }

    return status
  },

  getWatchlist: (configId: number) =>
    apiFetch<WatchlistEntry[]>(`/api/eassets/watchlist?config_id=${configId}`),
  removeFromWatchlist: (configId: number, symbol: string) =>
    apiFetch(`/api/eassets/watchlist/${configId}/${symbol}`, { method: "DELETE" }),

  getScraperStatus: () => apiFetch<ScraperStatus>("/api/eassets/scraper/status"),
  triggerScrape: () => apiFetch("/api/eassets/scraper/capture", { method: "POST" }),

  getLatestConfig: () => apiFetch<BotConfig | null>("/api/eassets/config/latest"),
  getConfig: (configId: number) =>
    apiFetch<BotConfig>(`/api/eassets/config/${configId}`),
  saveConfig: (config: BotConfig) =>
    apiFetch("/api/eassets/config", { method: "POST", body: JSON.stringify(config) }),
  updateConfig: (configId: number, config: BotConfig) =>
    apiFetch(`/api/eassets/config/${configId}`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  getBybitBalance: () =>
    apiFetch<BybitBalance>("/api/eassets/config/bybit/balance"),
}
