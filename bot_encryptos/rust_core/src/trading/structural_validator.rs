use crate::engine::scorer::SymbolSignals;

// ---------------------------------------------------------------------------
// Critérios de estrutura (0-5 pontos)
// ---------------------------------------------------------------------------

/// Avalia a estrutura do símbolo e retorna quantos dos 5 critérios foram atingidos.
///
/// # Critérios
/// 1. range_level_4h >= 3 OU range_level_1d >= 3
/// 2. toi >= 40.000 (Total OI em USD)
/// 3. oi_trend >= 0 (OI crescendo ou estável)
/// 4. exp_btc_1d > 0 (tendência diária positiva)
/// 5. lsr < 1.0 OU lsr_trend < 0 (ratio favorável ou em queda)
pub fn evaluate(signals: &SymbolSignals) -> u8 {
    let mut score: u8 = 0;

    // 1. Range / estrutura de candle
    if signals.range_level_4h >= 3.0 || signals.range_level_1d >= 3.0 {
        score += 1;
    }

    // 2. Total OI em USD
    if signals.toi >= 40_000.0 {
        score += 1;
    }

    // 3. OI trend positivo
    if signals.oi_trend >= 0.0 {
        score += 1;
    }

    // 4. Exponencial diário positivo
    if signals.exp_btc_1d > 0.0 {
        score += 1;
    }

    // 5. LSR favorável
    if signals.lsr < 1.0 || signals.lsr_trend < 0.0 {
        score += 1;
    }

    score
}

// ---------------------------------------------------------------------------
// Estado de invalidação para uma entrada na watchlist
// ---------------------------------------------------------------------------

#[derive(Debug, Default)]
pub struct InvalidationTracker {
    /// Quantos checks consecutivos com exp_btc_1d < -50
    pub exp_btc_negative_streak: u32,
    /// Quantos checks consecutivos com oi_trend < 0
    pub oi_negative_streak: u32,
}

/// Verifica se a entrada deve ser invalidada com base nos sinais atuais.
///
/// # Regras de invalidação
/// - exp_btc_1d < -50 por 2+ checks consecutivos
/// - range_level_4h < 2 E range_level_1d < 2
/// - oi_trend < 0 por 3+ checks consecutivos
/// - attempt_count >= max_attempts
pub fn check_invalidation(
    signals: &SymbolSignals,
    tracker: &mut InvalidationTracker,
    attempt_count: i32,
    max_attempts: i32,
) -> Option<&'static str> {
    // Atualiza streaks
    if signals.exp_btc_1d < -50.0 {
        tracker.exp_btc_negative_streak += 1;
    } else {
        tracker.exp_btc_negative_streak = 0;
    }

    if signals.oi_trend < 0.0 {
        tracker.oi_negative_streak += 1;
    } else {
        tracker.oi_negative_streak = 0;
    }

    // Verifica condições de invalidação na ordem de severidade
    if tracker.exp_btc_negative_streak >= 2 {
        return Some("exp_btc_1d negativo por 2+ checks consecutivos");
    }

    if signals.range_level_4h < 2.0 && signals.range_level_1d < 2.0 {
        return Some("range_level insuficiente em 4h e 1d");
    }

    if tracker.oi_negative_streak >= 3 {
        return Some("oi_trend negativo por 3+ checks consecutivos");
    }

    if attempt_count >= max_attempts {
        return Some("limite de tentativas atingido");
    }

    None
}
