use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Configuração central do bot, espelhando eassets_bot_config no PostgreSQL.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotConfig {
    pub config_id: i32,
    pub config_name: String,

    // Capital e risco
    pub capital_per_trade: f64,
    pub leverage: i32,
    pub max_positions: i32,
    pub stop_loss_pct: f64,
    pub take_profit_pct: f64,
    pub trailing_stop_pct: f64,
    pub trailing_start_pct: f64,

    // Filtros de entrada
    pub min_tpm: f64,
    pub max_lsr: f64,
    pub max_rsi_btc: f64,
    pub min_score: f64,

    // PCL (Position-Cooldown-Loop)
    pub pcl_enabled: bool,
    pub pcl_cooldown_minutes: i32,
    pub pcl_max_attempts: i32,
    pub pcl_min_struct_score: i32,

    // Universo de símbolos (preenchido via env var BYBIT_SYMBOLS)
    pub symbols: Vec<String>,
}

impl BotConfig {
    /// Lê configuração a partir de variáveis de ambiente.
    pub fn from_env() -> Result<Self> {
        dotenvy::dotenv().ok();

        let symbols_raw =
            std::env::var("BYBIT_SYMBOLS").unwrap_or_else(|_| "BTCUSDT,ETHUSDT,SOLUSDT".into());
        let symbols = symbols_raw
            .split(',')
            .map(|s| s.trim().to_uppercase())
            .filter(|s| !s.is_empty())
            .collect();

        Ok(BotConfig {
            config_id: parse_env("BOT_CONFIG_ID", 1),
            config_name: std::env::var("BOT_CONFIG_NAME")
                .unwrap_or_else(|_| "default".into()),
            capital_per_trade: parse_env("CAPITAL_PER_TRADE", 100.0),
            leverage: parse_env("LEVERAGE", 10),
            max_positions: parse_env("MAX_POSITIONS", 3),
            stop_loss_pct: parse_env("STOP_LOSS_PCT", 2.0),
            take_profit_pct: parse_env("TAKE_PROFIT_PCT", 4.0),
            trailing_stop_pct: parse_env("TRAILING_STOP_PCT", 1.5),
            trailing_start_pct: parse_env("TRAILING_START_PCT", 2.0),
            min_tpm: parse_env("MIN_TPM", 800.0),
            max_lsr: parse_env("MAX_LSR", 1.0),
            max_rsi_btc: parse_env("MAX_RSI_BTC", 40.0),
            min_score: parse_env("MIN_SCORE", 60.0),
            pcl_enabled: parse_env("PCL_ENABLED", true),
            pcl_cooldown_minutes: parse_env("PCL_COOLDOWN_MINUTES", 30),
            pcl_max_attempts: parse_env("PCL_MAX_ATTEMPTS", 3),
            pcl_min_struct_score: parse_env("PCL_MIN_STRUCT_SCORE", 3),
            symbols,
        })
    }
}

fn parse_env<T: std::str::FromStr>(key: &str, default: T) -> T {
    std::env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

// ---------------------------------------------------------------------------
// Estado de execução do engine
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum EngineStatus {
    Stopped,
    Running,
    Paused,
}

impl Default for EngineStatus {
    fn default() -> Self {
        EngineStatus::Stopped
    }
}

#[derive(Debug, Default)]
pub struct EngineState {
    pub status: EngineStatus,
    pub open_positions: usize,
    pub last_decision_at: Option<chrono::DateTime<chrono::Utc>>,
}

// ---------------------------------------------------------------------------
// AppState — compartilhado via Arc entre todas as tasks/handlers Axum
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<RwLock<BotConfig>>,
    pub engine: Arc<RwLock<EngineState>>,
    pub db: PgPool,
    /// Sinaliza ao decision loop que deve parar (true = parar)
    pub shutdown: Arc<tokio::sync::watch::Sender<bool>>,
    pub shutdown_rx: Arc<tokio::sync::watch::Receiver<bool>>,
}

impl AppState {
    pub fn new(config: BotConfig, db: PgPool) -> Self {
        let (tx, rx) = tokio::sync::watch::channel(false);
        AppState {
            config: Arc::new(RwLock::new(config)),
            engine: Arc::new(RwLock::new(EngineState::default())),
            db,
            shutdown: Arc::new(tx),
            shutdown_rx: Arc::new(rx),
        }
    }

    pub async fn get_config(&self) -> BotConfig {
        self.config.read().await.clone()
    }

    pub async fn update_config(&self, new_config: BotConfig) {
        let mut w = self.config.write().await;
        *w = new_config;
    }

    pub async fn open_positions_count(&self) -> usize {
        self.engine.read().await.open_positions
    }
}

/// URL do servidor Python para notificações internas
pub fn python_api_url() -> String {
    std::env::var("PYTHON_API_URL")
        .unwrap_or_else(|_| "http://python_api:8000".into())
}

/// Porta do servidor Axum
pub fn rust_core_port() -> u16 {
    std::env::var("RUST_CORE_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(8001)
}
