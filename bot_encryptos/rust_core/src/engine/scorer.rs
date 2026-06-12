use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// SymbolSignals — todos os indicadores necessários para scoring e filtragem
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SymbolSignals {
    pub symbol: String,
    pub price: f64,

    // Exponencial BTC por timeframe (retorno % composto)
    pub exp_btc_5m: f64,
    pub exp_btc_15m: f64,
    pub exp_btc_1h: f64,
    pub exp_btc_1d: f64,

    // Volume / atividade
    pub trades_min: f64,

    // Open Interest trend (% delta em relação à média)
    pub oi_trend: f64,

    // Long/Short Ratio e sua tendência (negativo = queda = favorável)
    pub lsr: f64,
    pub lsr_trend: f64,

    // Nível de range (0-5 — quanto maior, mais estrutura)
    pub range_level: f64,
    pub range_level_4h: f64,
    pub range_level_1d: f64,

    // RSI 4h do próprio ativo
    pub rsi_4h: f64,

    // Total Open Interest em USD (TOI)
    pub toi: f64,
}

// ---------------------------------------------------------------------------
// Pesos do score (somam 1.0)
// ---------------------------------------------------------------------------

const W_EXP_BTC: f64 = 0.30;
const W_TRADES_MIN: f64 = 0.25;
const W_OI_TREND: f64 = 0.20;
const W_LSR: f64 = 0.15;
const W_RANGE: f64 = 0.10;

// Valores de saturação para normalização linear
const SAT_EXP_BTC: f64 = 5.0;     // % de retorno composto que satura em 1.0
const SAT_TRADES_MIN: f64 = 3000.0; // trades/min que satura em 1.0
const SAT_OI_TREND: f64 = 10.0;   // % de crescimento OI que satura em 1.0
const SAT_LSR: f64 = 1.5;         // LSR máximo usado para normalização inversa
const SAT_RANGE: f64 = 5.0;       // range_level máximo

/// Calcula o score final (0–100) de um símbolo.
pub fn score(signals: &SymbolSignals) -> f64 {
    // exp_btc: média dos 3 timeframes obrigatórios
    let exp_avg = (signals.exp_btc_5m + signals.exp_btc_15m + signals.exp_btc_1h) / 3.0;
    let n_exp = norm(exp_avg, 0.0, SAT_EXP_BTC);

    let n_tpm = norm(signals.trades_min, 0.0, SAT_TRADES_MIN);

    let n_oi = norm(signals.oi_trend, 0.0, SAT_OI_TREND);

    // LSR favorável = LSR baixo → invertemos a normalização
    let n_lsr = norm(SAT_LSR - signals.lsr.clamp(0.0, SAT_LSR), 0.0, SAT_LSR);

    let n_range = norm(signals.range_level, 0.0, SAT_RANGE);

    let raw = W_EXP_BTC * n_exp
        + W_TRADES_MIN * n_tpm
        + W_OI_TREND * n_oi
        + W_LSR * n_lsr
        + W_RANGE * n_range;

    (raw * 100.0).clamp(0.0, 100.0)
}

/// Normalização linear com clamp em [0, 1].
/// norm(value, min, max) → 0.0 quando value ≤ min, 1.0 quando value ≥ max.
fn norm(value: f64, min: f64, max: f64) -> f64 {
    if max <= min {
        return 0.0;
    }
    ((value - min) / (max - min)).clamp(0.0, 1.0)
}
