import { useState, useEffect } from 'react';
import { marked } from 'marked';
import {
    FaBullseye,
    FaCircle,
    FaCircleInfo,
    FaPlus,
    FaRobot,
    FaTrophy,
    FaTriangleExclamation,
} from 'react-icons/fa6';
import { fetchAIAnalysis, fetchSmartReports, fetchSmartReportById } from '../services/api';

marked.setOptions({
    breaks: true,
    gfm: true,
});

export default function SmartReport({ exchange }) {
    const [reports, setReports] = useState([]);
    const [currentReport, setCurrentReport] = useState(null);

    const [loadingList, setLoadingList] = useState(false);
    const [loadingReport, setLoadingReport] = useState(false);
    const [generating, setGenerating] = useState(false);

    useEffect(() => {
        loadReportsList();
    }, [exchange]);

    const loadReportsList = () => {
        setLoadingList(true);
        fetchSmartReports(20, 0)
            .then(res => {
                const exReports = (res.data || []).filter(r => r.exchange === exchange);
                setReports(exReports);
                if (exReports.length > 0 && !currentReport && !generating) {
                    loadReportDetails(exReports[0].id);
                }
            })
            .catch(err => console.error("Failed to load reports:", err))
            .finally(() => setLoadingList(false));
    };

    const loadReportDetails = (id) => {
        setLoadingReport(true);
        fetchSmartReportById(id)
            .then(res => setCurrentReport(res.data))
            .catch(err => console.error("Failed to load report details:", err))
            .finally(() => setLoadingReport(false));
    };

    const generateNewReport = () => {
        setGenerating(true);
        setCurrentReport(null);
        fetchAIAnalysis(exchange)
            .then(res => {
                const newReport = {
                    id: res.report_id,
                    exchange: res.exchange,
                    createdAt: res.created_at,
                    marketOverview: res.analysis,
                    recommendedCoins: res.recommended_coins,
                    isAccurate: null
                };
                setCurrentReport(newReport);
                // Prepend to list
                setReports(prev => [{
                    id: res.report_id,
                    exchange: res.exchange,
                    createdAt: res.created_at,
                    isAccurate: null
                }, ...prev]);
            })
            .catch(err => {
                alert(`Erro ao gerar relatório: ${err.message}`);
            })
            .finally(() => setGenerating(false));
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
        <>
        <div className="smart-report-container">
            <div className="smart-report-sidebar">
                <div className="sidebar-header">
                    <h3>Histórico de Relatórios</h3>
                    <button
                        className={`btn-primary ${generating ? 'loading' : ''}`}
                        onClick={generateNewReport}
                        disabled={generating}
                    >
                        {generating ? 'Gerando...' : (
                            <span className="icon-inline">
                                <FaPlus aria-hidden="true" />
                                Novo Relatório (IA)
                            </span>
                        )}
                    </button>
                </div>
                
                <div className="reports-list">
                    {loadingList ? (
                        <div className="loading-spinner">Carregando histórico...</div>
                    ) : reports.length === 0 ? (
                        <div className="empty-state">Nenhum relatório encontrado para {exchange}.</div>
                    ) : (
                        reports.map(report => (
                            <div 
                                key={report.id} 
                                className={`report-item ${currentReport?.id === report.id ? 'active' : ''}`}
                                onClick={() => loadReportDetails(report.id)}
                            >
                                <div className="report-item-header">
                                    <span className="report-id">#{report.id}</span>
                                    <span className="report-date">
                                        {new Date(report.createdAt).toLocaleString('pt-BR')}
                                    </span>
                                </div>
                                <div className="report-item-status">
                                    {report.isAccurate === true && <span className="status-badge valid">Correto</span>}
                                    {report.isAccurate === false && <span className="status-badge invalid">Incorreto</span>}
                                    {report.isAccurate === null && <span className="status-badge pending">Aguardando Avaliação</span>}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>

            <div className="smart-report-content">
                {generating ? (
                    <div className="ai-loading">
                        <div className="ai-loading-bar">
                            <div className="ai-loading-progress" />
                        </div>
                        <p>A IA está analisando os dados de mercado da {exchange === 'binance' ? 'Binance' : 'Bybit'}...</p>
                        <p className="ai-loading-sub">Isso pode levar até 30 segundos. Salvando no banco de dados.</p>
                    </div>
                ) : loadingReport ? (
                    <div className="loading-container">
                        <div className="spinner-large" />
                        <p>Carregando detalhes do relatório...</p>
                    </div>
                ) : currentReport ? (
                    <div className="report-details">
                        <div className="report-header-info">
                            <h2>Relatório Inteligente #{currentReport.id}</h2>
                            <p className="report-meta">Gerado em: {new Date(currentReport.createdAt).toLocaleString('pt-BR')} | Exchange: {currentReport.exchange}</p>
                        </div>

                        <div className="ai-result">
                            <div
                                className="ai-content"
                                dangerouslySetInnerHTML={{ __html: renderMarkdown(currentReport.marketOverview) }}
                            />
                        </div>

                        {currentReport.recommendedCoins && currentReport.recommendedCoins.length > 0 && (
                            <div className="ai-coins-section">
                                <h3 className="ai-coins-title icon-inline">
                                    <FaTrophy aria-hidden="true" />
                                    Estratégias Refinadas pela IA
                                </h3>
                                <p className="ai-coins-subtitle">
                                    Top oportunidades avaliadas e selecionadas
                                </p>
                                <div className="ai-coins-grid">
                                    {currentReport.recommendedCoins.map((coin, idx) => (
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
                                                        <span className="ai-coin-rate-label">Taxa ({coin.funding_interval || 8}h)</span>
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
                    </div>
                ) : (
                    <div className="ai-placeholder">
                        <span className="ai-placeholder-icon"><FaRobot aria-hidden="true" /></span>
                        <p>Selecione um relatório no histórico ou crie um novo</p>
                    </div>
                )}
            </div>
        </div>
        </>
    );
}
