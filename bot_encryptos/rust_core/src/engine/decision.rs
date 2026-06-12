use crate::config::AppState;
use crate::engine::scorer::{score, SymbolSignals};
use crate::engine::signal_filter::check_all;
use crate::market::bybit_rest::{calc_exp_btc, calc_oi_trend, BybitRestClient};
use crate::market::bybit_ws::TradeCounter;
use crate::market::BtcState;
use crate::trading::bybit_executor::BybitExecutor;
use std::collections::VecDeque;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

const DECISION_INTERVAL_MS: u64 = 2000;
const OI_HISTORY_SIZE: usize = 10;
const LSR_HISTORY_SIZE: usize = 5;

/// Inicia o loop principal de decisão em background.
/// Roda a cada ~2s para cada símbolo monitorado.
pub fn start(
    state: Arc<AppState>,
    rest: Arc<BybitRestClient>,
    ws_counter: Arc<TradeCounter>,
    btc_state: Arc<RwLock<BtcState>>,
    executor: Arc<BybitExecutor>,
) {
    tokio::spawn(async move {
        info!("Decision loop iniciado");
        let mut shutdown_rx = (*state.shutdown_rx).clone();

        // Histórico de OI e LSR por símbolo para calcular tendências
        let oi_history: dashmap::DashMap<String, VecDeque<f64>> = dashmap::DashMap::new();
        let lsr_history: dashmap::DashMap<String, VecDeque<f64>> = dashmap::DashMap::new();

        loop {
            tokio::select! {
                _ = shutdown_rx.changed() => {
                    if *shutdown_rx.borrow() {
                        info!("Decision loop encerrando por sinal de shutdown");
                        break;
                    }
                }
                _ = tokio::time::sleep(Duration::from_millis(DECISION_INTERVAL_MS)) => {
                    let cfg = state.get_config().await;

                    // Verifica status do engine
                    {
                        let engine = state.engine.read().await;
                        if engine.status != crate::config::EngineStatus::Running {
                            continue;
                        }
                    }

                    let btc = btc_state.read().await.clone();
                    let open_positions = state.open_positions_count().await;

                    // Obtém preços atuais uma vez para todos os símbolos
                    let tickers = match rest.get_tickers().await {
                        Ok(t) => t,
                        Err(e) => {
                            warn!("Falha ao obter tickers: {:#}", e);
                            continue;
                        }
                    };

                    for symbol in &cfg.symbols {
                        // Obtém preço atual
                        let price = tickers
                            .iter()
                            .find(|t| &t.symbol == symbol)
                            .and_then(|t| t.last_price.parse::<f64>().ok())
                            .unwrap_or(0.0);

                        if price == 0.0 {
                            continue;
                        }

                        // Coleta sinais assincronamente
                        let signals = match collect_signals(
                            symbol,
                            price,
                            &rest,
                            &ws_counter,
                            &oi_history,
                            &lsr_history,
                        )
                        .await
                        {
                            Ok(s) => s,
                            Err(e) => {
                                warn!("Falha ao coletar sinais para {}: {:#}", symbol, e);
                                continue;
                            }
                        };

                        // Aplica checklist dos 6 filtros
                        let filter = check_all(&signals, &cfg, &btc, open_positions);
                        if !filter.passed {
                            debug!(
                                "{} filtrado: {:?}",
                                symbol,
                                filter.failed_reasons.first()
                            );
                            continue;
                        }

                        // Calcula score
                        let s = score(&signals);
                        info!("{} passou filtros, score={:.1}", symbol, s);

                        if s < cfg.min_score {
                            debug!("{} score {:.1} < min_score {:.1}", symbol, s, cfg.min_score);
                            continue;
                        }

                        // Abre posição
                        info!("{} abrindo posição LONG (score={:.1})", symbol, s);
                        let size = cfg.capital_per_trade * cfg.leverage as f64 / price;
                        match executor
                            .open_position(symbol, "Buy", size, &cfg)
                            .await
                        {
                            Ok(result) => {
                                info!(
                                    "Posição aberta: {} orderId={}",
                                    symbol, result.order_id
                                );
                                // Atualiza contador de posições abertas
                                let mut engine = state.engine.write().await;
                                engine.open_positions += 1;
                                engine.last_decision_at = Some(chrono::Utc::now());
                            }
                            Err(e) => {
                                warn!("Falha ao abrir posição em {}: {:#}", symbol, e);
                            }
                        }
                    }
                }
            }
        }
    });
}

