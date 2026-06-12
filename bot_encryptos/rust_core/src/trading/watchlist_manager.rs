use crate::config::BotConfig;
use crate::db::postgres::DbPool;
use crate::engine::scorer::SymbolSignals;
use crate::market::bybit_rest::BybitRestClient;
use crate::trading::position_manager::Position;
use crate::trading::structural_validator::{
    check_invalidation, evaluate, InvalidationTracker,
};
use anyhow::Result;
use chrono::{DateTime, Utc};
use dashmap::DashMap;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Duration;
use tracing::{info, warn};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Estados da máquina PCL
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum WatchlistStatus {
    Watchlist,
    Cooldown,
    Candidate,
    Active,
    Invalidated,
    Completed,
}

impl std::fmt::Display for WatchlistStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:?}", self)
    }
}

// ---------------------------------------------------------------------------
// Entrada na watchlist
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WatchlistEntry {
    pub id: Uuid,
    pub config_id: i32,
    pub symbol: String,
    pub status: WatchlistStatus,
    pub struct_score: u8,
    pub attempt_count: i32,
    pub cooldown_until: Option<DateTime<Utc>>,
    pub added_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub original_position_id: Option<Uuid>,
}

impl WatchlistEntry {
    pub fn new(
        config_id: i32,
        symbol: &str,
        struct_score: u8,
        position_id: Option<Uuid>,
    ) -> Self {
        let now = Utc::now();
        WatchlistEntry {
            id: Uuid::new_v4(),
            config_id,
            symbol: symbol.to_string(),
            status: WatchlistStatus::Watchlist,
            struct_score,
            attempt_count: 0,
            cooldown_until: None,
            added_at: now,
            updated_at: now,
            original_position_id: position_id,
        }
    }

    pub fn is_in_cooldown(&self) -> bool {
        match self.cooldown_until {
            Some(until) => Utc::now() < until,
            None => false,
        }
    }
}

// ---------------------------------------------------------------------------
// WatchlistManager
// ---------------------------------------------------------------------------

pub struct WatchlistManager {
    entries: Arc<DashMap<String, WatchlistEntry>>,
    trackers: Arc<DashMap<String, InvalidationTracker>>,
    db: DbPool,
    rest: Arc<BybitRestClient>,
}

impl WatchlistManager {
    pub fn new(db: DbPool, rest: Arc<BybitRestClient>) -> Arc<Self> {
        Arc::new(WatchlistManager {
            entries: Arc::new(DashMap::new()),
            trackers: Arc::new(DashMap::new()),
            db,
            rest,
        })
    }

    /// Hook chamado pelo RiskManager quando uma posição fecha por stop loss.
    /// Avalia a estrutura do ativo e o adiciona à watchlist se adequado.
    pub async fn on_stop_triggered(&self, position: Position, config: &BotConfig) {
        info!("PCL: stop acionado em {}", position.symbol);

        // Obtém sinais para avaliação estrutural
        let signals = match self.fetch_signals(&position.symbol).await {
            Ok(s) => s,
            Err(e) => {
                warn!("PCL: falha ao obter sinais para {}: {:#}", position.symbol, e);
                return;
            }
        };

        let struct_score = evaluate(&signals);
        info!(
            "PCL: {} struct_score={}/5 (min={})",
            position.symbol, struct_score, config.pcl_min_struct_score
        );

        // Loga o evento PCL_ADDED
        let _ = crate::db::postgres::insert_order_log(
            &self.db,
            config.config_id,
            &position.symbol,
            "PCL_ADDED",
            &format!(
                "Stop acionado. struct_score={}/5",
                struct_score
            ),
        )
        .await;

        if struct_score < config.pcl_min_struct_score as u8 {
            info!(
                "PCL: {} não elegível (struct_score {} < {})",
                position.symbol, struct_score, config.pcl_min_struct_score
            );
            return;
        }

        // Cooldown após stop
        let cooldown_until = Utc::now()
            + chrono::Duration::minutes(config.pcl_cooldown_minutes as i64);

        let mut entry = WatchlistEntry::new(
            config.config_id,
            &position.symbol,
            struct_score,
            Some(position.id),
        );
        entry.status = WatchlistStatus::Cooldown;
        entry.cooldown_until = Some(cooldown_until);

        // Persiste no banco
        if let Err(e) = crate::db::postgres::upsert_watchlist(&self.db, &entry).await {
            warn!("PCL: falha ao persistir watchlist para {}: {:#}", position.symbol, e);
        }

        self.entries.insert(position.symbol.clone(), entry);
        info!("PCL: {} adicionado à watchlist em cooldown até {}", position.symbol, cooldown_until);
    }

    /// Loop PCL — roda a cada 60s, processa entradas em cooldown e candidatos.
    pub fn start_loop(self: Arc<Self>, config_arc: Arc<tokio::sync::RwLock<BotConfig>>) {
        tokio::spawn(async move {
            info!("PCL loop iniciado");
            let mut interval = tokio::time::interval(Duration::from_secs(60));

            loop {
                interval.tick().await;
                let config = config_arc.read().await.clone();

                if !config.pcl_enabled {
                    continue;
                }

                self.process_loop(&config).await;
            }
        });
    }

