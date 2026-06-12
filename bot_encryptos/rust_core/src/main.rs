mod config;
mod db;
mod engine;
mod market;
mod trading;

use crate::config::{rust_core_port, AppState, BotConfig, EngineStatus};
use crate::db::postgres;
use crate::market::btc_monitor::BtcMonitor;
use crate::market::bybit_rest::BybitRestClient;
use crate::market::bybit_ws::TradeCounter;
use crate::trading::bybit_executor::BybitExecutor;
use crate::trading::position_manager::PositionManager;
use crate::trading::watchlist_manager::WatchlistManager;

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::info;
use tracing_subscriber::EnvFilter;

// ---------------------------------------------------------------------------
// Entrypoint
// ---------------------------------------------------------------------------

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Logging estruturado
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .json()
        .init();

    dotenvy::dotenv().ok();
    info!("Iniciando rust_core bot_encryptos");

    // Configuração
    let config = BotConfig::from_env()?;
    info!("Símbolos monitorados: {:?}", config.symbols);

    // Pool PostgreSQL
    let db = postgres::create_pool().await?;
    info!("Pool PostgreSQL criado");

    // AppState compartilhado
    let app_state = Arc::new(AppState::new(config.clone(), db.clone()));

    // Serviços compartilhados
    let rest = BybitRestClient::new();
    let ws_counter = TradeCounter::new();
    let executor = BybitExecutor::new_arc();
    let pos_manager = PositionManager::new(db.clone());
    let watchlist_manager = WatchlistManager::new(db.clone(), rest.clone());

    // BTC Monitor
    let (btc_state, btc_monitor) =
        BtcMonitor::new(rest.clone(), config.max_rsi_btc);
    btc_monitor.start();

    // WebSocket Bybit (trades)
    {
        let symbols = config.symbols.clone();
        let counter = ws_counter.clone();
        tokio::spawn(async move {
            market::bybit_ws::run(symbols, counter).await;
        });
    }

    // PCL loop
    {
        let wm = watchlist_manager.clone();
        let cfg_arc = app_state.config.clone();
        wm.start_loop(cfg_arc);
    }

    // Decision loop (inicia somente quando engine for ativado via /internal/start)
    engine::decision::start(
        app_state.clone(),
        rest.clone(),
        ws_counter.clone(),
        btc_state.clone(),
        executor.clone(),
    );

    // Servidor Axum
    let port = rust_core_port();
    let router = build_router(
        app_state.clone(),
        rest.clone(),
        ws_counter.clone(),
        executor.clone(),
        pos_manager.clone(),
        watchlist_manager.clone(),
        btc_state,
    );

    let addr = format!("0.0.0.0:{}", port);
    info!("Servidor Axum ouvindo em {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, router).await?;

    Ok(())
}

// ---------------------------------------------------------------------------
// Contexto compartilhado pelo router Axum
// ---------------------------------------------------------------------------

#[derive(Clone)]
struct RouterState {
    app: Arc<AppState>,
    rest: Arc<BybitRestClient>,
    ws_counter: Arc<TradeCounter>,
    executor: Arc<BybitExecutor>,
    pos_manager: Arc<PositionManager>,
    watchlist_manager: Arc<WatchlistManager>,
    btc_state: Arc<tokio::sync::RwLock<crate::market::BtcState>>,
}

fn build_router(
    app: Arc<AppState>,
    rest: Arc<BybitRestClient>,
    ws_counter: Arc<TradeCounter>,
    executor: Arc<BybitExecutor>,
    pos_manager: Arc<PositionManager>,
    watchlist_manager: Arc<WatchlistManager>,
    btc_state: Arc<tokio::sync::RwLock<crate::market::BtcState>>,
) -> Router {
    let state = RouterState {
        app,
        rest,
        ws_counter,
        executor,
        pos_manager,
        watchlist_manager,
        btc_state,
    };

    Router::new()
        .route("/internal/start", post(handle_start))
        .route("/internal/stop", post(handle_stop))
        .route("/internal/config", post(handle_update_config))
        .route("/internal/status", get(handle_status))
        .route("/internal/snapshot-updated", post(handle_snapshot_updated))
        .with_state(state)
}

// ---------------------------------------------------------------------------
// Handlers internos
// ---------------------------------------------------------------------------

/// POST /internal/start — inicia o engine de decisão
async fn handle_start(State(s): State<RouterState>) -> impl IntoResponse {
    let mut engine = s.app.engine.write().await;
    if engine.status == EngineStatus::Running {
        return (
            StatusCode::CONFLICT,
            Json(serde_json::json!({ "message": "Engine já está rodando" })),
        );
    }
    engine.status = EngineStatus::Running;
    info!("Engine iniciado via /internal/start");
    (
        StatusCode::OK,
        Json(serde_json::json!({ "message": "Engine iniciado" })),
    )
}