/// Coleta todos os sinais necessários para scoring de um símbolo.
async fn collect_signals(
    symbol: &str,
    price: f64,
    rest: &Arc<BybitRestClient>,
    ws_counter: &Arc<TradeCounter>,
    oi_history: &dashmap::DashMap<String, VecDeque<f64>>,
    lsr_history: &dashmap::DashMap<String, VecDeque<f64>>,
) -> anyhow::Result<SymbolSignals> {
    // Klines para exp_btc em diferentes TFs
    let (klines_5m, klines_15m, klines_1h, klines_1d, klines_4h) = tokio::join!(
        rest.get_klines(symbol, "5", 10),
        rest.get_klines(symbol, "15", 10),
        rest.get_klines(symbol, "60", 10),
        rest.get_klines(symbol, "D", 10),
        rest.get_klines(symbol, "240", 20),
    );

    let exp_btc_5m = klines_5m.as_ref().map(|k| calc_exp_btc(k)).unwrap_or(0.0);
    let exp_btc_15m = klines_15m.as_ref().map(|k| calc_exp_btc(k)).unwrap_or(0.0);
    let exp_btc_1h = klines_1h.as_ref().map(|k| calc_exp_btc(k)).unwrap_or(0.0);
    let exp_btc_1d = klines_1d.as_ref().map(|k| calc_exp_btc(k)).unwrap_or(0.0);

    // RSI 4h
    let rsi_4h = klines_4h
        .as_ref()
        .map(|k| {
            let closes: Vec<f64> = k.iter().map(|c| c.close).collect();
            crate::market::btc_monitor::calc_rsi(&closes, 14)
        })
        .unwrap_or(50.0);

    // Trades por minuto via WS
    let trades_min = ws_counter.get_trades_per_min(symbol);

    // Open Interest
    let oi_current = rest.get_open_interest(symbol).await.unwrap_or(0.0);

    // Atualiza histórico de OI
    let oi_trend = {
        let mut hist = oi_history
            .entry(symbol.to_string())
            .or_insert_with(|| VecDeque::with_capacity(OI_HISTORY_SIZE + 1));
        hist.push_back(oi_current);
        if hist.len() > OI_HISTORY_SIZE {
            hist.pop_front();
        }
        let slice: Vec<f64> = hist.iter().copied().collect();
        calc_oi_trend(&slice)
    };

    // Long/Short Ratio
    let (long_r, short_r) = rest
        .get_long_short_ratio(symbol, "5min")
        .await
        .unwrap_or((0.5, 0.5));
    let lsr = if short_r > 0.0 { long_r / short_r } else { 1.0 };

    // Tendência do LSR
    let lsr_trend = {
        let mut hist = lsr_history
            .entry(symbol.to_string())
            .or_insert_with(|| VecDeque::with_capacity(LSR_HISTORY_SIZE + 1));
        hist.push_back(lsr);
        if hist.len() > LSR_HISTORY_SIZE {
            hist.pop_front();
        }
        if hist.len() >= 2 {
            hist.back().unwrap() - hist.front().unwrap()
        } else {
            0.0
        }
    };

    // range_level: derivado da amplitude dos candles 4h (simplificado)
    let range_level = estimate_range_level(
        klines_4h.as_deref().unwrap_or(&[]),
    );

    Ok(SymbolSignals {
        symbol: symbol.to_string(),
        price,
        exp_btc_5m,
        exp_btc_15m,
        exp_btc_1h,
        exp_btc_1d,
        trades_min,
        oi_trend,
        lsr,
        lsr_trend,
        range_level,
        range_level_4h: range_level,
        range_level_1d: 0.0, // preenchido com klines D quando necessário
        rsi_4h,
        toi: oi_current,
    })
}

/// Estima nível de range (0-5) baseado na amplitude relativa dos candles.
fn estimate_range_level(klines: &[crate::market::bybit_rest::KlineData]) -> f64 {
    if klines.is_empty() {
        return 0.0;
    }
    let ranges: Vec<f64> = klines
        .iter()
        .filter(|k| k.low > 0.0)
        .map(|k| (k.high - k.low) / k.low * 100.0)
        .collect();

    if ranges.is_empty() {
        return 0.0;
    }

    let avg_range: f64 = ranges.iter().sum::<f64>() / ranges.len() as f64;

    // Escala heurística: amplitude média de candle 4h
    // < 0.5% → 1, < 1% → 2, < 2% → 3, < 3% → 4, >= 3% → 5
    if avg_range < 0.5 {
        1.0
    } else if avg_range < 1.0 {
        2.0
    } else if avg_range < 2.0 {
        3.0
    } else if avg_range < 3.0 {
        4.0
    } else {
        5.0
    }
}
