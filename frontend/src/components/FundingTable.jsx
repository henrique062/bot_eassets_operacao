import { useState, useEffect, useCallback } from 'react';
import { FaArrowRotateRight, FaCircle, FaTableList } from 'react-icons/fa6';
import { fetchFundingRates, fetchBatchLSR } from '../services/api';

const PAGE_SIZE = 20;
const INTERVAL_FILTERS = [
    { value: 'all', label: 'Todos' },
    { value: '1', label: '1h' },
    { value: '4', label: '4h' },
    { value: '8', label: '8h' },
];

const COLUMNS = [
    { key: 'symbol', label: 'Par', sortable: true, tooltip: 'Par de contrato perpétuo da corretora' },
    { key: 'score', label: 'Score', sortable: true, format: 'score', tooltip: 'Força de confirmação do radar calculada pelo motor' },
    { key: 'fundingRatePercent', label: 'Funding Rate', sortable: true, format: 'rate', tooltip: 'Valor real da taxa recebida a cada ciclo' },
    { key: 'fundingInterval', label: 'Intervalo', sortable: true, format: 'interval', tooltip: 'Quantas horas faltam para fechar o ciclo da moeda' },
    { key: 'direction', label: 'Sinal', sortable: true, format: 'signal', tooltip: 'Operação sugerida pelo Radar (comprar/vender)' },
    { key: 'estimatedProfit', label: 'Lucro/Período', sortable: true, format: 'profit', tooltip: 'Margem de lucro a ser lucrada na virada' },

    { key: 'lastPrice', label: 'Preço', sortable: true, format: 'price', tooltip: 'Último preço negociado' },
    { key: 'price24hPcnt', label: '24h %', sortable: true, format: 'change', tooltip: 'Variação do preço na janela diária' },
    { key: 'volume24h', label: 'Volume 24h', sortable: true, format: 'volume', tooltip: 'Volume negociado financeiro diário (Liquidez)' },
    { key: 'lsr', label: 'LSR', sortable: false, format: 'lsr', tooltip: 'Long/Short Ratio. Mostra sardinhas vs baleias' },
    { key: 'nextFundingTime', label: 'Próx. Funding', sortable: true, format: 'time', tooltip: 'Tempo exato atualizado a cada segundo para o settlement' },
];

