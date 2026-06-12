use anyhow::Result;
use dashmap::DashMap;
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

const WS_URL: &str = "wss://stream.bybit.com/v5/public/linear";
const MAX_BACKOFF_SECS: u64 = 30;

/// Mapa de contadores de trades por símbolo.
/// Cada entrada armazena um contador acumulado por minuto.
pub struct TradeCounter {
    // Mapa símbolo → (contador_acumulado, timestamp_ultimo_reset)
    counts: DashMap<String, (AtomicU64, Instant)>,
}

impl TradeCounter {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            counts: DashMap::new(),
        })
    }

    /// Incrementa o contador de trades para o símbolo.
    pub fn increment(&self, symbol: &str) {
        let entry = self.counts.entry(symbol.to_string()).or_insert_with(|| {
            (AtomicU64::new(0), Instant::now())
        });
        entry.0.fetch_add(1, Ordering::Relaxed);
    }

    /// Retorna trades/minuto para o símbolo.
    /// Faz reset do contador a cada janela de 60s.
    pub fn get_trades_per_min(&self, symbol: &str) -> f64 {
        let Some(entry) = self.counts.get(symbol) else {
            return 0.0;
        };
        let elapsed = entry.1.elapsed();
        let count = entry.0.load(Ordering::Relaxed) as f64;
        if elapsed.as_secs_f64() > 0.0 {
            // Normaliza para trades por minuto
            count / elapsed.as_secs_f64() * 60.0
        } else {
            0.0
        }
    }

    /// Reseta contadores mais antigos que 2 minutos para evitar overflow.
    pub fn reset_stale(&self) {
        let now = Instant::now();
        self.counts.retain(|_, (counter, ts)| {
            if now.duration_since(*ts) > Duration::from_secs(120) {
                counter.store(0, Ordering::Relaxed);
                *ts = now;
            }
            true
        });
    }
}

// ---------------------------------------------------------------------------
// Mensagens WebSocket Bybit (publicTrade)
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct WsMessage {
    topic: Option<String>,
    data: Option<serde_json::Value>,
}

/// Inicia a conexão WebSocket e mantém contadores de trades atualizados.
/// Reconecta automaticamente com backoff exponencial em caso de falha.
pub async fn run(symbols: Vec<String>, counter: Arc<TradeCounter>) {
    let topics: Vec<String> = symbols
        .iter()
        .map(|s| format!("publicTrade.{}", s))
        .collect();

    let mut backoff = 1u64;

    loop {
        match connect_ws(&topics, counter.clone()).await {
            Ok(_) => {
                info!("WebSocket Bybit encerrou normalmente, reconectando...");
            }
            Err(e) => {
                error!("Erro no WebSocket Bybit: {:#}", e);
            }
        }

        warn!("Reconectando em {}s...", backoff);
        tokio::time::sleep(Duration::from_secs(backoff)).await;
        backoff = (backoff * 2).min(MAX_BACKOFF_SECS);
    }
}

async fn connect_ws(topics: &[String], counter: Arc<TradeCounter>) -> Result<()> {
    let (ws_stream, _) = connect_async(WS_URL).await?;
    info!("WebSocket Bybit conectado: {}", WS_URL);

    let (mut write, mut read) = ws_stream.split();

    // Subscreve aos tópicos em lote
    let subscribe_msg = serde_json::json!({
        "op": "subscribe",
        "args": topics
    });
    write
        .send(Message::Text(subscribe_msg.to_string()))
        .await?;
    info!("Subscrito a {} tópicos", topics.len());

    // Ping heartbeat a cada 20s para manter conexão ativa
    let mut ping_interval = tokio::time::interval(Duration::from_secs(20));

    loop {
        tokio::select! {
            msg = read.next() => {
                match msg {
                    Some(Ok(Message::Text(text))) => {
                        handle_message(&text, &counter);
                    }
                    Some(Ok(Message::Ping(data))) => {
                        write.send(Message::Pong(data)).await.ok();
                    }
                    Some(Ok(Message::Close(_))) => {
                        warn!("Servidor Bybit fechou conexão WebSocket");
                        break;
                    }
                    Some(Err(e)) => {
                        return Err(e.into());
                    }
                    None => {
                        warn!("Stream WebSocket encerrado");
                        break;
                    }
                    _ => {}
                }
            }
            _ = ping_interval.tick() => {
                write.send(Message::Text(r#"{"op":"ping"}"#.to_string())).await.ok();
                counter.reset_stale();
            }
        }
    }

    Ok(())
}

fn handle_message(text: &str, counter: &TradeCounter) {
    let Ok(msg) = serde_json::from_str::<WsMessage>(text) else {
        return;
    };

    let Some(topic) = msg.topic else {
        return;
    };

    // topic formato: "publicTrade.BTCUSDT"
    if let Some(symbol) = topic.strip_prefix("publicTrade.") {
        if let Some(data) = msg.data {
            let trades = if data.is_array() {
                data.as_array().map(|a| a.len()).unwrap_or(0)
            } else {
                1
            };
            for _ in 0..trades {
                counter.increment(symbol);
            }
        }
    }
}
