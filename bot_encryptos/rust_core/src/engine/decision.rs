use crate::config::{python_api_url, AppState, EngineStatus};
use crate::market::bybit_rest::BybitRestClient;
use crate::trading::bybit_executor::BybitExecutor;
use crate::trading::position_manager::{Position, PositionManager};
use crate::trading::risk_manager;
use crate::trading::watchlist_manager::WatchlistManager;
use serde::Deserialize;
use std::sync::Arc;
use std::time::Duration;
use tracing::{info, warn};

// Intervalo do loop de decisão. O snapshot eAssets muda a cada ~30min, então
// não há necessidade de polling agressivo — 15s é folgado e reativo.
const DECISION_INTERVAL_MS: u64 = 15_000;

// ---------------------------------------------------------------------------
// Resposta do endpoint /api/eassets/panel/entry-candidates (python_api)
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct CandidatesEnvelope {
    data: CandidatesData,
}

#[derive(Debug, Deserialize)]
struct CandidatesData {
    btc_safe: bool,
    #[serde(default)]
    btc_state: Option<String>,
    #[serde(default)]
    candidates: Vec<Candidate>,
}

#[derive(Debug, Deserialize, Clone)]
struct Candidate {
    symbol: String,
    #[serde(default)]
    score: Option<f64>,
    #[serde(default)]
    entry_score: Option<i64>,
    #[serde(default)]
    grade: Option<String>,
}

/// Inicia o loop de decisão.
///
/// A partir da metodologia Encryptos, a decisão de QUAIS moedas operar vem do
/// painel (snapshot eAssets), não de um score próprio. O motor consome o
/// endpoint `entry-candidates` (já filtrado por gate macro do BTC + Setup de
/// Ouro) e executa LONG na Bybit, respeitando capital, alavancagem e limite de
/// posições. SL/TP/trailing e PCL ficam a cargo do `risk_manager`.
pub fn start(
    state: Arc<AppState>,
    rest: Arc<BybitRestClient>,
    executor: Arc<BybitExecutor>,
    pos_manager: Arc<PositionManager>,
    watchlist_manager: Arc<WatchlistManager>,
) {
    tokio::spawn(async move {
        info!("Decision loop iniciado (fonte: ranking do Painel de Moedas)");
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(10))
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());
        let mut shutdown_rx = (*state.shutdown_rx).clone();

        loop {
            tokio::select! {
                _ = shutdown_rx.changed() => {
                    if *shutdown_rx.borrow() {
                        info!("Decision loop encerrando por sinal de shutdown");
                        break;
                    }
                }
                _ = tokio::time::sleep(Duration::from_millis(DECISION_INTERVAL_MS)) => {
                    // Só age quando o engine está Running (ativado via /internal/start)
                    {
                        let engine = state.engine.read().await;
                        if engine.status != EngineStatus::Running {
                            continue;
                        }
                    }

                    let cfg = state.get_config().await;

                    // 1. Busca candidatos no painel (já passa pelo gate do BTC)
                    let url = format!(
                        "{}/api/eassets/panel/entry-candidates?min_score={}",
                        python_api_url(),
                        cfg.min_score
                    );
                    let data = match http.get(&url).send().await {
                        Ok(resp) => match resp.json::<CandidatesEnvelope>().await {
                            Ok(env) => env.data,
                            Err(e) => {
                                warn!("Falha ao decodificar candidatos do painel: {:#}", e);
                                continue;
                            }
                        },
                        Err(e) => {
                            warn!("Falha ao consultar candidatos do painel: {:#}", e);
                            continue;
                        }
                    };

                    if !data.btc_safe {
                        info!(
                            "BTC sem janela ({}) — nenhuma entrada permitida",
                            data.btc_state.as_deref().unwrap_or("—")
                        );
                        continue;
                    }
                    if data.candidates.is_empty() {
                        continue;
                    }

                    // 2. Executa entradas respeitando limite de posições
                    for cand in &data.candidates {
                        if pos_manager.count() >= cfg.max_positions as usize {
                            break;
                        }
                        // Já existe posição aberta para esse símbolo?
                        if pos_manager.get(&cand.symbol).is_some() {
                            continue;
                        }

                        // Preço atual na Bybit (também valida que o símbolo existe lá)
                        let price = match current_price(&rest, &cand.symbol).await {
                            Some(p) if p > 0.0 => p,
                            _ => {
                                warn!(
                                    "{} sem preço na Bybit (símbolo pode não existir lá) — pulando",
                                    cand.symbol
                                );
                                continue;
                            }
                        };

                        open_long(
                            cand,
                            price,
                            &cfg,
                            &state,
                            &rest,
                            &executor,
                            &pos_manager,
                            &watchlist_manager,
                        )
                        .await;
                    }

                    // Mantém o contador do engine em sincronia com as posições reais
                    {
                        let mut engine = state.engine.write().await;
                        engine.open_positions = pos_manager.count();
                    }
                }
            }
        }
    });
}