/// POST /internal/stop — para o engine de decisão
async fn handle_stop(State(s): State<RouterState>) -> impl IntoResponse {
    let mut engine = s.app.engine.write().await;
    engine.status = EngineStatus::Stopped;
    info!("Engine parado via /internal/stop");
    (
        StatusCode::OK,
        Json(serde_json::json!({ "message": "Engine parado" })),
    )
}

/// POST /internal/config — atualiza configuração em runtime
#[derive(Debug, Deserialize)]
struct UpdateConfigRequest {
    capital_per_trade: Option<f64>,
    leverage: Option<i32>,
    max_positions: Option<i32>,
    stop_loss_pct: Option<f64>,
    take_profit_pct: Option<f64>,
    trailing_stop_pct: Option<f64>,
    trailing_start_pct: Option<f64>,
    min_tpm: Option<f64>,
    max_lsr: Option<f64>,
    max_rsi_btc: Option<f64>,
    min_score: Option<f64>,
    pcl_enabled: Option<bool>,
    pcl_cooldown_minutes: Option<i32>,
    pcl_max_attempts: Option<i32>,
    pcl_min_struct_score: Option<i32>,
}

async fn handle_update_config(
    State(s): State<RouterState>,
    Json(req): Json<UpdateConfigRequest>,
) -> impl IntoResponse {
    let mut config = s.app.config.write().await;

    if let Some(v) = req.capital_per_trade {
        config.capital_per_trade = v;
    }
    if let Some(v) = req.leverage {
        config.leverage = v;
    }
    if let Some(v) = req.max_positions {
        config.max_positions = v;
    }
    if let Some(v) = req.stop_loss_pct {
        config.stop_loss_pct = v;
    }
    if let Some(v) = req.take_profit_pct {
        config.take_profit_pct = v;
    }
    if let Some(v) = req.trailing_stop_pct {
        config.trailing_stop_pct = v;
    }
    if let Some(v) = req.trailing_start_pct {
        config.trailing_start_pct = v;
    }
    if let Some(v) = req.min_tpm {
        config.min_tpm = v;
    }
    if let Some(v) = req.max_lsr {
        config.max_lsr = v;
    }
    if let Some(v) = req.max_rsi_btc {
        config.max_rsi_btc = v;
    }
    if let Some(v) = req.min_score {
        config.min_score = v;
    }
    if let Some(v) = req.pcl_enabled {
        config.pcl_enabled = v;
    }
    if let Some(v) = req.pcl_cooldown_minutes {
        config.pcl_cooldown_minutes = v;
    }
    if let Some(v) = req.pcl_max_attempts {
        config.pcl_max_attempts = v;
    }
    if let Some(v) = req.pcl_min_struct_score {
        config.pcl_min_struct_score = v;
    }

    info!("Configuração atualizada via /internal/config");
    (
        StatusCode::OK,
        Json(serde_json::json!({ "message": "Configuração atualizada" })),
    )
}

/// GET /internal/status — retorna estado atual do engine
#[derive(Serialize)]
struct StatusResponse {
    engine_status: String,
    open_positions: usize,
    last_decision_at: Option<String>,
    btc_rsi_30m: f64,
    btc_rsi_1h: f64,
    btc_is_reset: bool,
    watchlist_count: usize,
}

async fn handle_status(State(s): State<RouterState>) -> impl IntoResponse {
    let engine = s.app.engine.read().await;
    let btc = s.btc_state.read().await;
    let wl_count = s.watchlist_manager.get_all().len();

    let resp = StatusResponse {
        engine_status: format!("{:?}", engine.status),
        open_positions: engine.open_positions,
        last_decision_at: engine
            .last_decision_at
            .map(|dt| dt.to_rfc3339()),
        btc_rsi_30m: btc.rsi_30m,
        btc_rsi_1h: btc.rsi_1h,
        btc_is_reset: btc.is_reset,
        watchlist_count: wl_count,
    };

    (StatusCode::OK, Json(resp))
}

/// POST /internal/snapshot-updated — notifica que novo snapshot eAssets está disponível.
/// O engine usa este hook para forçar uma reavaliação imediata dos sinais.
async fn handle_snapshot_updated(State(s): State<RouterState>) -> impl IntoResponse {
    info!("Snapshot eAssets atualizado, reavaliando sinais...");
    // O decision loop já roda a cada 2s; este endpoint pode ser usado para
    // forçar uma execução imediata se implementado com um channel no futuro.
    // Por ora retorna 200 e o loop natural processará na próxima iteração.
    (
        StatusCode::OK,
        Json(serde_json::json!({ "message": "Snapshot recebido, engine reavaliará na próxima iteração" })),
    )
}
