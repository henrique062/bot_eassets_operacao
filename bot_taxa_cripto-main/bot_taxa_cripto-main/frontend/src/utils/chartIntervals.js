export const CHART_INTERVAL_OPTIONS = [
  { value: '1m', label: '1m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' },
  { value: '4h', label: '4h' },
  { value: '8h', label: '8h' },
  { value: '1d', label: '1d' },
];

const LIMIT_BY_INTERVAL = {
  '1m': 360,
  '15m': 320,
  '1h': 300,
  '4h': 260,
  '8h': 240,
  '1d': 200,
};

const REFRESH_MS_BY_INTERVAL = {
  '1m': 1500,
  '15m': 3000,
  '1h': 5000,
  '4h': 8000,
  '8h': 10000,
  '1d': 15000,
};

export function getKlineLimitForInterval(interval) {
  return LIMIT_BY_INTERVAL[interval] || 500;
}

export function getRefreshMsForInterval(interval) {
  return REFRESH_MS_BY_INTERVAL[interval] || 15000;
}

export function resolveChartInterval(exchange, requestedInterval) {
  const ex = String(exchange || 'binance').toLowerCase();
  let apiInterval = requestedInterval;
  let hint = '';

  if (ex === 'bybit' && requestedInterval === '8h') {
    apiInterval = '4h';
    hint = 'Bybit não possui kline 8h nativo; usando 4h.';
  }

  return { apiInterval, hint };
}

// Mapeia o intervalo do app para o formato WebSocket de cada exchange
const BYBIT_WS_INTERVAL = {
  '1m': '1', '15m': '15', '1h': '60', '4h': '240', '8h': '480', '1d': 'D',
};

export function toWsInterval(exchange, interval) {
  if (String(exchange).toLowerCase() === 'bybit') {
    return BYBIT_WS_INTERVAL[interval] || interval;
  }
  // Binance usa o mesmo formato da REST API
  return interval;
}
