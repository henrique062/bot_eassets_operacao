use anyhow::{anyhow, Context, Result};
use dashmap::DashMap;
use reqwest::Client;
use serde::Deserialize;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing::{debug, warn};

const BASE_URL: &str = "https://api.bybit.com";

// ---------------------------------------------------------------------------
// Tipos de dados retornados pela API REST
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct TickerData {
    pub symbol: String,
    #[serde(rename = "lastPrice", default)]
    pub last_price: String,
    #[serde(rename = "volume24h", default)]
    pub volume_24h: String,
    #[serde(rename = "openInterestValue", default)]
    pub oi_value: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct KlineData {
    /// [start_time, open, high, low, close, volume, turnover]
    pub start_time: i64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub turnover: f64,
}

#[derive(Debug, Clone)]
struct CacheEntry<T> {
    value: T,
    inserted_at: Instant,
    ttl: Duration,
}

impl<T: Clone> CacheEntry<T> {
    fn is_valid(&self) -> bool {
        self.inserted_at.elapsed() < self.ttl
    }
}

// ---------------------------------------------------------------------------
// Cliente REST com cache em memória
// ---------------------------------------------------------------------------

pub struct BybitRestClient {
    http: Client,
    ticker_cache: DashMap<String, CacheEntry<Vec<TickerData>>>,
    lsr_cache: DashMap<String, CacheEntry<(f64, f64)>>,
    oi_cache: DashMap<String, CacheEntry<f64>>,
    kline_cache: DashMap<String, CacheEntry<Vec<KlineData>>>,
    funding_cache: DashMap<String, CacheEntry<f64>>,
}

impl BybitRestClient {
    pub fn new() -> Arc<Self> {
        let http = Client::builder()
            .timeout(Duration::from_secs(10))
            .build()
            .expect("Falha ao criar cliente HTTP");

        Arc::new(Self {
            http,
            ticker_cache: DashMap::new(),
            lsr_cache: DashMap::new(),
            oi_cache: DashMap::new(),
            kline_cache: DashMap::new(),
            funding_cache: DashMap::new(),
        })
    }

    // -----------------------------------------------------------------------
    // Tickers (cache 5s)
    // -----------------------------------------------------------------------

    pub async fn get_tickers(&self) -> Result<Vec<TickerData>> {
        const CACHE_KEY: &str = "_all_tickers";
        if let Some(entry) = self.ticker_cache.get(CACHE_KEY) {
            if entry.is_valid() {
                return Ok(entry.value.clone());
            }
        }

        let url = format!("{}/v5/market/tickers?category=linear", BASE_URL);
        let resp: serde_json::Value = self
            .http
            .get(&url)
            .send()
            .await
            .context("GET /v5/market/tickers")?
            .json()
            .await?;

        let tickers = parse_tickers(&resp)?;
        self.ticker_cache.insert(
            CACHE_KEY.to_string(),
            CacheEntry {
                value: tickers.clone(),
                inserted_at: Instant::now(),
                ttl: Duration::from_secs(5),
            },
        );
        Ok(tickers)
    }

    // -----------------------------------------------------------------------
    // Open Interest (cache 30s)
    // -----------------------------------------------------------------------

    pub async fn get_open_interest(&self, symbol: &str) -> Result<f64> {
        if let Some(entry) = self.oi_cache.get(symbol) {
            if entry.is_valid() {
                return Ok(entry.value);
            }
        }

        let url = format!(
            "{}/v5/market/open-interest?category=linear&symbol={}&intervalTime=5min&limit=1",
            BASE_URL, symbol
        );
        let resp: serde_json::Value = self
            .http
            .get(&url)
            .send()
            .await
            .context("GET /v5/market/open-interest")?
            .json()
            .await?;

        let oi = resp["result"]["list"]
            .as_array()
            .and_then(|a| a.first())
            .and_then(|e| e["openInterest"].as_str())
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(0.0);

        self.oi_cache.insert(
            symbol.to_string(),
            CacheEntry {
                value: oi,
                inserted_at: Instant::now(),
                ttl: Duration::from_secs(30),
            },
        );
        Ok(oi)
    }

    // -----------------------------------------------------------------------
    // Long/Short Ratio (cache 120s)
    // -----------------------------------------------------------------------

    /// Retorna (long_ratio, short_ratio)
    pub async fn get_long_short_ratio(
        &self,
        symbol: &str,
        period: &str,
    ) -> Result<(f64, f64)> {
        let cache_key = format!("{}_{}", symbol, period);
        if let Some(entry) = self.lsr_cache.get(&cache_key) {
            if entry.is_valid() {
                return Ok(entry.value);
            }
        }

        let url = format!(
            "{}/v5/market/account-ratio?category=linear&symbol={}&period={}&limit=1",
            BASE_URL, symbol, period
        );
        let resp: serde_json::Value = self
            .http
            .get(&url)
            .send()
            .await
            .context("GET /v5/market/account-ratio")?
            .json()
            .await?;

        let (long_r, short_r) = resp["result"]["list"]
            .as_array()
            .and_then(|a| a.first())
            .map(|e| {
                let l = e["buyRatio"]
                    .as_str()
                    .and_then(|s| s.parse::<f64>().ok())
                    .unwrap_or(0.5);
                let s = e["sellRatio"]
                    .as_str()
                    .and_then(|s| s.parse::<f64>().ok())
                    .unwrap_or(0.5);
                (l, s)
            })
            .unwrap_or((0.5, 0.5));

        let pair = (long_r, short_r);
        self.lsr_cache.insert(
            cache_key,
            CacheEntry {
                value: pair,
                inserted_at: Instant::now(),
                ttl: Duration::from_secs(120),
            },
        );
        Ok(pair)
    }

    // -----------------------------------------------------------------------
    // Klines (cache TTL dinâmico por interval)
    // -----------------------------------------------------------------------

    pub async fn get_klines(
        &self,
        symbol: &str,
        interval: &str,
        limit: u32,
    ) -> Result<Vec<KlineData>> {
        let cache_key = format!("{}_{}_{}", symbol, interval, limit);
        if let Some(entry) = self.kline_cache.get(&cache_key) {
            if entry.is_valid() {
                return Ok(entry.value.clone());
            }
        }

        let url = format!(
            "{}/v5/market/kline?category=linear&symbol={}&interval={}&limit={}",
            BASE_URL, symbol, interval, limit
        );
        let resp: serde_json::Value = self
            .http
            .get(&url)
            .send()
            .await
            .context("GET /v5/market/kline")?
            .json()
            .await?;

        let klines = parse_klines(&resp)?;
        let ttl = kline_ttl(interval);
        self.kline_cache.insert(
            cache_key,
            CacheEntry {
                value: klines.clone(),
                inserted_at: Instant::now(),
                ttl,
            },
        );
        Ok(klines)
    }

    // -----------------------------------------------------------------------
    // Funding Rate (cache 300s)
    // -----------------------------------------------------------------------

    pub async fn get_funding_rate(&self, symbol: &str) -> Result<f64> {
        if let Some(entry) = self.funding_cache.get(symbol) {
            if entry.is_valid() {
                return Ok(entry.value);
            }
        }

        let url = format!(
            "{}/v5/market/funding/history?category=linear&symbol={}&limit=1",
            BASE_URL, symbol
        );
        let resp: serde_json::Value = self
            .http
            .get(&url)
            .send()
            .await
            .context("GET /v5/market/funding/history")?
            .json()
            .await?;

        let rate = resp["result"]["list"]
            .as_array()
            .and_then(|a| a.first())
            .and_then(|e| e["fundingRate"].as_str())
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(0.0);

        self.funding_cache.insert(
            symbol.to_string(),
            CacheEntry {
                value: rate,
                inserted_at: Instant::now(),
                ttl: Duration::from_secs(300),
            },
        );
        Ok(rate)
    }
}

// ---------------------------------------------------------------------------
// Helpers de parsing
// ---------------------------------------------------------------------------

fn parse_tickers(resp: &serde_json::Value) -> Result<Vec<TickerData>> {
    let list = resp["result"]["list"]
        .as_array()
        .ok_or_else(|| anyhow!("Resposta de tickers inválida"))?;

    let tickers = list
        .iter()
        .filter_map(|v| serde_json::from_value::<TickerData>(v.clone()).ok())
        .collect();

    Ok(tickers)
}

fn parse_klines(resp: &serde_json::Value) -> Result<Vec<KlineData>> {
    // Bybit retorna lista de arrays: [startTime, open, high, low, close, volume, turnover]
    let list = resp["result"]["list"]
        .as_array()
        .ok_or_else(|| anyhow!("Resposta de klines inválida"))?;

    let klines = list
        .iter()
        .filter_map(|row| {
            let arr = row.as_array()?;
            if arr.len() < 7 {
                return None;
            }
            Some(KlineData {
                start_time: arr[0].as_str()?.parse().ok()?,
                open: arr[1].as_str()?.parse().ok()?,
                high: arr[2].as_str()?.parse().ok()?,
                low: arr[3].as_str()?.parse().ok()?,
                close: arr[4].as_str()?.parse().ok()?,
                volume: arr[5].as_str()?.parse().ok()?,
                turnover: arr[6].as_str()?.parse().ok()?,
            })
        })
        .collect();

    Ok(klines)
}

/// TTL de cache dinâmico baseado no intervalo do candle.
fn kline_ttl(interval: &str) -> Duration {
    match interval {
        "1" => Duration::from_secs(30),
        "3" => Duration::from_secs(60),
        "5" => Duration::from_secs(60),
        "15" => Duration::from_secs(120),
        "30" => Duration::from_secs(240),
        "60" => Duration::from_secs(300),
        "240" => Duration::from_secs(600),
        "D" | "1D" => Duration::from_secs(1800),
        _ => Duration::from_secs(60),
    }
}

// ---------------------------------------------------------------------------
// Cálculo de exp_btc (exponencial acumulada) a partir de klines
// ---------------------------------------------------------------------------

/// Calcula variação exponencial acumulada dos closes normalizada (0-100 scale).
/// Positivo = tendência de alta, negativo = tendência de baixa.
pub fn calc_exp_btc(klines: &[KlineData]) -> f64 {
    if klines.len() < 3 {
        return 0.0;
    }
    let closes: Vec<f64> = klines.iter().map(|k| k.close).collect();
    let n = closes.len();
    let recent = &closes[n.saturating_sub(5)..];
    if recent.len() < 2 {
        return 0.0;
    }

    // Retorno composto simples dos últimos N candles
    let first = recent.first().copied().unwrap_or(1.0);
    let last = recent.last().copied().unwrap_or(1.0);
    if first == 0.0 {
        return 0.0;
    }
    ((last / first) - 1.0) * 100.0
}

/// Calcula trend do OI comparando OI atual com média dos últimos N valores.
/// Positivo = OI em crescimento.
pub fn calc_oi_trend(oi_history: &[f64]) -> f64 {
    if oi_history.len() < 2 {
        return 0.0;
    }
    let current = *oi_history.last().unwrap();
    let avg: f64 = oi_history.iter().sum::<f64>() / oi_history.len() as f64;
    if avg == 0.0 {
        return 0.0;
    }
    ((current / avg) - 1.0) * 100.0
}
