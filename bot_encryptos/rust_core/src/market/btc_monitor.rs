use crate::market::bybit_rest::BybitRestClient;
use anyhow::Result;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;
use tracing::{error, info};

const BTC_SYMBOL: &str = "BTCUSDT";

// ---------------------------------------------------------------------------
// Estado público do BTC
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default)]
pub struct BtcState {
    pub rsi_30m: f64,
    pub rsi_1h: f64,
    /// true quando rsi_30m ≤ max_rsi_btc OU rsi_1h ≤ max_rsi_btc
    pub is_reset: bool,
}

// ---------------------------------------------------------------------------
// Monitor — task em background que atualiza o BtcState a cada 30s
// ---------------------------------------------------------------------------

pub struct BtcMonitor {
    state: Arc<RwLock<BtcState>>,
    rest: Arc<BybitRestClient>,
    max_rsi_btc: f64,
}

impl BtcMonitor {
    pub fn new(rest: Arc<BybitRestClient>, max_rsi_btc: f64) -> (Arc<RwLock<BtcState>>, Arc<Self>) {
        let state = Arc::new(RwLock::new(BtcState::default()));
        let monitor = Arc::new(BtcMonitor {
            state: state.clone(),
            rest,
            max_rsi_btc,
        });
        (state, monitor)
    }

    /// Inicia a task em background.
    pub fn start(self: Arc<Self>) {
        tokio::spawn(async move {
            info!("BtcMonitor iniciado");
            let mut interval = tokio::time::interval(Duration::from_secs(30));
            loop {
                interval.tick().await;
                if let Err(e) = self.refresh().await {
                    error!("BtcMonitor erro ao atualizar: {:#}", e);
                }
            }
        });
    }

    async fn refresh(&self) -> Result<()> {
        let klines_30m = self
            .rest
            .get_klines(BTC_SYMBOL, "30", 20)
            .await
            .unwrap_or_default();
        let klines_1h = self
            .rest
            .get_klines(BTC_SYMBOL, "60", 20)
            .await
            .unwrap_or_default();

        let rsi_30m = calc_rsi(&klines_30m.iter().map(|k| k.close).collect::<Vec<_>>(), 14);
        let rsi_1h = calc_rsi(&klines_1h.iter().map(|k| k.close).collect::<Vec<_>>(), 14);

        let is_reset = rsi_30m <= self.max_rsi_btc || rsi_1h <= self.max_rsi_btc;

        let mut state = self.state.write().await;
        state.rsi_30m = rsi_30m;
        state.rsi_1h = rsi_1h;
        state.is_reset = is_reset;

        info!(
            "BTC RSI 30m={:.1} 1h={:.1} reset={}",
            rsi_30m, rsi_1h, is_reset
        );
        Ok(())
    }

    /// Atualiza o limiar max_rsi_btc (chamado quando config é recarregada).
    pub async fn set_max_rsi(&self, max_rsi: f64) {
        // O campo é imutável nesta versão; para recarga em runtime, recrie o monitor
        // ou use RwLock<f64>. Por ora, o decision_loop lê diretamente do config.
        let _ = max_rsi;
    }
}

// ---------------------------------------------------------------------------
// Cálculo de RSI (Wilder's Smoothed Moving Average)
// ---------------------------------------------------------------------------

/// Calcula RSI de 14 períodos usando SMMA (Wilder's method).
/// Retorna 50.0 se dados insuficientes.
pub fn calc_rsi(closes: &[f64], period: usize) -> f64 {
    if closes.len() < period + 1 {
        return 50.0;
    }

    let mut gains = Vec::with_capacity(closes.len() - 1);
    let mut losses = Vec::with_capacity(closes.len() - 1);

    for i in 1..closes.len() {
        let delta = closes[i] - closes[i - 1];
        if delta >= 0.0 {
            gains.push(delta);
            losses.push(0.0);
        } else {
            gains.push(0.0);
            losses.push(-delta);
        }
    }

    // Média inicial (SMA dos primeiros `period` elementos)
    let mut avg_gain: f64 = gains[..period].iter().sum::<f64>() / period as f64;
    let mut avg_loss: f64 = losses[..period].iter().sum::<f64>() / period as f64;

    // Wilder's smoothing
    for i in period..gains.len() {
        avg_gain = (avg_gain * (period as f64 - 1.0) + gains[i]) / period as f64;
        avg_loss = (avg_loss * (period as f64 - 1.0) + losses[i]) / period as f64;
    }

    if avg_loss == 0.0 {
        return 100.0;
    }

    let rs = avg_gain / avg_loss;
    100.0 - (100.0 / (1.0 + rs))
}
