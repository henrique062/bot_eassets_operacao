use crate::config::BotConfig;
use crate::engine::scorer::SymbolSignals;
use crate::market::BtcState;

// ---------------------------------------------------------------------------
// Resultado da filtragem de sinais
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct FilterResult {
    pub passed: bool,
    pub failed_reasons: Vec<String>,
}

impl FilterResult {
    fn pass() -> Self {
        FilterResult {
            passed: true,
            failed_reasons: vec![],
        }
    }

    fn fail(reasons: Vec<String>) -> Self {
        FilterResult {
            passed: false,
            failed_reasons: reasons,
        }
    }
}

/// Verifica os 6 filtros obrigatórios da metodologia Encryptos.
///
/// # Filtros
/// 1. Reset BTC — RSI BTC 30m ou 1h ≤ max_rsi_btc
/// 2. Exponencial BTC — exp_btc positivo em 5m, 15m e 1h simultaneamente
/// 3. Aceleração TPM — trades_min > min_tpm OU salto ≥ 4x (detectado externamente)
/// 4. LSR favorável — lsr < max_lsr OU em queda clara (lsr_trend < 0)
/// 5. Combustível OI — oi_trend positivo
/// 6. Posições disponíveis — open_positions < max_positions
pub fn check_all(
    signals: &SymbolSignals,
    config: &BotConfig,
    btc: &BtcState,
    open_positions: usize,
) -> FilterResult {
    let mut reasons = Vec::new();

    // 1. Reset BTC
    if !btc.is_reset {
        reasons.push(format!(
            "BTC não está em reset: RSI30m={:.1} RSI1h={:.1} (max={})",
            btc.rsi_30m, btc.rsi_1h, config.max_rsi_btc
        ));
    }

    // 2. Exponencial BTC positivo em todos os timeframes obrigatórios
    if signals.exp_btc_5m <= 0.0 || signals.exp_btc_15m <= 0.0 || signals.exp_btc_1h <= 0.0 {
        reasons.push(format!(
            "exp_btc não positivo em todos TFs: 5m={:.2} 15m={:.2} 1h={:.2}",
            signals.exp_btc_5m, signals.exp_btc_15m, signals.exp_btc_1h
        ));
    }

    // 3. Aceleração TPM
    // (salto 4x é avaliado externamente pelo WS; aqui verificamos o threshold mínimo)
    if signals.trades_min < config.min_tpm {
        reasons.push(format!(
            "TPM insuficiente: {:.0} < {} (min_tpm)",
            signals.trades_min, config.min_tpm
        ));
    }

    // 4. LSR favorável
    let lsr_ok = signals.lsr < config.max_lsr || signals.lsr_trend < 0.0;
    if !lsr_ok {
        reasons.push(format!(
            "LSR desfavorável: {:.3} >= {} e trend={:.4} não negativo",
            signals.lsr, config.max_lsr, signals.lsr_trend
        ));
    }

    // 5. Combustível OI
    if signals.oi_trend <= 0.0 {
        reasons.push(format!(
            "OI trend não positivo: {:.2}",
            signals.oi_trend
        ));
    }

    // 6. Posições disponíveis
    if open_positions >= config.max_positions as usize {
        reasons.push(format!(
            "Limite de posições atingido: {}/{} abertas",
            open_positions, config.max_positions
        ));
    }

    if reasons.is_empty() {
        FilterResult::pass()
    } else {
        FilterResult::fail(reasons)
    }
}