    async fn process_loop(&self, config: &BotConfig) {
        let symbols: Vec<String> = self
            .entries
            .iter()
            .map(|e| e.key().clone())
            .collect();

        for symbol in symbols {
            let Some(entry) = self.entries.get(&symbol).map(|e| e.clone()) else {
                continue;
            };

            match entry.status {
                WatchlistStatus::Cooldown => {
                    if !entry.is_in_cooldown() {
                        info!("PCL: {} saiu do cooldown → Candidate", symbol);
                        self.transition(&symbol, WatchlistStatus::Candidate, config).await;
                    }
                }
                WatchlistStatus::Candidate => {
                    self.evaluate_candidate(&symbol, config).await;
                }
                WatchlistStatus::Active | WatchlistStatus::Completed | WatchlistStatus::Invalidated => {
                    // Nada a fazer
                }
                WatchlistStatus::Watchlist => {
                    // Aguardando qualificação
                    self.evaluate_candidate(&symbol, config).await;
                }
            }
        }
    }

    async fn evaluate_candidate(&self, symbol: &str, config: &BotConfig) {
        let signals = match self.fetch_signals(symbol).await {
            Ok(s) => s,
            Err(e) => {
                warn!("PCL evaluate_candidate {}: {:#}", symbol, e);
                return;
            }
        };

        let attempt_count = self
            .entries
            .get(symbol)
            .map(|e| e.attempt_count)
            .unwrap_or(0);

        // Aplica invalidação dentro de um bloco para soltar o RefMut antes de chamar transition
        let invalidation_reason = {
            let mut tracker = self
                .trackers
                .entry(symbol.to_string())
                .or_default();

            check_invalidation(
                &signals,
                &mut *tracker,
                attempt_count,
                config.pcl_max_attempts,
            )
        };

        // Verifica invalidação
        if let Some(reason) = invalidation_reason {
            warn!("PCL: {} INVALIDADO: {}", symbol, reason);
            self.transition(symbol, WatchlistStatus::Invalidated, config).await;
            let _ = crate::db::postgres::insert_order_log(
                &self.db,
                config.config_id,
                symbol,
                "PCL_INVALIDATED",
                reason,
            )
            .await;
            return;
        }

        let struct_score = evaluate(&signals);
        if struct_score >= config.pcl_min_struct_score as u8 {
            info!("PCL: {} candidate elegível (struct_score={}/5)", symbol, struct_score);
            let _ = crate::db::postgres::insert_order_log(
                &self.db,
                config.config_id,
                symbol,
                "PCL_REENTRY",
                &format!("Candidato elegível. struct_score={}/5", struct_score),
            )
            .await;
            // Incrementa tentativas
            if let Some(mut entry) = self.entries.get_mut(symbol) {
                entry.attempt_count += 1;
                entry.updated_at = Utc::now();
            }
        }
    }

    async fn transition(&self, symbol: &str, new_status: WatchlistStatus, _config: &BotConfig) {
        if let Some(mut entry) = self.entries.get_mut(symbol) {
            entry.status = new_status;
            entry.updated_at = Utc::now();
        }

        if let Some(entry) = self.entries.get(symbol) {
            let _ = crate::db::postgres::upsert_watchlist(&self.db, &entry).await;
        }
    }

    pub fn get_all(&self) -> Vec<WatchlistEntry> {
        self.entries.iter().map(|e| e.value().clone()).collect()
    }

    async fn fetch_signals(&self, symbol: &str) -> Result<SymbolSignals> {
        // Coleta sinais mínimos para avaliação estrutural
        let (klines_4h, klines_1d) = tokio::join!(
            self.rest.get_klines(symbol, "240", 20),
            self.rest.get_klines(symbol, "D", 10),
        );

        let oi_current = self.rest.get_open_interest(symbol).await.unwrap_or(0.0);
        let (long_r, short_r) = self
            .rest
            .get_long_short_ratio(symbol, "5min")
            .await
            .unwrap_or((0.5, 0.5));
        let lsr = if short_r > 0.0 { long_r / short_r } else { 1.0 };

        let exp_btc_1d = klines_1d
            .as_ref()
            .map(|k| crate::market::bybit_rest::calc_exp_btc(k))
            .unwrap_or(0.0);

        let range_level_4h = klines_4h
            .as_ref()
            .map(|k| estimate_range(k))
            .unwrap_or(0.0);

        let range_level_1d = klines_1d
            .as_ref()
            .map(|k| estimate_range(k))
            .unwrap_or(0.0);

        let price = klines_4h
            .as_ref()
            .and_then(|k| k.last())
            .map(|k| k.close)
            .unwrap_or(0.0);

        Ok(SymbolSignals {
            symbol: symbol.to_string(),
            price,
            exp_btc_1d,
            oi_trend: 0.0, // obtido pelo decision loop; aqui apenas estrutural
            lsr,
            lsr_trend: 0.0,
            range_level: range_level_4h,
            range_level_4h,
            range_level_1d,
            toi: oi_current,
            ..Default::default()
        })
    }
}

fn estimate_range(klines: &[crate::market::bybit_rest::KlineData]) -> f64 {
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
    let avg = ranges.iter().sum::<f64>() / ranges.len() as f64;
    if avg < 0.5 { 1.0 } else if avg < 1.0 { 2.0 } else if avg < 2.0 { 3.0 } else if avg < 3.0 { 4.0 } else { 5.0 }
}
