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
  is_alpha: boolean
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

export interface LivePosition {
  id: string
  symbol: string
  is_alpha: boolean
  direction: "LONG" | "SHORT" | string
  side: string
  source: "BOT" | "MANUAL"
  source_config_id: number | null
  bot_position_id: string | null
  entry_price: number
  mark_price: number | null
  liquidation_price: number | null
  size: number
  value: number
  leverage: number | null
  unrealised_pnl: number | null
  pnl_pct: number | null
  open_timestamp: number | null
  updated_at: string | null
}

export interface LivePositionsResponse {
  connected: boolean
  error: string | null
  fetched_at: string | null
  bot_count: number
  manual_count: number
  positions: LivePosition[]
}

export interface Trade {
  id: number
  symbol: string
  is_alpha: boolean
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
  is_alpha: boolean
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
  is_alpha: boolean
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

export interface BybitBalance {
  connected: boolean
  error: string | null
  account_type: string | null
  coin: string
  capital: number | null
  balance: number | null
  equity: number | null
  wallet_balance: number | null
  total_wallet_balance: number | null
  total_available_balance: number | null
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

export interface AlphaSymbol {
  symbol: string
  asset: string
  source: string | null
  created_at: string | null
  updated_at: string | null
}

export interface AlphaSymbolsResponse {
  tag: "alpha"
  count: number
  symbols: AlphaSymbol[]
}

// ---------------------------------------------------------------------------
// Painel de análise manual (metodologia Encryptos)
// ---------------------------------------------------------------------------

export interface PanelSnapshot {
  id: number
  timestamp: string
  timestamp_brt: string
  exchange: string | null
  setup: string | null
  symbols: number | null
  btc_reset: boolean | null
}

export interface BtcMacro {
  state: string
  safe: boolean
  reset: boolean
  rsi_30m: number | null
  rsi_1h: number | null
  rsi_5m: number | null
}

export interface PanelMeta {
  id: number
  timestamp: string
  timestamp_brt: string
  exchange: string | null
  setup: string | null
  symbols: number | null
  btc_reset: boolean | null
}

export interface PanelRow {
  symbol: string
  asset: string
  is_alpha: boolean
  rank: number | null
  score: number | null
  setup: string | null
  price: number | null
  change: number | null
  exp1d: number | null
  exp4h: number | null
  exp1h: number | null
  oitrend: number | null
  lsr: number | null
  lsrtrend: number | null
  rsi4h: number | null
  oiusd: number | null
  trades: number | null
  range4h: number | null
  range1d: number | null
  trades1d: number | null
  toi: number | null
  entry_score: number | null
  entry_grade: string
}

export interface PanelData {
  meta: PanelMeta
  btc: BtcMacro
  rows: PanelRow[]
}

export interface SetupChecklist {
  exp_pos: boolean
  tpm_hot: boolean
  lsr_fuel: boolean
  oi_in: boolean
  rsi_runway: boolean
  accumulation: boolean
  funding_neg: boolean
}

export interface SetupRow {
  symbol: string
  asset: string
  is_alpha: boolean
  rank: number | null
  score: number | null
  setup_grade: string
  setup_cls: string
  setup_score: number
  checklist: SetupChecklist
  trap: boolean
  change: number | null
  lsr: number | null
  oitrend: number | null
}

export interface SetupData {
  meta: PanelMeta
  btc: BtcMacro
  rows: SetupRow[]
}

export interface RadarRow {
  symbol: string
  asset: string
  is_alpha: boolean
  toi: number | null
  oiusd: number | null
  trades1d: number | null
  rank: number | null
  score: number | null
  setup: string | null
  change: number | null
  days_top: number
  total_snaps: number
}

export interface RadarData {
  meta: PanelMeta
  rows: RadarRow[]
}

export interface TopoRow {
  symbol: string
  asset: string
  is_alpha: boolean
  appearances: number
  best_rank: number | null
  avg_rank: number | null
  max_score: number | null
  avg_score: number | null
}

export interface HistoryPoint {
  snapshot_id: number
  timestamp: string
  timestamp_brt: string
  rank: number | null
  score: number | null
  setup: string | null
  price: number | null
  change: number | null
  exp1d: number | null
  exp4h: number | null
  exp1h: number | null
  oitrend: number | null
  lsr: number | null
  lsrtrend: number | null
  rsi4h: number | null
  oiusd: number | null
  toi: number | null
}

export interface SymbolHistory {
  symbol: string
  asset: string
  is_alpha: boolean
  history: HistoryPoint[]
}
