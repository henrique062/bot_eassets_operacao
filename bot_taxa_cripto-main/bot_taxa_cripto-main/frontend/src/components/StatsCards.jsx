import { useState, useEffect } from 'react';
import {
    FaArrowTrendDown,
    FaArrowTrendUp,
    FaBolt,
    FaChartLine,
    FaCoins,
    FaTableList,
} from 'react-icons/fa6';
import { fetchStats } from '../services/api';

function formatPercent(value) {
    if (value === null || value === undefined) return '—';
    const num = Number(value);
    return (num >= 0 ? '+' : '') + num.toFixed(4) + '%';
}

export default function StatsCards({ exchange }) {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        fetchStats(exchange)
            .then(res => setStats(res.data))
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [exchange]);

    if (loading) {
        return (
            <div className="stats-grid">
                {[1, 2, 3, 4, 5].map(i => (
                    <div key={i} className="stat-card skeleton">
                        <div className="skeleton-line" />
                        <div className="skeleton-line short" />
                    </div>
                ))}
            </div>
        );
    }

    if (!stats) return null;

    // Calcular melhor ativo para lucrar (maior funding rate absoluto)
    const bestProfit = stats.top10Positive?.[0] || stats.top10Negative?.[0];
    const bestDir = bestProfit?.fundingRate > 0 ? 'SHORT' : 'LONG';
    const bestInterval = stats.intervals || {};
    const nonStdIntervals = Object.entries(bestInterval)
        .filter(([k]) => k !== '8h')
        .map(([k, v]) => `${v} pares a ${k}`)
        .join(', ');

    const cards = [
        {
            label: 'Total de Pares',
            value: stats.totalPairs,
            icon: <FaTableList aria-hidden="true" />,
            sub: `${stats.positiveCount} positivos · ${stats.negativeCount} negativos`,
            color: 'var(--accent-blue)',
        },
        {
            label: 'Maior Taxa',
            value: stats.maxRate ? formatPercent(stats.maxRate.fundingRatePercent) : '—',
            icon: <FaArrowTrendUp aria-hidden="true" />,
            sub: stats.maxRate?.symbol || '',
            color: 'var(--accent-green)',
        },
        {
            label: 'Menor Taxa',
            value: stats.minRate ? formatPercent(stats.minRate.fundingRatePercent) : '—',
            icon: <FaArrowTrendDown aria-hidden="true" />,
            sub: stats.minRate?.symbol || '',
            color: 'var(--accent-red)',
        },
        {
            label: 'Taxa Média',
            value: formatPercent(stats.avgRatePercent),
            icon: <FaChartLine aria-hidden="true" />,
            sub: nonStdIntervals ? (
                <span className="icon-inline">
                    <FaBolt aria-hidden="true" />
                    {nonStdIntervals}
                </span>
            ) : (
                `${stats.neutralCount} neutros`
            ),
            color: 'var(--accent-purple)',
        },
        {
            label: 'Melhor Oportunidade',
            value: bestProfit ? `${bestDir}` : '—',
            icon: <FaCoins aria-hidden="true" />,
            sub: bestProfit
                ? `${bestProfit.symbol} · ${formatPercent(bestProfit.fundingRatePercent)}/período`
                : '',
            color: bestDir === 'SHORT' ? 'var(--accent-red)' : 'var(--accent-green)',
        },
    ];

    return (
        <div className="stats-grid">
            {cards.map((card, i) => (
                <div key={i} className="stat-card" style={{ '--card-accent': card.color }}>
                    <div className="stat-card-header">
                        <span className="stat-icon">{card.icon}</span>
                        <span className="stat-label">{card.label}</span>
                    </div>
                    <div className="stat-value">{card.value}</div>
                    <div className="stat-sub">{card.sub}</div>
                </div>
            ))}
        </div>
    );
}
