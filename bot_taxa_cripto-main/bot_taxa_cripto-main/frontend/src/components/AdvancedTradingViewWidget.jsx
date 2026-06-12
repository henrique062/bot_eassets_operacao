import { useEffect, useMemo, useRef, useState } from 'react';

const EMBED_SCRIPT_SRC = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';

function normalizeSymbol(raw) {
  const clean = String(raw || '')
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '');
  if (!clean) return '';
  return clean.endsWith('USDT') ? clean : `${clean}USDT`;
}

function toTvSymbol(exchange, symbol) {
  const normalized = normalizeSymbol(symbol);
  if (!normalized) return '';
  const ex = String(exchange || 'binance').toLowerCase();
  const prefix = ex === 'bybit' ? 'BYBIT' : 'BINANCE';
  return `${prefix}:${normalized}.P`;
}

function toTvInterval(interval) {
  const map = {
    '1m': '1',
    '15m': '15',
    '1h': '60',
    '4h': '240',
    '8h': '480',
    '1d': 'D',
  };
  return map[String(interval || '').toLowerCase()] || '1';
}

export default function AdvancedTradingViewWidget({
  symbol,
  exchange = 'binance',
  interval = '1m',
}) {
  // containerRef aponta para o div já no DOM — o script do TradingView encontra dimensões reais
  const containerRef = useRef(null);
  const [loading, setLoading] = useState(true);

  const tvSymbol = useMemo(() => toTvSymbol(exchange, symbol), [exchange, symbol]);
  const tvInterval = useMemo(() => toTvInterval(interval), [interval]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !tvSymbol) return;

    setLoading(true);
    container.querySelectorAll('script').forEach(s => s.remove());
    const widgetDiv = container.querySelector('.tradingview-widget-container__widget');
    if (widgetDiv) widgetDiv.innerHTML = '';

    const script = document.createElement('script');
    script.src = EMBED_SCRIPT_SRC;
    script.async = true;
    script.type = 'text/javascript';
    script.text = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval: tvInterval,
      timezone: 'America/Sao_Paulo',
      theme: 'dark',
      style: '1',
      locale: 'br',
      hide_top_toolbar: false,
      hide_side_toolbar: false,
      withdateranges: false,
      allow_symbol_change: true,
      save_image: true,
      studies: [],
      details: false,
      hotlist: false,
      calendar: false,
      disabled_features: ['legend_widget'],
      enabled_features: ['left_toolbar', 'header_symbol_search'],
      support_host: 'https://www.tradingview.com',
    });
    script.onload = () => setLoading(false);
    container.appendChild(script);

    const doneTimer = setTimeout(() => setLoading(false), 1800);

    return () => {
      clearTimeout(doneTimer);
      container.querySelectorAll('script').forEach(s => s.remove());
      const wd = container.querySelector('.tradingview-widget-container__widget');
      if (wd) wd.innerHTML = '';
    };
  }, [tvSymbol, tvInterval]);

  return (
    // tv-advanced-shell usa position: absolute; inset: 0 no CSS — preenche manual-op-chart-wrap
    // sem depender de cadeias de height: 100% em flex containers
    <div className="tv-advanced-shell">
      {loading && <div className="tv-advanced-loading">Carregando TradingView Advanced...</div>}
      {/* tradingview-widget-container também usa position: absolute; inset: 0 via CSS */}
      <div
        ref={containerRef}
        className="tradingview-widget-container"
      >
        <div className="tradingview-widget-container__widget" />
      </div>
    </div>
  );
}
