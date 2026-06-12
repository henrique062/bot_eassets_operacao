import { useState } from 'react';
import { marked } from 'marked';
import {
    FaBolt,
    FaBrain,
    FaBullseye,
    FaCircle,
    FaCircleInfo,
    FaRobot,
    FaTrophy,
    FaTriangleExclamation,
} from 'react-icons/fa6';
import { fetchAIAnalysis } from '../services/api';

// Configure marked for safe rendering
marked.setOptions({
    breaks: true,
    gfm: true,
});

export default function AIAnalysis({ exchange }) {
    const [analysis, setAnalysis] = useState('');
    const [recommendedCoins, setRecommendedCoins] = useState([]);
    const [loading, setLoading] = useState(false);
    const [loaded, setLoaded] = useState(false);

    const runAnalysis = () => {
        setLoading(true);
        setLoaded(false);
        fetchAIAnalysis(exchange)
            .then(res => {
                setAnalysis(res.analysis || 'Sem resposta da IA');
                setRecommendedCoins(res.recommended_coins || []);
                setLoaded(true);
            })
            .catch(err => {
                setAnalysis(`Erro: ${err.message}`);
                setRecommendedCoins([]);
                setLoaded(true);
            })
            .finally(() => setLoading(false));
    };

    function renderMarkdown(text) {
        if (!text) return '';
        try {
            return marked.parse(text);
        } catch {
            return text;
        }
    }

    function getDirectionClass(direction) {
        return direction === 'LONG' ? 'dir-long' : 'dir-short';
    }

    function getDirectionIcon(direction) {
        return (
            <FaCircle
                aria-hidden="true"
                className={direction === 'LONG' ? 'positive' : 'negative'}
            />
        );
    }

    function getConfidenceClass(confidence) {
        const c = (confidence || '').toLowerCase();
        if (c === 'forte') return 'score-forte';
        if (c === 'moderado') return 'score-moderado';
        return 'score-fraco';
    }

    return (
        <div className="ai-panel">
            <div className="ai-header">
                <div>
                    <h2 className="icon-inline">
                        <FaRobot aria-hidden="true" />
                        Análise com Inteligência Artificial
                    </h2>
                    <p className="ai-subtitle">
                        Gemini analisa funding rates, LSR e condições de mercado para recomendar os melhores ativos
                    </p>
                </div>
                <button
                    className={`ai-run-btn ${loading ? 'loading' : ''}`}
                    onClick={runAnalysis}
                    disabled={loading}
                >
                    {loading ? (
                        <>
                            <span className="spinner-small" />
                            Analisando...
                        </>
                    ) : (
                        <>
                            <FaBolt aria-hidden="true" />
                            Analisar Agora
                        </>
                    )}
                </button>
            </div>

            {loading && (
                <div className="ai-loading">
                    <div className="ai-loading-bar">
                        <div className="ai-loading-progress" />
                    </div>
                    <p>A IA está analisando os dados de mercado da {exchange === 'binance' ? 'Binance' : 'Bybit'}...</p>
                    <p className="ai-loading-sub">Isso pode levar até 30 segundos</p>
                </div>
            )}

            {loaded && !loading && (
                <>
                    {/* Análise em markdown renderizado */}
                    <div className="ai-result">
                        <div
                            className="ai-content"
                            dangerouslySetInnerHTML={{ __html: renderMarkdown(analysis) }}
                        />
                    </div>

                    {/* Grid de moedas recomendadas */}
                    {recommendedCoins.length > 0 && (
                        <div className="ai-coins-section">
                            <h3 className="ai-coins-title icon-inline">
                                <FaTrophy aria-hidden="true" />
                                Moedas Recomendadas pela IA
                            </h3>
                            <p className="ai-coins-subtitle">
                                Top {recommendedCoins.length} oportunidades ordenadas por score
                            </p>
                            <div className="ai-coins-grid">
                                {recommendedCoins.map((coin, idx) => (
                                    <div
                                        key={coin.symbol + idx}
                                        className={`ai-coin-card ${coin.direction === 'LONG' ? 'coin-long' : 'coin-short'}`}
                                    >
                                        <div className="ai-coin-header">
                                            <div className="ai-coin-rank">#{idx + 1}</div>
                                            <div className="ai-coin-symbol">{coin.symbol}</div>
                                            <span className={`direction-badge ${getDirectionClass(coin.direction)}`}>
                                                {getDirectionIcon(coin.direction)} {coin.direction}
                                            </span>
                                        </div>

                                        <div className="ai-coin-metrics">
                                            <div className={`ai-coin-score ${getConfidenceClass(coin.confidence)}`}>
                                                <span className="score-number">{coin.score}</span>
                                                <span className="score-label">{coin.confidence}</span>
                                            </div>
                                            <div className="ai-coin-rates">
                                                <div className="ai-coin-rate">
                                                    <span className="ai-coin-rate-label">Taxa ({coin.funding_interval}h)</span>
                                                    <span className={`ai-coin-rate-value ${coin.rate_percent >= 0 ? 'positive' : 'negative'}`}>
                                                        {coin.rate_percent >= 0 ? '+' : ''}{Number(coin.rate_percent).toFixed(4)}%
                                                    </span>
                                                </div>
                                                <div className="ai-coin-rate">
                                                    <span className="ai-coin-rate-label">Mensal</span>
                                                    <span className={`ai-coin-rate-value ${coin.monthly_rate >= 0 ? 'positive' : 'negative'}`}>
                                                        {coin.monthly_rate >= 0 ? '+' : ''}{Number(coin.monthly_rate).toFixed(1)}%
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="ai-coin-details">
                                            <div className="ai-coin-detail">
                                                <span className="ai-coin-detail-icon"><FaCircleInfo aria-hidden="true" /></span>
                                                <span>{coin.justification}</span>
                                            </div>
                                            <div className="ai-coin-detail">
                                                <span className="ai-coin-detail-icon"><FaTriangleExclamation aria-hidden="true" /></span>
                                                <span>{coin.risk}</span>
                                            </div>
                                        </div>

                                        <div className="ai-coin-strategy">
                                            <span className="ai-coin-strategy-badge">
                                                <FaBullseye aria-hidden="true" />
                                                {coin.strategy}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </>
            )}

            {!loaded && !loading && (
                <div className="ai-placeholder">
                    <span className="ai-placeholder-icon"><FaBrain aria-hidden="true" /></span>
                    <p>Clique em <strong>"Analisar Agora"</strong> para a IA identificar as melhores oportunidades</p>
                    <p className="ai-placeholder-sub">
                        A IA vai avaliar funding rates, Long/Short Ratio, volume e intervalos de funding para gerar recomendações personalizadas
                    </p>
                </div>
            )}
        </div>
    );
}