// Componente interno para exibir countdown em tempo real
function LiveCountdown({ targetTime }) {
    const [timeLeft, setTimeLeft] = useState('');

    useEffect(() => {
        if (!targetTime) {
            setTimeLeft('—');
            return;
        }

        const updateClock = () => {
            const date = new Date(Number(targetTime));
            const now = new Date();
            const diff = date - now;

            if (diff <= 0) {
                if (Math.abs(diff) < 10 * 60000) setTimeLeft('Agora');
                else setTimeLeft('—');
                return;
            }

            const h = Math.floor(diff / 3600000);
            const m = Math.floor((diff % 3600000) / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            
            // Formatando com zeros à esquerda
            const pad = (num) => String(num).padStart(2, '0');
            setTimeLeft(`${pad(h)}h ${pad(m)}m ${pad(s)}s`);
        };

        updateClock();
        const interval = setInterval(updateClock, 1000);
        return () => clearInterval(interval);
    }, [targetTime]);

    return <span>{timeLeft}</span>;
}

function formatValue(value, format) {
    if (value === null || value === undefined) return '—';

    switch (format) {
        case 'rate': {
            const num = Number(value);
            return `${num >= 0 ? '+' : ''}${num.toFixed(4)}%`;
        }
        case 'interval':
            return `${Number(value)}h`;
        case 'profit': {
            const num = Number(value);
            if (num === 0) return '—';
            return `+${num.toFixed(4)}%`;
        }
        case 'monthly':
            return '';
        case 'price': {
            const num = Number(value);
            if (num >= 1000) return '$' + num.toLocaleString('en-US', { maximumFractionDigits: 2 });
            if (num >= 1) return '$' + num.toFixed(4);
            if (num === 0) return '—';
            return '$' + num.toPrecision(4);
        }
        case 'change': {
            const num = Number(value);
            if (num === 0) return '—';
            return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
        }
        case 'volume': {
            const num = Number(value);
            if (num === 0) return '—';
            if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
            if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
            if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
            return num.toFixed(0);
        }
        case 'time': {
            // Este caso de formatação não será mais usado diretamente no JSX
            // (substituído pelo LiveCountdown para ser re-renderizado a cada segundo)
            if (!value) return '—';
            return value;
        }
        default:
            return String(value);
    }
}

function getRateClass(value) {
    const num = Number(value);
    if (num > 0) return 'positive';
    if (num < 0) return 'negative';
    return 'neutral';
}

function stripEmojis(text) {
    if (typeof text !== 'string') return text;
    return text
        .replace(/\p{Extended_Pictographic}/gu, '')
        .replace(/\uFE0F/gu, '')
        .trim();
}

function getScoreInfo(scoreData) {
    if (!scoreData) return { score: 0, cls: 'score-evitar', label: '—', signal: '—' };
    const s = scoreData.score;
    const conf = scoreData.confidence;
    let cls = 'score-evitar';
    if (s >= 75) cls = 'score-forte';
    else if (s >= 50) cls = 'score-moderado';
    else if (s >= 30) cls = 'score-fraco';
    const rawSignal = scoreData.signal || scoreData.direction || '—';
    return { score: s, cls, label: conf, signal: stripEmojis(rawSignal) };
}

function getExchangeUrl(symbol, exchange) {
    if (exchange === 'bybit') {
        return `https://www.bybit.com/trade/usdt/${symbol}`;
    }
    return `https://www.binance.com/en/futures/${symbol}`;
}

export default function FundingTable({ exchange, onSelectSymbol }) {
    const [data, setData] = useState([]);
    const [lsrMap, setLsrMap] = useState({});
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [intervalFilter, setIntervalFilter] = useState('all');
    const [sortBy, setSortBy] = useState('score');
    const [sortOrder, setSortOrder] = useState('desc');
    const [page, setPage] = useState(0);
    const [scoringMode, setScoringMode] = useState('harvesting'); // 'harvesting' | 'counter_trend'

    // Função local para quando clica no símbolo
    const handleRowClick = (symbol) => {
        // Chamando prop original do painel pai 
        if (onSelectSymbol) onSelectSymbol(symbol);
    };

    const loadData = useCallback(() => {
        setLoading(true);
        fetchFundingRates(exchange, search, sortBy, sortOrder, scoringMode)
            .then(res => {
                const enriched = (res.data || []).map(item => ({
                    ...item,
                    estimatedProfit: Math.abs(item.fundingRatePercent),
                }));
                setData(enriched);
                setPage(0);
            })
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [exchange, search, sortBy, sortOrder, scoringMode]);

    const filteredData = intervalFilter === 'all'
        ? data
        : data.filter(item => Number(item.fundingInterval || 8) === Number(intervalFilter));
    const totalPages = Math.ceil(filteredData.length / PAGE_SIZE);
    const pagedData = filteredData.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

    // Fetch LSR for visible page
    useEffect(() => {
        const source = intervalFilter === 'all'
            ? data
            : data.filter(item => Number(item.fundingInterval || 8) === Number(intervalFilter));
        const pagedSymbols = source.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(d => d.symbol);
        if (pagedSymbols.length === 0) return;
        fetchBatchLSR(pagedSymbols, exchange)
            .then(res => setLsrMap(prev => ({ ...prev, ...res.data })))
            .catch(() => { });
    }, [data, page, exchange, intervalFilter]);

    useEffect(() => {
        setPage(0);
    }, [intervalFilter]);

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 60000);
        return () => clearInterval(interval);
    }, [loadData]);

    const handleSort = (key) => {
        if (key === 'direction' || key === 'estimatedProfit') key = 'fundingRate';
        if (sortBy === key) {
            setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc');
        } else {
            setSortBy(key);
            setSortOrder('desc');
        }
    };

    return (
        <div className="funding-table-container">
            <div className="table-header">
                <h2 className="icon-inline">
                    <FaTableList aria-hidden="true" />
                    Taxas de Financiamento
                </h2>
                <div className="table-controls">
                    <div style={{ display: 'flex', gap: '0', borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--border-color)', flexShrink: 0 }}>
                        <button
                            type="button"
                            onClick={() => setScoringMode('harvesting')}
                            aria-label="Modo Coleta de Taxa (Funding Harvesting)"
                            aria-pressed={scoringMode === 'harvesting'}
                            style={{
                                padding: '7px 14px',
                                fontSize: '0.8rem',
                                fontWeight: scoringMode === 'harvesting' ? '700' : '400',
                                background: scoringMode === 'harvesting' ? 'var(--accent-green)' : 'var(--bg-secondary)',
                                color: scoringMode === 'harvesting' ? '#000' : 'var(--text-secondary)',
                                border: 'none',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '5px',
                                transition: 'all 0.15s',
                            }}
                        >
                            Coleta de Taxa
                        </button>
                        <button
                            type="button"
                            onClick={() => setScoringMode('counter_trend')}
                            aria-label="Modo Counter-trend (Reversao)"
                            aria-pressed={scoringMode === 'counter_trend'}
                            style={{
                                padding: '7px 14px',
                                fontSize: '0.8rem',
                                fontWeight: scoringMode === 'counter_trend' ? '700' : '400',
                                background: scoringMode === 'counter_trend' ? '#8b5cf6' : 'var(--bg-secondary)',
                                color: scoringMode === 'counter_trend' ? '#fff' : 'var(--text-secondary)',
                                border: 'none',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '5px',
                                transition: 'all 0.15s',
                            }}
                        >
                            Counter-trend
                        </button>
                    </div>
                    <div className="interval-filter-group">
                        {INTERVAL_FILTERS.map(opt => (
                            <button
                                key={opt.value}
                                type="button"
                                className={`interval-filter-btn ${intervalFilter === opt.value ? 'active' : ''}`}
                                onClick={() => setIntervalFilter(opt.value)}
                            >
                                {opt.label}
                            </button>
                        ))}
                    </div>
                    <div className="search-box">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="11" cy="11" r="8" />
                            <path d="M21 21l-4.35-4.35" />
                        </svg>
                        <input type="text" placeholder="Buscar moeda..." value={search} onChange={e => setSearch(e.target.value)} />
                    </div>
                    <button className="refresh-btn" onClick={loadData} title="Atualizar" aria-label="Atualizar">
                        <FaArrowRotateRight aria-hidden="true" />
                    </button>
                </div>
            </div>

            <div className="table-scroll">
                <table className="funding-table">
                    <thead>
                        <tr>
                            <th className="rank-col">#</th>
                            {COLUMNS.map(col => {
                                const scoreTooltip = col.key === 'score'
                                    ? (scoringMode === 'harvesting'
                                        ? 'Score de Coleta: APY, Volume, Intervalo e Consistencia'
                                        : 'Score de Reversao: Extremidade, Persistencia, Volume e Volatilidade')
                                    : col.tooltip;

                                const scoreLabel = col.key === 'score'
                                    ? (
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                                            Score
                                            <span style={{
                                                fontSize: '0.6rem',
                                                fontWeight: '700',
                                                padding: '1px 5px',
                                                borderRadius: '4px',
                                                background: scoringMode === 'harvesting' ? 'var(--accent-green)' : '#8b5cf6',
                                                color: scoringMode === 'harvesting' ? '#000' : '#fff',
                                                lineHeight: '1.5',
                                            }}>
                                                {scoringMode === 'harvesting' ? 'Coleta' : 'Reversao'}
                                            </span>
                                        </span>
                                    )
                                    : col.label;

                                return (
                                    <th
                                        key={col.key}
                                        className={`${col.sortable ? 'sortable ' : ''}${col.tooltip ? 'has-tooltip' : ''}`}
                                        data-tooltip={scoreTooltip}
                                        onClick={() => col.sortable && handleSort(col.key)}
                                    >
                                        {scoreLabel}
                                        {(sortBy === col.key ||
                                            (col.key === 'direction' && sortBy === 'fundingRate') ||
                                            (col.key === 'estimatedProfit' && sortBy === 'fundingRate')
                                        ) && (
                                            <span className="sort-arrow">{sortOrder === 'desc' ? ' ▼' : ' ▲'}</span>
                                        )}
                                    </th>
                                );
                            })}
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            Array.from({ length: 10 }).map((_, i) => (
                                <tr key={i} className="skeleton-row">
                                    {Array.from({ length: COLUMNS.length + 1 }).map((_, j) => (
                                        <td key={j}><div className="skeleton-cell" /></td>
                                    ))}
                                </tr>
                            ))
                        ) : pagedData.length === 0 ? (
                            <tr>
                                <td colSpan={COLUMNS.length + 1} className="empty-state">
                                    Nenhum par encontrado{intervalFilter !== 'all' ? ` para taxa ${intervalFilter}h` : ''}
                                </td>
                            </tr>
                        ) : (
                            pagedData.map((row, i) => {
                                const rowLsr = lsrMap[row.symbol] || null;
                                const scoreInfo = getScoreInfo(row.scoreData);

                                return (
                                    <tr key={row.symbol} className="data-row" onClick={() => handleRowClick(row.symbol)}>
                                        <td className="rank-col">{page * PAGE_SIZE + i + 1}</td>
                                        {COLUMNS.map(col => {
                                            // === SCORE ===
                                            if (col.key === 'score') {
                                                return (
                                                    <td key={col.key}>
                                                        <div className={`score-badge ${scoreInfo.cls}`}>
                                                            <span className="score-number">{scoreInfo.score}</span>
                                                            <span className="score-label">{scoreInfo.label}</span>
                                                        </div>
                                                    </td>
                                                );
                                            }

                                            // === SINAL ===
                                            if (col.key === 'direction') {
                                                const sd = row.scoreData;
                                                if (!sd) return <td key={col.key}>—</td>;
                                                const dirClass = sd.shouldOpen
                                                    ? (sd.direction === 'SHORT' ? 'dir-short' : 'dir-long')
                                                    : 'dir-neutral';
                                                return (
                                                    <td key={col.key}>
                                                        <span className={`direction-badge ${dirClass}`}>
                                                            <FaCircle aria-hidden="true" />
                                                            {scoreInfo.signal}
                                                        </span>
                                                    </td>
                                                );
                                            }


                                            if (col.key === 'estimatedProfit') {
                                                const val = row.estimatedProfit;
                                                return <td key={col.key} className="profit-cell">{val ? `+${val.toFixed(4)}%` : '—'}</td>;
                                            }

                                            if (col.key === 'fundingInterval') {
                                                const hours = Number(row.fundingInterval || 8);
                                                return (
                                                    <td key={col.key}>
                                                        <span className={`interval-badge ${hours < 8 ? 'interval-fast' : ''}`}>{hours}h</span>
                                                    </td>
                                                );
                                            }

                                            if (col.key === 'lsr') {
                                                if (!rowLsr) return <td key={col.key} className="lsr-cell">—</td>;
                                                const ratio = rowLsr.longShortRatio;
                                                const cls = ratio > 1 ? 'positive' : ratio < 1 ? 'negative' : '';
                                                return (
                                                    <td key={col.key} className={`lsr-cell ${cls}`}>
                                                        <span className="lsr-mini">
                                                            <span className="lsr-value">{ratio.toFixed(2)}</span>
                                                            <span className="lsr-pct">{rowLsr.longAccount.toFixed(0)}L/{rowLsr.shortAccount.toFixed(0)}S</span>
                                                        </span>
                                                    </td>
                                                );
                                            }

                                            const val = row[col.key];
                                            const formatted = col.format ? formatValue(val, col.format) : val;
                                            const rateClass = (col.format === 'rate' || col.format === 'change' || col.format === 'monthly')
                                                ? getRateClass(val) : '';

                                            return (
                                                <td key={col.key} className={rateClass}>
                                                    {col.key === 'symbol' ? (
                                                        <span className="symbol-cell">
                                                            <span className="symbol-name">{row.symbol}</span>
                                                            <a
                                                                href={getExchangeUrl(row.symbol, exchange)}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="exchange-link"
                                                                title={`Abrir ${row.symbol} na ${exchange === 'bybit' ? 'Bybit' : 'Binance'}`}
                                                                onClick={e => e.stopPropagation()}
                                                            >
                                                                <FaCircle
                                                                    aria-hidden="true"
                                                                    style={{ color: exchange === 'bybit' ? '#fb923c' : '#facc15' }}
                                                                />
                                                            </a>
                                                        </span>
                                                    ) : col.key === 'nextFundingTime' ? (
                                                        <LiveCountdown targetTime={val} />
                                                    ) : formatted}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>

            {totalPages > 1 && (
                <div className="pagination">
                    <button disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</button>
                    <span className="page-info">Página {page + 1} de {totalPages} · {filteredData.length} pares</span>
                    <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>Próxima →</button>
                </div>
            )}
        </div>
    );
}
