use crate::config::BotConfig;
use anyhow::{anyhow, Context, Result};
use hmac::{Hmac, Mac};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tracing::{info, warn};

type HmacSha256 = Hmac<Sha256>;

const BASE_URL: &str = "https://api.bybit.com";

// ---------------------------------------------------------------------------
// Resultado de ordem
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderResult {
    pub order_id: String,
    pub symbol: String,
    pub side: String,
    pub qty: f64,
    pub entry_price: f64,
}

// ---------------------------------------------------------------------------
// Executor — assina e envia ordens para a Bybit
// ---------------------------------------------------------------------------

pub struct BybitExecutor {
    http: Client,
    api_key: String,
    api_secret: String,
}

impl BybitExecutor {
    pub fn new() -> Self {
        let api_key = std::env::var("BYBIT_API_KEY")
            .expect("BYBIT_API_KEY não configurada");
        let api_secret = std::env::var("BYBIT_API_SECRET")
            .expect("BYBIT_API_SECRET não configurada");

        BybitExecutor {
            http: Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .expect("Falha ao criar cliente HTTP para executor"),
            api_key,
            api_secret,
        }
    }

    pub fn new_arc() -> std::sync::Arc<Self> {
        std::sync::Arc::new(Self::new())
    }

    // -----------------------------------------------------------------------
    // Abre posição a mercado
    // -----------------------------------------------------------------------

    pub async fn open_position(
        &self,
        symbol: &str,
        side: &str, // "Buy" | "Sell"
        qty: f64,
        config: &BotConfig,
    ) -> Result<OrderResult> {
        let body = serde_json::json!({
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": format!("{:.4}", qty),
            "leverage": config.leverage.to_string(),
            "timeInForce": "IOC",
        });

        let resp = self
            .signed_post("/v5/order/create", &body)
            .await
            .context("open_position")?;

        let order_id = resp["result"]["orderId"]
            .as_str()
            .unwrap_or("")
            .to_string();

        if order_id.is_empty() {
            let msg = resp["retMsg"].as_str().unwrap_or("unknown").to_string();
            return Err(anyhow!("Bybit order error: {}", msg));
        }

        info!("Ordem aberta: {} {} qty={:.4} orderId={}", side, symbol, qty, order_id);

        Ok(OrderResult {
            order_id,
            symbol: symbol.to_string(),
            side: side.to_string(),
            qty,
            entry_price: 0.0, // preenchido pelo position_manager após fill
        })
    }

    // -----------------------------------------------------------------------
    // Fecha posição
    // -----------------------------------------------------------------------

    pub async fn close_position(
        &self,
        symbol: &str,
        side: &str, // lado oposto ao da posição
        qty: f64,
    ) -> Result<()> {
        let body = serde_json::json!({
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": format!("{:.4}", qty),
            "reduceOnly": true,
            "timeInForce": "IOC",
        });

        let resp = self
            .signed_post("/v5/order/create", &body)
            .await
            .context("close_position")?;

        let ret_code = resp["retCode"].as_i64().unwrap_or(-1);
        if ret_code != 0 {
            let msg = resp["retMsg"].as_str().unwrap_or("unknown").to_string();
            return Err(anyhow!("Bybit close error: {}", msg));
        }

        info!("Posição fechada: {} {}", symbol, side);
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Define TP/SL via trading-stop
    // -----------------------------------------------------------------------

    pub async fn set_tp_sl(
        &self,
        symbol: &str,
        tp_price: f64,
        sl_price: f64,
        position_idx: i64, // 0 = one-way mode
    ) -> Result<()> {
        let body = serde_json::json!({
            "category": "linear",
            "symbol": symbol,
            "takeProfit": format!("{:.4}", tp_price),
            "stopLoss": format!("{:.4}", sl_price),
            "positionIdx": position_idx,
        });

        let resp = self
            .signed_post("/v5/position/trading-stop", &body)
            .await
            .context("set_tp_sl")?;

        let ret_code = resp["retCode"].as_i64().unwrap_or(-1);
        if ret_code != 0 {
            let msg = resp["retMsg"].as_str().unwrap_or("unknown").to_string();
            return Err(anyhow!("Bybit set_tp_sl error: {}", msg));
        }

        info!(
            "TP/SL configurado: {} tp={:.4} sl={:.4}",
            symbol, tp_price, sl_price
        );
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Obtém o preço atual de uma posição aberta
    // -----------------------------------------------------------------------

    pub async fn get_position_entry_price(&self, symbol: &str) -> Result<f64> {
        let ts = now_ms();
        let params = format!(
            "category=linear&symbol={}&timestamp={}&api_key={}",
            symbol, ts, self.api_key
        );
        let sign = self.sign(&params);

        let url = format!(
            "{}/v5/position/list?{}&sign={}",
            BASE_URL, params, sign
        );

        let resp: serde_json::Value = self
            .http
            .get(&url)
            .header("X-BAPI-API-KEY", &self.api_key)
            .header("X-BAPI-TIMESTAMP", ts.to_string())
            .header("X-BAPI-SIGN", sign)
            .send()
            .await?
            .json()
            .await?;

        let price = resp["result"]["list"]
            .as_array()
            .and_then(|a| a.first())
            .and_then(|e| e["avgPrice"].as_str())
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(0.0);

        Ok(price)
    }

    // -----------------------------------------------------------------------
    // Requisição POST assinada com HMAC-SHA256
    // -----------------------------------------------------------------------

    async fn signed_post(&self, path: &str, body: &serde_json::Value) -> Result<serde_json::Value> {
        let ts = now_ms();
        let recv_window = 5000u64;
        let body_str = serde_json::to_string(body)?;

        // Payload para assinatura: timestamp + api_key + recv_window + body
        let sign_payload = format!("{}{}{}{}", ts, self.api_key, recv_window, body_str);
        let signature = self.sign(&sign_payload);

        let url = format!("{}{}", BASE_URL, path);
        let resp: serde_json::Value = self
            .http
            .post(&url)
            .header("X-BAPI-API-KEY", &self.api_key)
            .header("X-BAPI-TIMESTAMP", ts.to_string())
            .header("X-BAPI-SIGN", &signature)
            .header("X-BAPI-RECV-WINDOW", recv_window.to_string())
            .header("Content-Type", "application/json")
            .body(body_str)
            .send()
            .await
            .context(format!("POST {}", path))?
            .json()
            .await?;

        Ok(resp)
    }

    fn sign(&self, payload: &str) -> String {
        let mut mac = HmacSha256::new_from_slice(self.api_secret.as_bytes())
            .expect("HMAC key inválida");
        mac.update(payload.as_bytes());
        hex::encode(mac.finalize().into_bytes())
    }
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}
