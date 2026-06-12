export interface BotStatus {
  engine_status: "Running" | "Stopped" | "Paused"
  open_positions: number
  last_decision_at: string | null
  btc_rsi_30m: number
  btc_rsi_1h: number
  btc_is_reset: boolean
  watchlist_count: number
}

export interface ActiveBotSession {
  id: number
  session_name: string
  active?: boolean
}

export interface SessionStatus {
  config: BotConfig
  positions: Position[]
  open_positions: number
  unrealised_pnl: number
}

export interface BtcStatus {
  rsi_30m: number | null
  rsi_1h: number | null
  is_reset: boolean
}

export interface Position {
  id: number
  config_id: number
  symbol: string
  direction: "LONG" | "SHORT"
  entry_price: number
  size: number
  value: number
  entry_score: number | null
  entry_tpm: number | null
  entry_lsr: number | null
  open_timestamp: number
  created_at: string
}

export interface Trade {
  id: number
  symbol: string
  direction: "LONG" | "SHORT"
  entry_price: number
  exit_price: number
  size: number
  total_pnl: number
  total_pnl_pct: number
  close_reason: string | null
  open_time: string | null
  close_time: string | null
  entry_score: number | null
  created_at: string
}

export interface SignalData {
  symbol: string
  score: number
  exp_btc_1h: number
  exp_btc_1d: number
  trades_min: number
  oi_trend: number
  lsr: number
  range_level: number
  filter_passed: boolean
  failed_reasons: string[]
}

export interface WatchlistEntry {
  id: number
  symbol: string
  state: "WATCHLIST" | "COOLDOWN" | "CANDIDATE" | "INVALIDATED" | "COMPLETED"
  attempt_count: number
  max_attempts: number
  total_pnl_so_far: number
  cooldown_until: string | null
  last_check_at: string | null
  last_check_passed: boolean | null
  added_at: string
}

export interface ScraperStatus {
  running: boolean
  last_ok: string | null
  last_error: string | null
  next_run_at: string | null
}

export interface BotConfig {
  id?: number
  session_name: string
  capital: number
  balance: number
  leverage: number
  min_tpm: number
  max_lsr: number
  max_rsi_btc: number
  min_score: number
  max_positions: number
  stop_loss_pct: number | null
  take_profit_pct: number | null
  trailing_stop_pct: number | null
  trailing_start_pct: number | null
  pcl_enabled: boolean
  pcl_cooldown_minutes: number
  pcl_max_attempts: number
}

export interface ApiResponse<T> {
  ok: boolean
  data: T
  error?: string
}
