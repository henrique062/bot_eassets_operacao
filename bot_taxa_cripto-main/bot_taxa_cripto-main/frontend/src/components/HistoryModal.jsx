import { useState, useEffect, useCallback } from 'react';
import {
    FaChartLine,
    FaCircle,
    FaCoins,
    FaScaleBalanced,
    FaXmark,
} from 'react-icons/fa6';
import { fetchHistory, fetchLSR, fetchKlines } from '../services/api';
import TradingViewChart from './TradingViewChart';
import {
    CHART_INTERVAL_OPTIONS,
    getKlineLimitForInterval,
    getRefreshMsForInterval,
    resolveChartInterval,
} from '../utils/chartIntervals';

function toGMT3(ts) {
    if (!ts) return '—';
    const d = new Date(Number(ts));
    return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', hour12: false });
}

function toGMT3Short(ts) {
    if (!ts) return '';
    const d = new Date(Number(ts));
    return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function HistoryModal({ symbol, exchange, onClose }) {
    const [tab, setTab] = useState('price');
    const [history, setHistory] = useState([]);
    const [lsr, setLsr] = useState([]);
    const [klines, setKlines] = useState([]);
    const [chartInterval, setChartInterval] = useState('1h');
    const [loading, setLoading] = useState(true);
    const { apiInterval, hint: intervalHint } = resolveChartInterval(exchange, chartInterval);
    const liveUpdateHint = [
        intervalHint,
        `Atualização ao vivo: ${Math.round(getRefreshMsForInterval(chartInterval) / 1000)}s.`,
    ].filter(Boolean).join(' ');

    const loadKlines = useCallback(async () => {
        try {
            const res = await fetchKlines(symbol, exchange, apiInterval, getKlineLimitForInterval(chartInterval));
            setKlines(res.data || []);
        } catch {
            // Mantém último estado em falhas transitórias.
        }
    }, [symbol, exchange, apiInterval, chartInterval]);

    const loadData = useCallback(() => {
        setLoading(true);
        const promises = [
            fetchHistory(symbol, exchange, 50).then(r => setHistory(r.data || [])).catch(() => { }),
            fetchLSR(symbol, exchange, '1h', 30).then(r => setLsr(r.data || [])).catch(() => { }),
            loadKlines(),
        ];

        Promise.all(promises).finally(() => setLoading(false));
    }, [symbol, exchange, loadKlines]);

    useEffect(() => { loadData(); }, [loadData]);

    useEffect(() => {
        if (tab !== 'price') return;

        loadKlines();
        const refreshMs = getRefreshMsForInterval(chartInterval);
        const id = setInterval(() => {
            loadKlines();
        }, refreshMs);
        return () => clearInterval(id);
    }, [loadKlines, chartInterval, tab]);

    // Price Chart SVG
    function renderPriceChart() {
        if (!klines.length) return <div className="chart-empty">Sem dados de preço</div>;

        const closes = klines.map(k => k.close);
        const priceChange = closes[closes.length - 1] - closes[0];
        const priceChangePct = (priceChange / closes[0]) * 100;

        return (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <div className="price-chart-header" style={{ flexShrink: 0 }}>
                    <span className="price-current">${closes[closes.length - 1].toLocaleString('en-US', { maximumFractionDigits: 6 })}</span>
                    <span className={`price-change ${priceChange >= 0 ? 'positive' : 'negative'}`}>
                        {priceChange >= 0 ? '+' : ''}{priceChangePct.toFixed(2)}%
                    </span>
                </div>
                <div style={{ flex: 1, minHeight: '300px', width: '100%', position: 'relative' }}>
                    <TradingViewChart
                        data={klines}
                        interval={chartInterval}
                        onIntervalChange={setChartInterval}
                        intervalOptions={CHART_INTERVAL_OPTIONS}
                        intervalHint={liveUpdateHint}
                        fitKey={symbol}
                        symbol={symbol}
                        exchange={exchange}
                    />
                </div>
            </div>
        );
    }

    // Funding Rate Chart
    function renderFundingChart() {
        if (!history.length) return <div className="chart-empty">Sem dados</div>;
        const sorted = [...history].reverse();
        const w = 660, h = 180, pad = 50;
        const vals = sorted.map(h => h.fundingRatePercent);
        const maxVal = Math.max(...vals.map(Math.abs)) * 1.2 || 0.01;
        const midY = h / 2;

        return (
            <svg viewBox={`0 0 ${w} ${h}`} className="modal-chart">
                <line x1={pad} y1={midY} x2={w - pad} y2={midY} stroke="rgba(255,255,255,0.1)" />
                {sorted.map((item, i) => {
                    const x = pad + (i / (sorted.length - 1 || 1)) * (w - pad * 2);
                    const barH = (item.fundingRatePercent / maxVal) * (midY - 20);
                    const color = item.fundingRatePercent >= 0 ? '#00e68a' : '#ff4d6a';
                    return (
                        <rect key={i} x={x - 3} y={barH >= 0 ? midY - barH : midY} width={6} height={Math.abs(barH)}
                            fill={color} opacity="0.7" rx="2" />
                    );
                })}
            </svg>
        );
    }

    // LSR Section
    function renderLSR() {
        if (!lsr.length) return <div className="chart-empty">Sem dados de LSR</div>;
        const latest = lsr[0];

        return (
            <div>
                <div className="lsr-bar-container">
                    <div className="lsr-bar">
                        <div className="lsr-bar-long" style={{ width: `${latest.longAccount}%` }}>
                            <FaCircle aria-hidden="true" /> Long {latest.longAccount.toFixed(1)}%
                        </div>
                        <div className="lsr-bar-short" style={{ width: `${latest.shortAccount}%` }}>
                            <FaCircle aria-hidden="true" /> Short {latest.shortAccount.toFixed(1)}%
                        </div>
                    </div>
                </div>
                <div className="modal-stats" style={{ padding: '0 24px 16px' }}>
                    <div className="modal-stat-card">
                        <span className="modal-stat-label">Ratio</span>
                        <span className="modal-stat-value">{latest.longShortRatio.toFixed(2)}</span>
                    </div>
                    <div className="modal-stat-card">
                        <span className="modal-stat-label">Sentimento</span>
                        <span className="modal-stat-value icon-inline">
                            <FaCircle aria-hidden="true" />
                            {latest.longShortRatio > 1 ? 'Bullish' : 'Bearish'}
                        </span>
                    </div>
                </div>
                <table className="modal-table" style={{ margin: '0 24px', width: 'calc(100% - 48px)' }}>
                    <thead>
                        <tr><th>Data/Hora (GMT-3)</th><th>Ratio</th><th>Long %</th><th>Short %</th></tr>
                    </thead>
                    <tbody>
                        {lsr.slice(0, 15).map((item, i) => (
                            <tr key={i}>
                                <td>{toGMT3Short(item.timestamp)}</td>
                                <td>{item.longShortRatio.toFixed(2)}</td>
                                <td className="positive">{item.longAccount.toFixed(1)}%</td>
                                <td className="negative">{item.shortAccount.toFixed(1)}%</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    }

    return (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
            <div className="modal-content">
                <div className="modal-header">
                    <h2>{symbol}</h2>
                    <button className="modal-close" onClick={onClose}>
                        <FaXmark aria-hidden="true" />
                    </button>
                </div>

                <div className="modal-tabs">
                    <button className={`modal-tab ${tab === 'price' ? 'active' : ''}`} onClick={() => setTab('price')}>
                        <span className="icon-inline">
                            <FaChartLine aria-hidden="true" />
                            Preço
                        </span>
                    </button>
                    <button className={`modal-tab ${tab === 'funding' ? 'active' : ''}`} onClick={() => setTab('funding')}>
                        <span className="icon-inline">
                            <FaCoins aria-hidden="true" />
                            Funding Rate
                        </span>
                    </button>
                    <button className={`modal-tab ${tab === 'lsr' ? 'active' : ''}`} onClick={() => setTab('lsr')}>
                        <span className="icon-inline">
                            <FaScaleBalanced aria-hidden="true" />
                            Long/Short
                        </span>
                    </button>
                </div>

                <div className="modal-body" style={{ padding: tab === 'lsr' ? '16px 0' : '16px 24px' }}>
                    {loading ? (
                        <div className="chart-empty"><span className="spinner-small" /> Carregando...</div>
                    ) : (
                        <>
                            {tab === 'price' && renderPriceChart()}
                            {tab === 'funding' && (
                                <>
                                    {renderFundingChart()}
                                    <table className="modal-table">
                                        <thead>
                                            <tr><th>Data/Hora (GMT-3)</th><th>Taxa</th></tr>
                                        </thead>
                                        <tbody>
                                            {history.slice(0, 20).map((item, i) => (
                                                <tr key={i}>
                                                    <td>{toGMT3(item.fundingRateTimestamp)}</td>
                                                    <td className={item.fundingRatePercent >= 0 ? 'positive' : 'negative'}>
                                                        {item.fundingRatePercent >= 0 ? '+' : ''}{item.fundingRatePercent.toFixed(4)}%
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </>
                            )}
                            {tab === 'lsr' && renderLSR()}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
