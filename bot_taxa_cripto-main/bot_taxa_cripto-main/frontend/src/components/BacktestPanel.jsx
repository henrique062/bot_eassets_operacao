import { useState, useRef } from 'react';
import {
    FaArrowTrendUp,
    FaBolt,
    FaChartColumn,
    FaCircle,
    FaCircleXmark,
    FaClipboardList,
    FaRocket,
} from 'react-icons/fa6';
import { fetchBacktest } from '../services/api';

const PRESETS = [
    { label: 'Top Score', symbols: ['AWEUSDT', 'ENSOUSDT', 'DUSKUSDT', 'AXSUSDT', 'CYBERUSDT'] },
    { label: 'Majors', symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT'] },
];

export default function BacktestPanel({ exchange }) {
    const [symbol, setSymbol] = useState('BTCUSDT');
    const [capital, setCapital] = useState(1000);
    const [days, setDays] = useState(7);
    const [leverage, setLeverage] = useState(1);
    const [feeRate, setFeeRate] = useState(0.02);
    const [mode, setMode] = useState('sniping');
    const [entrySeconds, setEntrySeconds] = useState(30);
    const [exitSeconds, setExitSeconds] = useState(30);
    const [targetTakeProfitPct, setTargetTakeProfitPct] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [tradeSortBy, setTradeSortBy] = useState('id');
    const [tradeSortOrder, setTradeSortOrder] = useState('desc');
    const [tooltip, setTooltip] = useState(null);
    const chartRef = useRef(null);

    const runBacktest = () => {
        setLoading(true);
        setError('');
        setResult(null);
        const feeType = feeRate <= 0.03 ? 'maker' : 'taker';
        const tpVal = targetTakeProfitPct !== '' ? parseFloat(targetTakeProfitPct) : null;
        fetchBacktest(symbol, exchange, capital, days, leverage, feeType, mode, tpVal)
            .then(res => {
                if (res.success) {
                    setResult(res);
                } else {
                    setError(res.message || 'Erro no backtest');
                }
            })
            .catch(err => setError(err.message))
            .finally(() => setLoading(false));
    };

    const m = result?.metrics;

    // Sort trades
    const getSortedTrades = () => {
        if (!result?.trades) return [];
        const sorted = [...result.trades].sort((a, b) => {
            let aVal = a[tradeSortBy];
            let bVal = b[tradeSortBy];
            if (typeof aVal === 'string') {
                return tradeSortOrder === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            }
            return tradeSortOrder === 'asc' ? aVal - bVal : bVal - aVal;
        });
        return sorted;
    };

    const handleTradeSort = (key) => {
        if (tradeSortBy === key) {
            setTradeSortOrder(prev => prev === 'desc' ? 'asc' : 'desc');
        } else {
            setTradeSortBy(key);
            setTradeSortOrder('desc');
        }
    };

    const TRADE_COLS = [
        { key: 'id', label: '#' },
        { key: 'datetime', label: 'Data/Hora' },
        { key: 'direction', label: 'Direção' },
        { key: 'entryPrice', label: 'Entrada' },
        { key: 'exitPrice', label: 'Saída' },
        { key: 'fundingPnl', label: 'Funding' },
        { key: 'pricePnl', label: 'Preço P&L' },
        { key: 'pricePnlPct', label: 'Preço P&L %' },
        { key: 'feeCost', label: 'Fees' },
        { key: 'totalPnl', label: 'Total P&L' },
        { key: 'equityAfter', label: 'Capital' },
    ];

    // SVG Equity Curve with drawdown & tooltip
    function renderEquityCurve() {
        const curve = result?.equityCurve;
        if (!curve || curve.length < 2) return null;

        const w = 700, h = 200, pad = 40;
        const initialCapital = result.config.capital;
        const values = curve.map(p => p.equity);
        const minVal = Math.min(...values, initialCapital) * 0.998;
        const maxVal = Math.max(...values, initialCapital) * 1.002;
        const range = maxVal - minVal || 1;

        const points = curve.map((p, i) => {
            const x = pad + (i / (curve.length - 1)) * (w - pad * 2);
            const y = pad + (1 - (p.equity - minVal) / range) * (h - pad * 2);
            return { x, y, equity: p.equity, datetime: p.datetime };
        });

        const capitalY = pad + (1 - (initialCapital - minVal) / range) * (h - pad * 2);
        
        let linePath = `M${points[0].x},${points[0].y}`;
        for (let i = 1; i < points.length; i++) {
            // Desenha reta horizontal até o tempo do próximo ponto, depois reta vertical até o novo valor
            linePath += ` L${points[i].x},${points[i - 1].y} L${points[i].x},${points[i].y}`;
        }
        
        const fullAreaPath = linePath + ` L${points[points.length - 1].x},${h - pad} L${points[0].x},${h - pad} Z`;

        const gridLines = 4;
        const grids = [];
        for (let i = 0; i <= gridLines; i++) {
            const y = pad + (i / gridLines) * (h - pad * 2);
            const val = maxVal - (i / gridLines) * range;
            grids.push({ y, label: `$${val.toFixed(0)}` });
        }

        const handleMouseMove = (e) => {
            const svg = chartRef.current;
            if (!svg) return;
            const rect = svg.getBoundingClientRect();
            const scaleX = w / rect.width;
            const mouseX = (e.clientX - rect.left) * scaleX;

            // Find closest point
            let closest = points[0];
            let minDist = Infinity;
            for (const p of points) {
                const dist = Math.abs(p.x - mouseX);
                if (dist < minDist) {
                    minDist = dist;
                    closest = p;
                }
            }
            setTooltip({
                x: closest.x,
                y: closest.y,
                equity: closest.equity,
                datetime: closest.datetime,
            });
        };

        const handleMouseLeave = () => setTooltip(null);

        return (
            <svg
                ref={chartRef}
                viewBox={`0 0 ${w} ${h}`}
                className="equity-chart"
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
                style={{ cursor: 'crosshair' }}
            >
                {grids.map((g, i) => (
                    <g key={i}>
                        <line x1={pad} y1={g.y} x2={w - pad} y2={g.y} stroke="rgba(255,255,255,0.06)" />
                        <text x={pad - 5} y={g.y + 4} textAnchor="end" fill="rgba(255,255,255,0.3)" fontSize="10">{g.label}</text>
                    </g>
                ))}

                <defs>
                    <linearGradient id="eqGradGreen" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#00e68a" stopOpacity="0.3" />
                        <stop offset="100%" stopColor="#00e68a" stopOpacity="0" />
                    </linearGradient>
                    <linearGradient id="eqGradRed" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#ff4d6a" stopOpacity="0" />
                        <stop offset="100%" stopColor="#ff4d6a" stopOpacity="0.3" />
                    </linearGradient>
                    <clipPath id="clipAbove">
                        <rect x={pad} y={0} width={w - pad * 2} height={capitalY} />
                    </clipPath>
                    <clipPath id="clipBelow">
                        <rect x={pad} y={capitalY} width={w - pad * 2} height={h - capitalY} />
                    </clipPath>
                </defs>

                {/* Capital initial line */}
                <line x1={pad} y1={capitalY} x2={w - pad} y2={capitalY} stroke="rgba(255,255,255,0.2)" strokeDasharray="4,4" />
                <text x={w - pad + 3} y={capitalY + 3} fill="rgba(255,255,255,0.25)" fontSize="8">Capital</text>

                {/* Green area above capital */}
                <path d={fullAreaPath} fill="url(#eqGradGreen)" clipPath="url(#clipAbove)" />
                {/* Red area below capital */}
                <path d={fullAreaPath} fill="url(#eqGradRed)" clipPath="url(#clipBelow)" />
                {/* Line coloring */}
                <path d={linePath} fill="none" stroke="#00e68a" strokeWidth="2" clipPath="url(#clipAbove)" />
                <path d={linePath} fill="none" stroke="#ff4d6a" strokeWidth="2" clipPath="url(#clipBelow)" />

                {/* Start/End labels */}
                <text x={points[0].x} y={h - 8} textAnchor="start" fill="rgba(255,255,255,0.4)" fontSize="9">
                    {curve[0].datetime}
                </text>
                <text x={points[points.length - 1].x} y={h - 8} textAnchor="end" fill="rgba(255,255,255,0.4)" fontSize="9">
                    {curve[curve.length - 1].datetime}
                </text>

                {/* Tooltip crosshair & balloon */}
                {tooltip && (
                    <g>
                        {/* Vertical line */}
                        <line x1={tooltip.x} y1={pad} x2={tooltip.x} y2={h - pad} stroke="rgba(255,255,255,0.3)" strokeDasharray="3,3" />
                        {/* Dot */}
                        <circle cx={tooltip.x} cy={tooltip.y} r="4" fill={tooltip.equity >= initialCapital ? '#00e68a' : '#ff4d6a'} stroke="#fff" strokeWidth="1.5" />
                        {/* Tooltip background */}
                        <rect
                            x={tooltip.x > w / 2 ? tooltip.x - 120 : tooltip.x + 8}
                            y={Math.max(pad, tooltip.y - 28)}
                            width="112"
                            height="36"
                            rx="4"
                            fill="rgba(10,15,30,0.92)"
                            stroke="rgba(255,255,255,0.15)"
                        />
                        <text
                            x={tooltip.x > w / 2 ? tooltip.x - 115 : tooltip.x + 13}
                            y={Math.max(pad, tooltip.y - 28) + 14}
                            fill={tooltip.equity >= initialCapital ? '#00e68a' : '#ff4d6a'}
                            fontSize="11"
                            fontWeight="bold"
                        >
                            ${tooltip.equity.toFixed(2)}
                        </text>
                        <text
                            x={tooltip.x > w / 2 ? tooltip.x - 115 : tooltip.x + 13}
                            y={Math.max(pad, tooltip.y - 28) + 28}
                            fill="rgba(255,255,255,0.5)"
                            fontSize="8"
                        >
                            {tooltip.datetime}
                        </text>
                    </g>
                )}
            </svg>
        );
    }

    return (
        <div className="backtest-panel">
            <div className="backtest-header">
                <div>
                    <h2 className="icon-inline">
                        <FaChartColumn aria-hidden="true" />
                        Backtester — Funding Rate Sniping
                    </h2>
                    <p className="backtest-subtitle">Simula a estratégia de abrir posição antes do settlement e fechar logo após</p>
                </div>
            </div>

            {/* Configuração */}
            <div className="backtest-config">
                {/* Mode Toggle */}
                <div style={{ marginBottom: 12 }}>
                    <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, display: 'block', marginBottom: 6 }}>Modo de Simulação</label>
                    <div className="mode-toggle">
                        <button className={`mode-btn ${mode === 'sniping' ? 'active' : ''}`} onClick={() => setMode('sniping')}>
                            <span className="icon-inline">
                                <FaBolt aria-hidden="true" />
                                Sniping 30s
                            </span>
                        </button>
                        <button className={`mode-btn ${mode === 'normal' ? 'active' : ''}`} onClick={() => setMode('normal')}>
                            <span className="icon-inline">
                                <FaArrowTrendUp aria-hidden="true" />
                                Normal (Klines)
                            </span>
                        </button>
                    </div>
                    <p style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>
                        {mode === 'sniping'
                            ? 'Abre 30s antes, fecha 30s depois. Variação de preço ≈ 0. P&L = Funding - Fees.'
                            : 'Usa velas 1h/4h para calcular variação de preço real entre entrada e saída.'}
                    </p>
                </div>

                <div className="config-row">
                    <div className="config-field">
                        <label>Par</label>
                        <input type="text" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} placeholder="BTCUSDT" />
                    </div>
                    <div className="config-field">
                        <label>Capital ($)</label>
                        <input type="number" value={capital} onChange={e => setCapital(Number(e.target.value))} min={10} />
                    </div>
                    <div className="config-field">
                        <label>Período</label>
                        <select value={days} onChange={e => setDays(Number(e.target.value))}>
                            <option value={1}>1 dia</option>
                            <option value={7}>7 dias</option>
                            <option value={14}>14 dias</option>
                            <option value={30}>30 dias</option>
                            <option value={60}>60 dias</option>
                            <option value={90}>90 dias</option>
                        </select>
                    </div>
                    <div className="config-field">
                        <label>Alavancagem</label>
                        <select value={leverage} onChange={e => setLeverage(Number(e.target.value))}>
                            {[1, 2, 3, 5, 10].map(l => <option key={l} value={l}>{l}x</option>)}
                        </select>
                    </div>
                    <div className="config-field">
                        <label>Fee (%)</label>
                        <input
                            type="number"
                            value={feeRate}
                            onChange={e => setFeeRate(Number(e.target.value))}
                            min={0}
                            max={1}
                            step={0.01}
                        />
                    </div>
                </div>

                {/* Entry/Exit seconds */}
                <div className="config-row" style={{ marginTop: 8 }}>
                    <div className="config-field">
                        <label>Entrada (seg antes)</label>
                        <input type="number" value={entrySeconds} onChange={e => setEntrySeconds(Number(e.target.value))} min={1} max={300} />
                    </div>
                    <div className="config-field">
                        <label>Saída (seg depois)</label>
                        <input type="number" value={exitSeconds} onChange={e => setExitSeconds(Number(e.target.value))} min={1} max={300} />
                    </div>
                    <div className="config-field">
                        <label>Take Profit (%)</label>
                        <input type="number" value={targetTakeProfitPct} onChange={e => setTargetTakeProfitPct(e.target.value)} min={0} step={0.01} placeholder="Opcional" />
                    </div>
                </div>

                <div className="config-presets">
                    {PRESETS.map((p, i) => (
                        <div key={i} className="preset-group">
                            <span className="preset-label">{p.label}:</span>
                            {p.symbols.map(s => (
                                <button key={s} className={`preset-btn ${symbol === s ? 'active' : ''}`} onClick={() => setSymbol(s)}>{s.replace('USDT', '')}</button>
                            ))}
                        </div>
                    ))}
                </div>

                <button className={`backtest-run-btn ${loading ? 'loading' : ''}`} onClick={runBacktest} disabled={loading}>
                    {loading ? (
                        <>
                            <span className="spinner-small" />
                            Simulando...
                        </>
                    ) : (
                        <span className="icon-inline">
                            <FaRocket aria-hidden="true" />
                            {`Rodar Backtest (${mode === 'sniping' ? 'Sniping 30s' : 'Normal'})`}
                        </span>
                    )}
                </button>
            </div>

            {error && (
                <div className="backtest-error">
                    <FaCircleXmark aria-hidden="true" /> {error}
                </div>
            )}

            {loading && (
                <div className="ai-loading">
                    <div className="ai-loading-bar"><div className="ai-loading-progress" /></div>
                    <p>Rodando simulação {mode === 'sniping' ? 'Sniping 30s' : 'Normal'} de {days} dia(s) para {symbol}...</p>
                </div>
            )}

            {/* Resultados */}
            {m && (
                <div className="backtest-results">
                    {/* Badge de modo */}
                    <div style={{ marginBottom: 12 }}>
                        <span className={`mode-badge ${mode === 'sniping' ? 'sniping' : 'normal'}`}>
                            {mode === 'sniping' ? (
                                <span className="icon-inline">
                                    <FaBolt aria-hidden="true" /> Modo Sniping 30s
                                </span>
                            ) : (
                                <span className="icon-inline">
                                    <FaArrowTrendUp aria-hidden="true" /> Modo Normal
                                </span>
                            )}
                        </span>
                    </div>

                    {/* Cards de métricas */}
                    <div className="backtest-metrics">
                        <div className={`metric-card ${m.totalPnl >= 0 ? 'profit' : 'loss'}`}>
                            <span className="metric-label">P&L Total</span>
                            <span className="metric-value">{m.totalPnl >= 0 ? '+' : ''}${m.totalPnl.toFixed(2)}</span>
                            <span className="metric-sub">{m.totalPnlPct >= 0 ? '+' : ''}{m.totalPnlPct.toFixed(2)}%</span>
                        </div>
                        <div className="metric-card">
                            <span className="metric-label">Trades</span>
                            <span className="metric-value">{m.totalTrades}</span>
                            <span className="metric-sub">{m.wins}W / {m.losses}L</span>
                        </div>
                        <div className="metric-card">
                            <span className="metric-label">Win Rate</span>
                            <span className="metric-value">{m.winRate.toFixed(1)}%</span>
                            <span className="metric-sub">de acerto</span>
                        </div>
                        <div className="metric-card">
                            <span className="metric-label">Retorno Mensal</span>
                            <span className="metric-value">{m.monthlyReturn >= 0 ? '+' : ''}{m.monthlyReturn.toFixed(1)}%</span>
                            <span className="metric-sub">projetado</span>
                        </div>
                        <div className="metric-card">
                            <span className="metric-label">Max Drawdown</span>
                            <span className="metric-value">-{m.maxDrawdown.toFixed(2)}%</span>
                            <span className="metric-sub">pior queda</span>
                        </div>
                        <div className="metric-card">
                            <span className="metric-label">Funding vs Preço</span>
                            <span className="metric-value positive">+${m.totalFundingReceived.toFixed(2)}</span>
                            <span className="metric-sub">{m.totalPricePnl >= 0 ? '+' : ''}${m.totalPricePnl.toFixed(2)} preço | -${m.totalFeesPaid.toFixed(2)} fees</span>
                        </div>
                    </div>

                    {/* Equity Curve */}
                    <div className="equity-section">
                        <h3 className="icon-inline">
                            <FaArrowTrendUp aria-hidden="true" />
                            Curva de Capital
                        </h3>
                        <div className="equity-info">
                            <span>${result.config.capital.toFixed(0)} → <strong>${m.finalEquity.toFixed(2)}</strong></span>
                        </div>
                        {renderEquityCurve()}
                    </div>

                    {/* Trade Log — sortable */}
                    <div className="trade-log-section">
                        <h3 className="icon-inline">
                            <FaClipboardList aria-hidden="true" />
                            Histórico de Trades ({m.totalTrades})
                        </h3>
                        <div className="trade-log-scroll">
                            <table className="trade-log-table">
                                <thead>
                                    <tr>
                                        {TRADE_COLS.map(col => (
                                            <th
                                                key={col.key}
                                                className="sortable"
                                                onClick={() => handleTradeSort(col.key)}
                                                style={{ cursor: 'pointer' }}
                                            >
                                                {col.label}
                                                {tradeSortBy === col.key && (
                                                    <span className="sort-arrow">{tradeSortOrder === 'desc' ? ' ▼' : ' ▲'}</span>
                                                )}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {getSortedTrades().map(t => (
                                        <tr key={t.id} className={t.totalPnl >= 0 ? 'trade-win' : 'trade-loss'}>
                                            <td>{t.id}</td>
                                            <td>{t.datetime}</td>
                                            <td>
                                                <span className={`direction-badge ${t.direction === 'SHORT' ? 'dir-short' : 'dir-long'}`}>
                                                    <FaCircle aria-hidden="true" /> {t.direction}
                                                </span>
                                            </td>
                                            <td>${t.entryPrice}</td>
                                            <td>${t.exitPrice}</td>
                                            <td className="positive">+${t.fundingPnl.toFixed(4)}</td>
                                            <td className={t.pricePnl >= 0 ? 'positive' : 'negative'}>
                                                {t.pricePnl >= 0 ? '+' : ''}${t.pricePnl.toFixed(4)}
                                            </td>
                                            <td className={t.pricePnlPct >= 0 ? 'positive' : 'negative'}>
                                                {t.pricePnlPct >= 0 ? '+' : ''}{(t.pricePnlPct || 0).toFixed(4)}%
                                            </td>
                                            <td className="negative">-${t.feeCost.toFixed(4)}</td>
                                            <td className={t.totalPnl >= 0 ? 'positive' : 'negative'}>
                                                <strong>{t.totalPnl >= 0 ? '+' : ''}${t.totalPnl.toFixed(4)}</strong>
                                                <br /><small>{t.totalPnlPct >= 0 ? '+' : ''}{t.totalPnlPct.toFixed(4)}%</small>
                                            </td>
                                            <td>${t.equityAfter.toFixed(2)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
