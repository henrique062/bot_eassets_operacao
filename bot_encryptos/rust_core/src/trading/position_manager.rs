use crate::config::python_api_url;
use crate::db::postgres::DbPool;
use anyhow::Result;
use chrono::{DateTime, Utc};
use dashmap::DashMap;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::{error, info, warn};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Modelo de posição aberta
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Position {
    pub id: Uuid,
    pub config_id: i32,
    pub symbol: String,
    pub side: String,       // "Buy" | "Sell"
    pub qty: f64,
    pub entry_price: f64,
    pub entry_score: f64,
    pub stop_loss: f64,
    pub take_profit: f64,
    pub trailing_stop_pct: f64,
    pub trailing_start_pct: f64,
    pub order_id: String,
    pub opened_at: DateTime<Utc>,
    /// Preço mais favorável já atingido (para trailing stop)
    pub peak_price: f64,
    /// true quando trailing stop foi ativado
    pub trailing_active: bool,
    /// Motivo de fechamento (None = ainda aberta)
    pub close_reason: Option<String>,
    /// "paper" (simulado) ou "live" (real)
    pub mode: String,
}

impl Position {
    pub fn new(
        config_id: i32,
        symbol: &str,
        side: &str,
        qty: f64,
        entry_price: f64,
        entry_score: f64,
        stop_loss: f64,
        take_profit: f64,
        trailing_stop_pct: f64,
        trailing_start_pct: f64,
        order_id: &str,
    ) -> Self {
        Position {
            id: Uuid::new_v4(),
            config_id,
            symbol: symbol.to_string(),
            side: side.to_string(),
            qty,
            entry_price,
            entry_score,
            stop_loss,
            take_profit,
            trailing_stop_pct,
            trailing_start_pct,
            order_id: order_id.to_string(),
            opened_at: Utc::now(),
            peak_price: entry_price,
            trailing_active: false,
            close_reason: None,
            mode: "live".to_string(),
        }
    }

    /// Retorna o PnL percentual dado um preço atual.
    pub fn pnl_pct(&self, current_price: f64) -> f64 {
        if self.entry_price == 0.0 {
            return 0.0;
        }
        match self.side.as_str() {
            "Buy" => (current_price - self.entry_price) / self.entry_price * 100.0,
            "Sell" => (self.entry_price - current_price) / self.entry_price * 100.0,
            _ => 0.0,
        }
    }

    /// Atualiza peak_price e ativa trailing se necessário.
    pub fn update_peak(&mut self, current_price: f64) {
        match self.side.as_str() {
            "Buy" => {
                if current_price > self.peak_price {
                    self.peak_price = current_price;
                }
                // Ativa trailing quando lucro >= trailing_start_pct
                if self.pnl_pct(current_price) >= self.trailing_start_pct {
                    self.trailing_active = true;
                }
            }
            "Sell" => {
                if current_price < self.peak_price {
                    self.peak_price = current_price;
                }
                if self.pnl_pct(current_price) >= self.trailing_start_pct {
                    self.trailing_active = true;
                }
            }
            _ => {}
        }
    }

    /// Calcula o nível atual do trailing stop.
    pub fn trailing_stop_price(&self) -> f64 {
        let factor = 1.0 - self.trailing_stop_pct / 100.0;
        match self.side.as_str() {
            "Buy" => self.peak_price * factor,
            "Sell" => self.peak_price / factor,
            _ => self.stop_loss,
        }
    }
}

// ---------------------------------------------------------------------------
// PositionManager — mapa em memória + persistência PostgreSQL
// ---------------------------------------------------------------------------

pub struct PositionManager {
    positions: Arc<DashMap<String, Position>>,
    db: DbPool,
    http: Client,
}

impl PositionManager {
    pub fn new(db: DbPool) -> Arc<Self> {
        Arc::new(PositionManager {
            positions: Arc::new(DashMap::new()),
            db,
            http: Client::new(),
        })
    }

    /// Adiciona posição em memória e persiste no banco.
    pub async fn add(&self, position: Position) -> Result<()> {
        let symbol = position.symbol.clone();
        crate::db::postgres::insert_position(&self.db, &position).await?;
        self.positions.insert(symbol.clone(), position);
        self.notify_python("opened", &symbol).await;
        info!("Posição adicionada: {}", symbol);
        Ok(())
    }

    /// Remove posição da memória e marca como fechada no banco.
    pub async fn close(
        &self,
        symbol: &str,
        close_price: f64,
        reason: &str,
    ) -> Result<Option<Position>> {
        let Some((_, mut pos)) = self.positions.remove(symbol) else {
            return Ok(None);
        };
        pos.close_reason = Some(reason.to_string());

        let pnl = pos.pnl_pct(close_price) * pos.qty * pos.entry_price / 100.0;
        crate::db::postgres::close_position(
            &self.db,
            pos.id,
            close_price,
            pnl,
            reason,
        )
        .await?;

        self.notify_python("closed", symbol).await;
        info!("Posição fechada: {} reason={} pnl={:.4}", symbol, reason, pnl);
        Ok(Some(pos))
    }

    pub fn get(&self, symbol: &str) -> Option<Position> {
        self.positions.get(symbol).map(|e| e.clone())
    }

    pub fn all(&self) -> Vec<Position> {
        self.positions.iter().map(|e| e.value().clone()).collect()
    }

    pub fn count(&self) -> usize {
        self.positions.len()
    }

    /// Atualiza preço de pico para trailing stop.
    pub fn update_peak(&self, symbol: &str, current_price: f64) {
        if let Some(mut pos) = self.positions.get_mut(symbol) {
            pos.update_peak(current_price);
        }
    }

    // Notifica o serviço Python sobre mudança de posição
    async fn notify_python(&self, event: &str, symbol: &str) {
        let url = format!("{}/internal/position-update", python_api_url());
        let body = serde_json::json!({
            "event": event,
            "symbol": symbol,
        });
        if let Err(e) = self.http.post(&url).json(&body).send().await {
            warn!("Falha ao notificar Python sobre posição {}: {}", symbol, e);
        }
    }
}