/// Abre uma posição LONG e liga o monitoramento de risco.
#[allow(clippy::too_many_arguments)]
async fn open_long(
    cand: &Candidate,
    price: f64,
    cfg: &crate::config::BotConfig,
    state: &Arc<AppState>,
    rest: &Arc<BybitRestClient>,
    executor: &Arc<BybitExecutor>,
    pos_manager: &Arc<PositionManager>,
    watchlist_manager: &Arc<WatchlistManager>,
) {
    let qty = cfg.capital_per_trade * cfg.leverage as f64 / price;
    if qty <= 0.0 {
        return;
    }

    let mode = if cfg.paper_trading { "paper" } else { "live" };
    info!(
        "Entrada {} (grau={} score={:.0}) [{}] — LONG qty={:.4} @ {:.6}",
        cand.symbol,
        cand.grade.as_deref().unwrap_or("—"),
        cand.score.unwrap_or(0.0),
        mode,
        qty,
        price
    );

    // Stop loss / take profit a partir do preço de referência
    let stop_loss = if cfg.stop_loss_pct > 0.0 {
        price * (1.0 - cfg.stop_loss_pct / 100.0)
    } else {
        0.0
    };
    let take_profit = if cfg.take_profit_pct > 0.0 {
        price * (1.0 + cfg.take_profit_pct / 100.0)
    } else {
        0.0
    };

    // No modo paper, simulamos o fill (sem tocar na Bybit). No modo real,
    // enviamos a ordem de mercado e o TP/SL para a exchange.
    let order_id = if cfg.paper_trading {
        format!("PAPER-{}", uuid::Uuid::new_v4())
    } else {
        match executor.open_position(&cand.symbol, "Buy", qty, cfg).await {
            Ok(o) => o.order_id,
            Err(e) => {
                warn!("Falha ao abrir posição em {}: {:#}", cand.symbol, e);
                return;
            }
        }
    };

    let mut position = Position::new(
        cfg.config_id,
        &cand.symbol,
        "Buy",
        qty,
        price,
        cand.score.unwrap_or(0.0),
        stop_loss,
        take_profit,
        cfg.trailing_stop_pct,
        cfg.trailing_start_pct,
        &order_id,
    );
    position.mode = mode.to_string();

    if let Err(e) = pos_manager.add(position.clone()).await {
        warn!("Falha ao persistir posição {}: {:#}", cand.symbol, e);
    }

    // Define TP/SL na exchange apenas no modo real
    if !cfg.paper_trading && (stop_loss > 0.0 || take_profit > 0.0) {
        if let Err(e) = executor
            .set_tp_sl(&cand.symbol, take_profit, stop_loss, 0)
            .await
        {
            warn!("Falha ao definir TP/SL de {} na Bybit: {:#}", cand.symbol, e);
        }
    }

    // Liga o monitoramento de risco (SL/TP/trailing + hook PCL no stop)
    risk_manager::spawn_for_position(
        position,
        state.clone(),
        rest.clone(),
        executor.clone(),
        pos_manager.clone(),
        watchlist_manager.clone(),
    );

    // Atualiza timestamp da última decisão
    let mut engine = state.engine.write().await;
    engine.last_decision_at = Some(chrono::Utc::now());
}

/// Busca o último preço de um símbolo na Bybit. Retorna None se não existir.
async fn current_price(rest: &Arc<BybitRestClient>, symbol: &str) -> Option<f64> {
    let tickers = rest.get_tickers().await.ok()?;
    tickers
        .iter()
        .find(|t| t.symbol == symbol)
        .and_then(|t| t.last_price.parse::<f64>().ok())
}
