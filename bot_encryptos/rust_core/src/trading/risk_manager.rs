use crate::config::AppState;
use crate::market::bybit_rest::BybitRestClient;
use crate::trading::bybit_executor::BybitExecutor;
use crate::trading::position_manager::{Position, PositionManager};
use crate::trading::watchlist_manager::WatchlistManager;
use anyhow::Result;
use std::sync::Arc;
use std::time::Duration;
use tracing::{info, warn};

const CHECK_INTERVAL_MS: u64 = 1000;

/// Inicia uma task de monitoramento de risco para uma posição específica.
pub fn spawn_for_position(
    position: Position,
    app_state: Arc<AppState>,
    rest: Arc<BybitRestClient>,
    executor: Arc<BybitExecutor>,
    pos_manager: Arc<PositionManager>,
    watchlist_manager: Arc<WatchlistManager>,
) {
    let symbol = position.symbol.clone();
    tokio::spawn(async move {
        info!("RiskManager iniciado para {}", symbol);
        let mut interval = tokio::time::interval(Duration::from_millis(CHECK_INTERVAL_MS));

        loop {
            interval.tick().await;

            // Verifica se posição ainda existe
            let pos = match pos_manager.get(&symbol) {
                Some(p) => p,
                None => {
                    info!("RiskManager: posição {} removida, encerrando task", symbol);
                    break;
                }
            };

            // Obtém preço atual
            let tickers = match rest.get_tickers().await {
                Ok(t) => t,
                Err(e) => {
                    warn!("RiskManager {}: falha ao obter ticker: {:#}", symbol, e);
                    continue;
                }
            };

            let current_price = tickers
                .iter()
                .find(|t| t.symbol == symbol)
                .and_then(|t| t.last_price.parse::<f64>().ok())
                .unwrap_or(0.0);

            if current_price == 0.0 {
                continue;
            }

            // Atualiza pico para trailing stop
            pos_manager.update_peak(&symbol, current_price);

            // Re-obtém posição com pico atualizado
            let pos = match pos_manager.get(&symbol) {
                Some(p) => p,
                None => break,
            };

            // Determina o lado oposto para fechar
            let close_side = if pos.side == "Buy" { "Sell" } else { "Buy" };

            // Verificação de STOP LOSS
            let hit_sl = match pos.side.as_str() {
                "Buy" => current_price <= pos.stop_loss,
                "Sell" => current_price >= pos.stop_loss,
                _ => false,
            };

            if hit_sl {
                info!(
                    "STOP LOSS atingido: {} @ {:.4} (sl={:.4})",
                    symbol, current_price, pos.stop_loss
                );
                close_and_handle(
                    &pos,
                    current_price,
                    close_side,
                    "stop_loss",
                    &executor,
                    &pos_manager,
                    &watchlist_manager,
                    &app_state,
                )
                .await;
                break;
            }

            // Verificação de TAKE PROFIT
            let hit_tp = match pos.side.as_str() {
                "Buy" => current_price >= pos.take_profit,
                "Sell" => current_price <= pos.take_profit,
                _ => false,
            };

            if hit_tp {
                info!(
                    "TAKE PROFIT atingido: {} @ {:.4} (tp={:.4})",
                    symbol, current_price, pos.take_profit
                );
                close_and_handle(
                    &pos,
                    current_price,
                    close_side,
                    "take_profit",
                    &executor,
                    &pos_manager,
                    &watchlist_manager,
                    &app_state,
                )
                .await;
                break;
            }

            // Verificação de TRAILING STOP
            if pos.trailing_active {
                let ts_price = pos.trailing_stop_price();
                let hit_ts = match pos.side.as_str() {
                    "Buy" => current_price <= ts_price,
                    "Sell" => current_price >= ts_price,
                    _ => false,
                };

                if hit_ts {
                    info!(
                        "TRAILING STOP atingido: {} @ {:.4} (ts={:.4})",
                        symbol, current_price, ts_price
                    );
                    close_and_handle(
                        &pos,
                        current_price,
                        close_side,
                        "trailing_stop",
                        &executor,
                        &pos_manager,
                        &watchlist_manager,
                        &app_state,
                    )
                    .await;
                    break;
                }
            }
        }
    });
}

async fn close_and_handle(
    pos: &Position,
    close_price: f64,
    close_side: &str,
    reason: &str,
    executor: &Arc<BybitExecutor>,
    pos_manager: &Arc<PositionManager>,
    watchlist_manager: &Arc<WatchlistManager>,
    app_state: &Arc<AppState>,
) {
    // Fecha na exchange apenas no modo real (paper é simulado)
    if pos.mode != "paper" {
        if let Err(e) = executor.close_position(&pos.symbol, close_side, pos.qty).await {
            warn!("Falha ao fechar posição {} na exchange: {:#}", pos.symbol, e);
        }
    }

    // Persiste fechamento e remove da memória
    if let Err(e) = pos_manager.close(&pos.symbol, close_price, reason).await {
        warn!("Falha ao fechar posição {} no DB: {:#}", pos.symbol, e);
    }

    // Atualiza contador de posições abertas
    {
        let mut engine = app_state.engine.write().await;
        if engine.open_positions > 0 {
            engine.open_positions -= 1;
        }
    }

    // Se fechou por stop → dispara hook PCL
    if reason == "stop_loss" {
        let config = app_state.get_config().await;
        if config.pcl_enabled {
            watchlist_manager
                .on_stop_triggered(pos.clone(), &config)
                .await;
        }
    }

    // Registra trade completo no banco
    let config = app_state.get_config().await;
    let pnl_pct = pos.pnl_pct(close_price);
    let pnl_usd = pnl_pct * pos.qty * pos.entry_price / 100.0;

    if let Err(e) = crate::db::postgres::insert_trade(
        &app_state.db,
        pos,
        close_price,
        pnl_usd,
        pnl_pct,
        reason,
    )
    .await
    {
        warn!("Falha ao inserir trade no DB: {:#}", e);
    }
}
