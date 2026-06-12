import { useState, useEffect, useCallback, useMemo } from 'react';
import {
    FaArrowRotateLeft,
    FaArrowTrendDown,
    FaBolt,
    FaBookOpen,
    FaBrain,
    FaBullseye,
    FaChartLine,
    FaCircleCheck,
    FaCirclePlay,
    FaClipboard,
    FaClock,
    FaFileLines,
    FaFilter,
    FaFloppyDisk,
    FaPause,
    FaPencil,
    FaPlay,
    FaRobot,
    FaShieldHalved,
    FaStop,
    FaTableList,
    FaTriangleExclamation,
    FaTrashCan,
    FaWandMagicSparkles,
    FaXmark,
} from 'react-icons/fa6';
import RealTrading from './RealTrading';
import ConfirmModal from './ConfirmModal';
import EditBotModal from './EditBotModal';
import aiIcon from '../assets/tecnologia-de-ia.png';
import {
    fetchRealSessions,
    fetchRealStatus,
    fetchRealSessionStatus,
    stopReal,
    deleteRealSession,
    editRealSession,
    pauseRealSession,
    resumeRealSession,
    fetchFundingRates,
    closeAllRealPositions,
    validateRealApiKeys,
    fetchRealLogs,
    fetchStrategies,
    saveStrategy,
    deleteStrategy,
    sseUrl,
    requestBotAIAnalysis,
    applyBotAISuggestions,
    triggerRealManual,
    analyzeMarketForBot,
} from '../services/api';
import { deriveEntryMargin } from '../utils/trading';

const MODE_LABELS_SHORT = {
    auto_expiring: 'AUTO EXP',
    auto_strongest: 'AUTO FORTE',
    auto_highest_rate: 'AUTO TAXA',
    post_funding_follow: 'POS FAVOR',
    counter_trend: 'CONTRA',
    manual: 'MANUAL',
    manual_position: 'MANUAL OP',
    test: 'MANUAL OP',
};

const MODE_LABELS_LONG = {
    auto_expiring: 'Auto Expirando',
    auto_strongest: 'Auto Mais Forte',
    auto_highest_rate: 'Maior Taxa',
    post_funding_follow: 'Pos-Funding (Favor)',
    counter_trend: 'Contra-Tendência',
    manual: 'Manual',
    manual_position: 'Operação Manual',
    test: 'Operação Manual',
};

function getModeShortLabel(mode) {
    return MODE_LABELS_SHORT[mode] || 'MANUAL';
}

const PRESET_DISPLAY = {
    ct_precisa:       { name: 'CT Precisa',      color: '#22c55e' },
    ct_balanceada:    { name: 'CT Balanceada',    color: '#3b82f6' },
    coleta_segura:    { name: 'Coleta Segura',    color: '#8b5cf6' },
    coleta_expirando: { name: 'Coleta Expirando', color: '#f59e0b' },
};

function getModeLongLabel(mode) {
    return MODE_LABELS_LONG[mode] || mode || 'Manual';
}




function fmtMarginUsd(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return '—';
    return `$${n.toFixed(n >= 100 ? 2 : 4)}`;
}


export default function RealTradingPage({ exchange, prefilledConfig, onClearPrefilled }) {
    const [sessions, setSessions] = useState([]);
    const [activeSessions, setActiveSessions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [editFeedback, setEditFeedback] = useState(null); // { type: 'success'|'warning', message: string }
    const [editingSessionId, setEditingSessionId] = useState(null);
    const [historyModalSession, setHistoryModalSession] = useState(null);
    const [showLogsModal, setShowLogsModal] = useState(false);
    const [localPrefilled, setLocalPrefilled] = useState(prefilledConfig || null);
    const [showAIBotModal, setShowAIBotModal] = useState(false);
    const [aiBotCapital, setAIBotCapital] = useState('100');
    const [aiBotLeverage, setAIBotLeverage] = useState('5');
    const [aiBotGenerating, setAIBotGenerating] = useState(false);
    const [aiBotError, setAIBotError] = useState('');
    const [apiStatus, setApiStatus] = useState(null); // { connected, message }
    const [modalConfig, setModalConfig] = useState(null);
    const [activeMainTab, setActiveMainTab] = useState('trading'); // 'trading' | 'guide'

    // Sincroniza config vinda de fora (App.jsx)
    useEffect(() => {
        if (prefilledConfig) {
            setLocalPrefilled(prefilledConfig);
            onClearPrefilled?.();
        }
    }, [prefilledConfig]);

    const loadData = useCallback(async () => {
        try {
            const [sessRes, statusRes] = await Promise.all([
                fetchRealSessions(),
                fetchRealStatus(),
            ]);
            setSessions(sessRes.data || []);
            setActiveSessions(statusRes.sessions || []);
            setError('');
        } catch (e) {
            console.error(e);
            setError(e.message || 'Erro ao carregar dados.');
        } finally {
            setLoading(false);
        }
    }, []);

    // Validação de chaves de API ao montar a página
    useEffect(() => {
        validateRealApiKeys(exchange).then(res => setApiStatus(res)).catch(() => {});
    }, [exchange]);

    useEffect(() => {
        loadData(); // carrega sessões históricas uma vez no mount

        // Polling de 30s apenas para sessões inativas/históricas
        const interval = setInterval(loadData, 30000);

        let es = null;
        let retryTimer = null;

        const connect = () => {
            es = new EventSource(sseUrl('/real-trading/events'));

            es.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    setActiveSessions(data.sessions || []);
                } catch (e) {
                    console.error('SSE parse error:', e);
                }
            };

            es.onerror = () => {
                es.close();
                setError('Conexão SSE perdida. Reconectando...');
                retryTimer = setTimeout(() => {
                    setError('');
                    connect();
                }, 3000);
            };
        };

        connect();

        return () => {
            clearInterval(interval);
            es?.close();
            if (retryTimer) clearTimeout(retryTimer);
        };
    }, []); // sem dependências — conecta uma vez

    const handleStop = async (sessionId) => {
        setModalConfig({
            title: 'Parar Bot',
            message: 'Parar este bot de conta real?',
            onConfirm: async () => {
                try {
                    const result = await stopReal(sessionId);
                    await loadData();
                    if (result?.blocked) {
                        const remainingSymbols = Array.isArray(result?.remainingSymbols)
                            ? result.remainingSymbols
                            : [];
                        const symbolsText = remainingSymbols.length
                            ? `\nSímbolos pendentes: ${remainingSymbols.join(', ')}`
                            : '';
                        setModalConfig({
                            isAlert: true,
                            title: 'Parada bloqueada',
                            message: `${result?.message || 'Ainda existem posições abertas.'}${symbolsText}`,
                        });
                        return;
                    }
                    setModalConfig({
                        isAlert: true,
                        title: 'Bot parado',
                        message: result?.message || 'Bot parado com sucesso.',
                    });
                } catch (e) { setModalConfig({ isAlert: true, message: e.message, title: 'Erro' }); }
            }
        });
    };

    const handleDelete = async (sessionId) => {
        setModalConfig({
            title: 'Deletar Sessão',
            message: 'Deletar esta sessão permanentemente?',
            onConfirm: async () => {
                try {
                    await deleteRealSession(sessionId);
                    await loadData();
                    setModalConfig(null);
                } catch (e) { setModalConfig({ isAlert: true, message: e.message, title: 'Erro' }); }
            }
        });
    };

    const handleEdit = (sessionId) => {
        setEditingSessionId(editingSessionId === sessionId ? null : sessionId);
    };

    const handleSaveEdit = async (sessionId, config) => {
        try {
            const updated = await editRealSession(sessionId, config);
            setEditingSessionId(null);
            await loadData();

            let verified = updated;
            let verifiedFromReload = true;
            try {
                verified = await fetchRealSessionStatus(sessionId);
            } catch (_) {
                verifiedFromReload = false;
            }

            const verifiedConfig = verified?.config || {};
            const mismatches = [];

            const same = (a, b) => {
                if (a === null || a === undefined) return b === null || b === undefined;
                if (b === null || b === undefined) return false;
                if (typeof a === 'number' || typeof b === 'number') {
                    return Number(a) === Number(b);
                }
                return String(a).trim() === String(b).trim();
            };

            for (const [key, expected] of Object.entries(config || {})) {
                const actual = key === 'sessionName' ? verified?.sessionName : verifiedConfig?.[key];
                if (!same(expected, actual)) {
                    mismatches.push(key);
                }
            }

            if (mismatches.length > 0) {
                setEditFeedback({
                    type: 'warning',
                    message: `Edição salva, mas houve divergência de retorno em: ${mismatches.join(', ')}. Verifique no banco/logs.`,
                });
            } else if (!verifiedFromReload) {
                setEditFeedback({
                    type: 'warning',
                    message: 'Configurações salvas, mas não foi possível validar a sessão recarregada agora. Confira no histórico.',
                });
            } else {
                setEditFeedback({
                    type: 'success',
                    message: 'Configurações editadas e persistidas com sucesso.',
                });
            }
        } catch (e) { setModalConfig({ isAlert: true, message: e.message, title: 'Erro' }); }
    };

    const handleCloseAll = async (sessionId) => {
        setModalConfig({
            title: 'Fechar Posições',
            message: 'Fechar todas as posições abertas agora ao preço atual?',
            onConfirm: async () => {
                try {
                    await closeAllRealPositions(sessionId);
                    await loadData();
                    setModalConfig(null);
                } catch (e) { setModalConfig({ isAlert: true, message: e.message, title: 'Erro' }); }
            }
        });
    };

    const handlePauseToggle = async (sessionId, isPaused) => {
        try {
            if (isPaused) await resumeRealSession(sessionId);
            else await pauseRealSession(sessionId);
            await loadData();
        } catch (e) { setModalConfig({ isAlert: true, message: e.message, title: 'Erro' }); }
    };

    const inactiveSessions = sessions.filter(s => !s.active);

    const handleAIBotCreate = async () => {
        const capital = parseFloat(aiBotCapital);
        const leverage = parseInt(aiBotLeverage, 10);
        if (!capital || capital < 10) { setAIBotError('Capital mínimo é $10'); return; }
        if (!leverage || leverage < 1 || leverage > 20) { setAIBotError('Alavancagem: 1-20'); return; }
        setAIBotError('');
        setAIBotGenerating(true);
        try {
            const res = await analyzeMarketForBot(capital, leverage, exchange);
            if (!res?.config) { setAIBotError('Resposta inválida da IA. Tente novamente.'); return; }
            setShowAIBotModal(false);
            setLocalPrefilled({ ...res.config, exchange });
        } catch (e) {
            setAIBotError(e.message || 'Erro ao analisar mercado. Verifique os logs.');
        } finally {
            setAIBotGenerating(false);
        }
    };

    return (
        <div className="paper-page">
            {/* Badge de status da conexão com a API */}
            {apiStatus !== null && (
                <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: '8px',
                    background: apiStatus.connected ? 'rgba(0,230,138,0.08)' : 'rgba(255,77,106,0.08)',
                    border: `1px solid ${apiStatus.connected ? 'var(--accent-green)' : 'var(--accent-red)'}`,
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 14px', marginBottom: '16px', fontSize: '13px',
                }}>
                    <span style={{
                        width: '8px', height: '8px', borderRadius: '50%',
                        background: apiStatus.connected ? 'var(--accent-green)' : 'var(--accent-red)',
                        flexShrink: 0,
                    }} />
                    <span style={{ color: apiStatus.connected ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                        {apiStatus.connected ? 'API Conectada' : 'API Desconectada'}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>— {apiStatus.message}</span>
                </div>
            )}

            {/* Abas principais */}
            <div style={{ display: 'flex', gap: '0', marginBottom: '24px', borderBottom: '1px solid var(--border-color)' }}>
                {[
                    { key: 'trading', label: 'Trading', icon: <FaChartLine /> },
                    { key: 'guide', label: 'Guia de Estratégias', icon: <FaBookOpen /> },
                ].map(tab => (
                    <button
                        key={tab.key}
                        onClick={() => setActiveMainTab(tab.key)}
                        style={{
                            background: 'none',
                            border: 'none',
                            borderBottom: activeMainTab === tab.key ? '2px solid var(--accent-color)' : '2px solid transparent',
                            color: activeMainTab === tab.key ? 'var(--text-primary)' : 'var(--text-muted)',
                            padding: '10px 20px',
                            cursor: 'pointer',
                            fontSize: '14px',
                            fontWeight: activeMainTab === tab.key ? '600' : '400',
                            marginBottom: '-1px',
                        }}
                    >
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                            {tab.icon}
                            {tab.label}
                        </span>
                    </button>
                ))}
            </div>

            {activeMainTab === 'trading' && (
                <>
                    {/* Formulário de criação */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginBottom: '16px' }}>
                        <button
                            className="nav-btn"
                            style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', padding: '10px 20px', borderRadius: 'var(--radius-md)', fontWeight: 600, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                            onClick={() => setShowAIBotModal(true)}
                        >
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                <FaRobot />
                                Criar Bot com IA
                            </span>
                        </button>
                        <button
                            className="nav-btn"
                            style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', padding: '10px 20px', borderRadius: 'var(--radius-md)', fontWeight: 600, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                            onClick={() => setShowLogsModal(true)}
                        >
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                <FaTableList />
                                Painel de Logs & Histórico Global
                            </span>
                        </button>
                    </div>

                    {/* Modal: Criar Bot com IA */}
                    {showAIBotModal && (
                        <div className="modal-overlay" onClick={() => setShowAIBotModal(false)}>
                            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '440px' }}>
                                <div className="modal-header">
                                    <h3 className="icon-inline"><FaRobot /> Criar Bot com IA</h3>
                                    <button className="modal-close" onClick={() => setShowAIBotModal(false)}><FaXmark /></button>
                                </div>
                                <div className="modal-body" style={{ padding: '20px 24px' }}>
                                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                                        A IA vai analisar as taxas de funding em tempo real e gerar a melhor configuração de bot.
                                    </p>
                                    <div className="modal-field">
                                        <label>Capital (USDT)</label>
                                        <input
                                            type="number"
                                            min="10"
                                            step="10"
                                            value={aiBotCapital}
                                            onChange={e => setAIBotCapital(e.target.value)}
                                            placeholder="Ex: 100"
                                        />
                                        <span className="modal-field-hint">Mínimo $10</span>
                                    </div>
                                    <div className="modal-field">
                                        <label>Alavancagem</label>
                                        <input
                                            type="number"
                                            min="1"
                                            max="20"
                                            value={aiBotLeverage}
                                            onChange={e => setAIBotLeverage(e.target.value)}
                                            placeholder="Ex: 5"
                                        />
                                    </div>
                                    {aiBotError && <p className="modal-error">{aiBotError}</p>}
                                </div>
                                <div className="modal-footer" style={{ padding: '16px 24px', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                                    <button className="session-cancel-btn" onClick={() => setShowAIBotModal(false)}>Cancelar</button>
                                    <button className="session-save-btn" onClick={handleAIBotCreate} disabled={aiBotGenerating}>
                                        {aiBotGenerating ? 'Analisando mercado...' : (
                                            <span className="icon-inline"><FaRobot /> Analisar e Pré-preencher</span>
                                        )}
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    <RealTrading
                        exchange={exchange}
                        onSessionCreated={loadData}
                        prefilledConfig={localPrefilled}
                    />

                    {/* Bots em execução */}
                    {/* Sessões Ativas */}
                    <div className="section-block">
                        <div className="section-header">
                            <h2 style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                <FaCirclePlay style={{ color: 'var(--accent-green)' }} />
                                Bots em Execução ({activeSessions.length})
                            </h2>
                            <button className="refresh-btn" onClick={loadData} disabled={loading}>
                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                    <FaArrowRotateLeft />
                                    Atualizar
                                </span>
                            </button>
                        </div>

                        {error && <div className="error-message">{error}</div>}
                        {editFeedback && (
                            <div
                                style={{
                                    marginBottom: '12px',
                                    borderRadius: '8px',
                                    border: `1px solid ${editFeedback.type === 'success' ? 'rgba(0, 230, 138, 0.35)' : 'rgba(245, 158, 11, 0.35)'}`,
                                    background: editFeedback.type === 'success' ? 'rgba(0, 230, 138, 0.08)' : 'rgba(245, 158, 11, 0.12)',
                                    color: editFeedback.type === 'success' ? 'var(--accent-green)' : '#fbbf24',
                                    fontSize: '12px',
                                    fontWeight: 600,
                                    padding: '10px 12px',
                                }}
                            >
                                {editFeedback.message}
                            </div>
                        )}

                        {activeSessions.length > 0 && (
                            <div className="sessions-grid">
                                {activeSessions.map(session => (
                                    <ActiveSessionCard
                                        key={session.sessionId}
                                        session={session}
                                        isEditing={editingSessionId === session.sessionId}
                                        onStop={handleStop}
                                        onEdit={setEditingSessionId}
                                        onSaveEdit={handleSaveEdit}
                                        onViewHistory={() => setHistoryModalSession(session)}
                                        onCloseAll={handleCloseAll}
                                        onCopyStrategy={(cfg) => setLocalPrefilled(cfg)}
                                        onPauseToggle={handlePauseToggle}
                                    />
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Histórico de sessões finalizadas */}
                    <div className="sessions-section">
                        <div className="sessions-section-header">
                            <h3 style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                <FaFileLines />
                                Histórico de Sessões
                            </h3>
                            <button onClick={loadData} className="refresh-sessions-btn">
                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                    <FaArrowRotateLeft />
                                    Atualizar
                                </span>
                            </button>
                        </div>

                        {loading && <div className="sessions-loading">Carregando...</div>}

                        {!loading && inactiveSessions.length === 0 && (
                            <div className="sessions-empty">Nenhuma sessão finalizada ainda.</div>
                        )}

                        {!loading && inactiveSessions.length > 0 && (
                            <div className="sessions-grid">
                                {inactiveSessions.map(session => (
                                    <SessionCard
                                        key={session.id}
                                        session={session}
                                        onDelete={handleDelete}
                                        onViewHistory={() => setHistoryModalSession(session)}
                                    />
                                ))}
                            </div>
                        )}
                    </div>

                    {historyModalSession && (
                        <SessionHistoryModal
                            session={historyModalSession}
                            onClose={() => setHistoryModalSession(null)}
                        />
                    )}

                    {showLogsModal && (
                        <RealLogsModal
                            onClose={() => setShowLogsModal(false)}
                            activeSessions={activeSessions}
                            inactiveSessions={inactiveSessions}
                            onCopyStrategy={(cfg) => {
                                setLocalPrefilled(cfg);
                                setShowLogsModal(false);
                            }}
                        />
                    )}

                    {modalConfig && (
                        <ConfirmModal
                            title={modalConfig.title}
                            message={modalConfig.message}
                            isAlert={modalConfig.isAlert}
                            onConfirm={() => {
                                if (modalConfig.onConfirm) modalConfig.onConfirm();
                                setModalConfig(null);
                            }}
                            onCancel={() => setModalConfig(null)}
                        />
                    )}

                    {editingSessionId && (
                        <EditBotModal
                            session={activeSessions.find(s => s.sessionId === editingSessionId)}
                            onSave={handleSaveEdit}
                            onClose={() => setEditingSessionId(null)}
                        />
                    )}
                </>
            )}

            {activeMainTab === 'guide' && <StrategyGuideTab />}
        </div>
    );
}

// ─── Card de sessão ativa com painel de edição ───────────────────────────────

function buildStrategyFromSession(session) {
    const cfg = session.config || {};
    const operationMode = cfg.operationMode || 'manual';
    const strategy = {
        operationMode: cfg.operationMode || 'manual',
        autoDirection: cfg.autoDirection || 'both',
        autoMaxSymbols: cfg.autoMaxSymbols ?? 8,
        autoMinScore: cfg.autoMinScore ?? 50,
        minFundingRatePct: cfg.minFundingRatePct ?? cfg.min_funding_rate_pct ?? 0.001,
        autoWindowMinutes: cfg.autoWindowMinutes ?? 60,
        symbols: cfg.symbols || [],
        capital: parseFloat(cfg.capital) || 1000,
        leverage: cfg.leverage || 1,
        feeType: cfg.feeType || 'maker',
        entrySeconds: cfg.entrySeconds ?? 30,
        stopLossPct: cfg.stopLossPct ?? null,
        stopLossUsd: cfg.stopLossUsd ?? null,
        minProfitPct: cfg.minProfitPct ?? null,
        targetTakeProfitPct: cfg.targetTakeProfitPct ?? null,
        trailingStopPct: cfg.trailingStopPct ?? null,
        trailingStartProfitPct: cfg.trailingStartProfitPct ?? null,
        exchange: cfg.exchange || 'binance',
    };
    // Motivo: não persistir exitSeconds ao copiar estratégia de modo sem timeout.
    if (operationMode !== 'counter_trend' && operationMode !== 'post_funding_follow') {
        strategy.exitSeconds = cfg.exitSeconds ?? 30;
    }
    return strategy;
}

// Formata valores monetários com casas decimais adaptativas
function fmtVal(v, prefix = '') {
    const abs = Math.abs(v);
    const decimals = abs === 0 ? 4 : abs >= 1 ? 3 : abs >= 0.01 ? 4 : 6;
    const sign = v >= 0 ? (prefix ? '+' : '') : '-';
    return `${sign}${prefix}${Math.abs(v).toFixed(decimals)}`;
}

function ActiveSessionCard({ session, isEditing, onStop, onEdit, onSaveEdit, onViewHistory, onCloseAll, onCopyStrategy, onPauseToggle }) {
    const capital = parseFloat(session.config?.capital) || 0;
    const balance = parseFloat(session.balance) || 0;
    const realizedPnl = balance - capital;
    const realizedPnlPct = capital > 0 ? (realizedPnl / capital) * 100 : 0;
    const cfg = session.config || {};

    // Funding rates + preço atual dos símbolos configurados
    const [symbolRates, setSymbolRates] = useState({});

    useEffect(() => {
        const exchange = cfg.exchange || 'binance';
        const cfgSymbols = cfg.symbols || [];
        const posSymbols = Object.keys(session.positions || {});
        const allSymbols = [...new Set([...cfgSymbols, ...posSymbols])];
        if (!allSymbols.length) return;

        const loadRates = async () => {
            try {
                const res = await fetchFundingRates(exchange);
                const map = {};
                for (const r of (res.data || [])) {
                    if (allSymbols.includes(r.symbol)) {
                        const ttf = r.nextFundingTime ? r.nextFundingTime - Date.now() : null;
                        map[r.symbol] = {
                            rate: r.fundingRatePercent,
                            hoursLeft: ttf != null ? ttf / 3600000 : null,
                            lastPrice: r.lastPrice,
                        };
                    }
                }
                setSymbolRates(map);
            } catch (e) {
                // silencioso
            }
        };
        loadRates();
        const id = setInterval(loadRates, 6000);
        return () => clearInterval(id);
    }, [cfg.exchange, (cfg.symbols || []).join(','), Object.keys(session.positions || {}).sort().join(',')]);

    const positions = Object.values(session.positions || {});
    const hasOpenPositions = positions.length > 0;
    const orphanPositions = positions.filter(p => !(cfg.symbols || []).includes(p.symbol));

    let openPricePnl = 0;
    let openFundingPnl = 0;
    let openPnlCount = 0;
    const openPnlBySymbol = {};   // { symbol: { price, funding, total } }
    for (const pos of positions) {
        const ri = symbolRates[pos.symbol];
        const entryPrice = Number(pos.entryPrice);
        const size = Number(pos.size);
        const posValue = Number(pos.value);
        const lastPrice = Number(ri?.lastPrice);
        // Funding já recebido no settlement (abs(rate) * value)
        const fundingReceived = Number.isFinite(posValue) && Number.isFinite(pos.fundingRatePct)
            ? Math.abs(pos.fundingRatePct / 100) * posValue
            : 0;
        if (!Number.isFinite(entryPrice) || !Number.isFinite(size) || !Number.isFinite(lastPrice)) {
            openPnlBySymbol[pos.symbol] = null;
            continue;
        }
        const priceDiff = pos.direction === 'SHORT'
            ? entryPrice - lastPrice
            : lastPrice - entryPrice;
        const pricePnl = priceDiff * size;
        openPnlBySymbol[pos.symbol] = { price: pricePnl, funding: fundingReceived, total: pricePnl + fundingReceived };
        openPricePnl += pricePnl;
        openFundingPnl += fundingReceived;
        openPnlCount += 1;
    }
    const openPnl = openPricePnl + openFundingPnl;
    const hasOpenPnl = openPnlCount > 0;
    const openPnlPct = capital > 0 ? (openPnl / capital) * 100 : 0;
    const livePnl = realizedPnl + (hasOpenPnl ? openPnl : 0);
    const livePnlPct = capital > 0 ? (livePnl / capital) * 100 : 0;

    const modeLabel = getModeShortLabel(cfg.operationMode || 'manual');
    const botDatabaseId = session.sessionId ?? session.id;
    // Bot sem nenhuma atividade ainda: sem trades fechados e sem posições abertas
    const isVirgin = (session.totalTrades || 0) === 0 && !hasOpenPositions;


    return (
        <div className={`session-card session-card-active ${isVirgin ? '' : livePnl >= 0 ? 'session-card-active--profit' : 'session-card-active--loss'}`} onClick={onViewHistory} style={{ cursor: 'pointer' }}>
            <div className="session-card-header">
                <div className="session-name-row">
                    <span className="session-card-exchange">{(cfg.exchange || 'binance').toUpperCase()}</span>
                    <span className="session-name">{session.sessionName || `Bot #${session.sessionId}`}</span>
                    {(session.sessionName || '').startsWith('IA-') && (
                        <span title="Criado por IA" style={{ color: 'var(--accent-blue, #6c8eff)', fontSize: '12px', display: 'inline-flex', alignItems: 'center' }}>
                            <FaRobot />
                        </span>
                    )}
                </div>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {/* Exibe o ID da sessão com visual sutil (sem badge), próximo ao estilo do rótulo da exchange */}
                    {botDatabaseId != null && (
                        <span className="session-card-db-id-inline">
                            ID {botDatabaseId}
                        </span>
                    )}
                    {cfg.presetName && PRESET_DISPLAY[cfg.presetName] && (
                        <span
                            className="session-card-badge"
                            title={`Estratégia: ${PRESET_DISPLAY[cfg.presetName].name}`}
                            style={{ background: PRESET_DISPLAY[cfg.presetName].color + '22', color: PRESET_DISPLAY[cfg.presetName].color, borderColor: PRESET_DISPLAY[cfg.presetName].color + '55' }}
                        >
                            <FaWandMagicSparkles style={{ fontSize: '10px' }} />
                            {PRESET_DISPLAY[cfg.presetName].name}
                        </span>
                    )}
                    <span className="session-card-badge" style={{ background: 'rgba(255,255,255,0.1)', color: 'var(--text-secondary)' }}>{modeLabel}</span>
                    {session.paused
                        ? (
                            <span className="session-card-badge" style={{ background: 'rgba(234,179,8,0.2)', color: '#facc15', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                <FaPause />
                                PAUSADO
                            </span>
                        )
                        : <span className="session-card-badge badge-active">● ATIVO</span>
                    }
                </div>
            </div>

            <div className="session-sym-list">
                {(cfg.symbols || []).map(s => {
                    const pos = positions.find(p => p.symbol === s);
                    const ri = symbolRates[s];
                    const hoursStr = ri?.hoursLeft != null
                        ? ri.hoursLeft < 1
                            ? `${Math.round(ri.hoursLeft * 60)}m`
                            : `${ri.hoursLeft.toFixed(1)}h`
                        : '—';
                    const rateStr = ri?.rate != null
                        ? `${ri.rate >= 0 ? '+' : ''}${ri.rate.toFixed(4)}%`
                        : '—';

                    const symPnl = pos ? openPnlBySymbol[s] : null;
                    const totalPnl = symPnl ? symPnl.total : null;

                    return (
                        <div key={s} className={`sym-list-row${pos ? ' sym-list-open' : ''}`}>
                            <span className="sym-list-name">{s.replace('USDT', '')}</span>
                            <span className={`sym-list-rate ${ri?.rate >= 0 ? 'positive' : 'negative'}`}>{rateStr}</span>
                            <span className="sym-list-hours">{hoursStr}</span>
                            {pos ? (
                                <span className={`sym-list-pos ${pos.direction === 'SHORT' ? 'short' : 'long'}`}>
                                    {pos.direction === 'SHORT' ? '↓' : '↑'}
                                    <span className={`sym-list-money ${totalPnl === null ? 'pending' : totalPnl >= 0 ? 'positive' : 'negative'}`}>
                                        {totalPnl !== null ? fmtVal(totalPnl, '$') : '...'}
                                    </span>
                                </span>
                            ) : (
                                <span className="sym-list-idle">—</span>
                            )}
                        </div>
                    );
                })}
                {orphanPositions.length > 0 && (
                    <>
                        <div className="sym-list-divider">posição aberta · fora da lista</div>
                        {orphanPositions.map(pos => {
                            const s = pos.symbol;
                            const ri = symbolRates[s];
                            const hoursStr = ri?.hoursLeft != null
                                ? ri.hoursLeft < 1
                                    ? `${Math.round(ri.hoursLeft * 60)}m`
                                    : `${ri.hoursLeft.toFixed(1)}h`
                                : '—';
                            const rateStr = ri?.rate != null
                                ? `${ri.rate >= 0 ? '+' : ''}${ri.rate.toFixed(4)}%`
                                : '—';
                            const symPnl = openPnlBySymbol[s];
                            const totalPnl = symPnl ? symPnl.total : null;
                            return (
                                <div key={s} className="sym-list-row sym-list-open sym-list-orphan">
                                    <span className="sym-list-name">{s.replace('USDT', '')}</span>
                                    <span className={`sym-list-rate ${ri?.rate >= 0 ? 'positive' : 'negative'}`}>{rateStr}</span>
                                    <span className="sym-list-hours">{hoursStr}</span>
                                    <span className={`sym-list-pos ${pos.direction === 'SHORT' ? 'short' : 'long'}`}>
                                        {pos.direction === 'SHORT' ? '↓' : '↑'}
                                        <span className={`sym-list-money ${totalPnl === null ? 'pending' : totalPnl >= 0 ? 'positive' : 'negative'}`}>
                                            {totalPnl !== null ? fmtVal(totalPnl, '$') : '...'}
                                        </span>
                                    </span>
                                </div>
                            );
                        })}
                    </>
                )}
            </div>

            {/* PnL */}
            <div className="session-card-pnl">
                <div className="session-pnl-row">
                    <span className="session-pnl-label">Capital</span>
                    <span className="session-pnl-value">${capital.toFixed(2)}</span>
                </div>
                <div className="session-pnl-row">
                    <span className="session-pnl-label">Saldo Atual</span>
                    <span className="session-pnl-value">${balance.toFixed(2)}</span>
                </div>

                <div className="session-pnl-row">
                    <span className="session-pnl-label">Funding recebido</span>
                    {!hasOpenPositions ? (
                        <span className="session-pnl-value">—</span>
                    ) : (
                        <span className={`session-pnl-value ${openFundingPnl >= 0 ? 'positive' : 'negative'}`}>
                            {fmtVal(openFundingPnl, '$')}
                        </span>
                    )}
                </div>
                <div className="session-pnl-row">
                    <span className="session-pnl-label">Variação de preço</span>
                    {!hasOpenPositions ? (
                        <span className="session-pnl-value">—</span>
                    ) : hasOpenPnl ? (
                        <span className={`session-pnl-value ${openPricePnl >= 0 ? 'positive' : 'negative'}`}>
                            {fmtVal(openPricePnl, '$')} ({openPnlPct >= 0 ? '+' : ''}{openPnlPct.toFixed(4)}%)
                        </span>
                    ) : (
                        <span className="session-pnl-value">Calculando...</span>
                    )}
                </div>
                <div className="session-pnl-total">
                    <span className="session-pnl-label">Resultado total (live)</span>
                    {isVirgin ? (
                        <span className="session-pnl-number">—</span>
                    ) : (
                        <span className={`session-pnl-number ${livePnl >= 0 ? 'positive' : 'negative'}`}>
                            {fmtVal(livePnl, '$')} ({livePnlPct >= 0 ? '+' : ''}{livePnlPct.toFixed(4)}%)
                        </span>
                    )}
                </div>
            </div>

            {/* Stats do config */}
            <div className="session-card-stats">
                <span className="session-stat">{cfg.leverage || 1}x</span>
                <span className="session-stat">{cfg.feeType || 'maker'}</span>
                {cfg.operationMode === 'counter_trend' || cfg.operationMode === 'post_funding_follow' ? (
                    <span className="session-stat" title="Delay pós-virada" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaClock />
                        Delay {cfg.entrySeconds || 30}s · sem timeout
                    </span>
                ) : (
                    <span className="session-stat" title="Entrada / Saída" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaClock />
                        {cfg.entrySeconds || 30}s / {cfg.exitSeconds || 30}s
                    </span>
                )}
                {cfg.stopLossPct != null && (
                    <span className="session-stat stop-loss-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaShieldHalved />
                        SL {cfg.stopLossPct}%
                    </span>
                )}
                {cfg.stopLossUsd != null && (
                    <span className="session-stat stop-loss-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaShieldHalved />
                        SL ${cfg.stopLossUsd}
                    </span>
                )}
                {cfg.targetTakeProfitPct != null && (
                    <span className="session-stat tp-badge" style={{ color: 'var(--success-color)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaBullseye />
                        TP {cfg.targetTakeProfitPct}%
                    </span>
                )}
                {cfg.trailingStopPct != null && (
                    <span className="session-stat stop-loss-badge" style={{ color: 'var(--warning-color)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaArrowTrendDown />
                        TSL {cfg.trailingStopPct}%{cfg.trailingStartProfitPct != null ? ` (ativa em +${cfg.trailingStartProfitPct}%)` : ''}
                    </span>
                )}
                {cfg.minProfitPct != null && (
                    <span className="session-stat min-profit-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaCircleCheck />
                        Min {cfg.minProfitPct}%
                    </span>
                )}
                <span className="session-stat">{session.totalTrades || 0} trades</span>
            </div>

            {/* Histórico de Trades do Bot Ativo */}
            {session.trades && session.trades.length > 0 && (
                <div className="session-active-trades">
                    <div className="session-edit-title" style={{ marginTop: '12px', fontSize: '11px', color: 'var(--text-muted)' }}>ÚLTIMOS TRADES</div>
                    <div className="session-trades-list">
                        {session.trades.slice(0, 10).map(t => {
                            const tradePnl = Number(t.totalPnl ?? t.total_pnl ?? 0);
                            return (
                                <div key={t.id} className="active-trade-row">
                                    <span className={`active-trade-dir ${t.direction === 'SHORT' ? 'short' : 'long'}`}>
                                    {t.symbol.replace('USDT', '')}
                                    </span>
                                    <span className="active-trade-time">{t.closeTime?.split(' ')[1] ?? '—'}</span>
                                    <span className={`active-trade-pnl ${tradePnl >= 0 ? 'positive' : 'negative'}`}>
                                        {tradePnl >= 0 ? 'Lucro ' : 'Perda '}
                                        {fmtVal(tradePnl, '$')}
                                    </span>
                                </div>
                            );
                        })}
                        {session.trades.length > 10 && (
                            <div className="active-trade-row more-trades" style={{ justifyContent: 'center', opacity: 0.6, fontSize: '10px' }}>
                                + {session.trades.length - 10} trades ocultos
                            </div>
                        )}
                    </div>
                </div>
            )}

            <div className="session-card-actions" style={{ marginTop: '16px', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', gap: '6px' }}>
                    <button className="session-edit-btn" onClick={(e) => { e.stopPropagation(); onEdit(isEditing ? null : session.sessionId); }}>
                        <FaPencil style={{ marginRight: '5px' }} /> {isEditing ? 'Fechar' : 'Editar'}
                    </button>
                    {positions.length > 0 && (
                        <button className="session-closeall-btn" onClick={(e) => { e.stopPropagation(); onCloseAll(session.sessionId); }}>
                            <FaBolt style={{ marginRight: '5px' }} /> Fechar Tudo
                        </button>
                    )}
                    <button
                        title="Copiar configuração deste bot para criar um novo"
                        className="session-edit-btn"
                        style={{ padding: '6px 10px', fontSize: '11px', opacity: 0.75 }}
                        onClick={(e) => { e.stopPropagation(); onCopyStrategy?.(buildStrategyFromSession(session)); }}
                    >
                        <FaClipboard style={{ marginRight: '5px' }} /> Copiar
                    </button>
                </div>
                <div style={{ display: 'flex', gap: '6px' }}>
                    <button
                        className="session-edit-btn"
                        style={{ color: session.paused ? 'var(--accent-green, #4ade80)' : 'var(--warning-color, #facc15)' }}
                        onClick={(e) => { e.stopPropagation(); onPauseToggle?.(session.sessionId, session.paused); }}
                    >
                        {session.paused
                            ? <><FaPlay style={{ marginRight: '5px' }} /> Retomar</>
                            : <><FaPause style={{ marginRight: '5px' }} /> Pausar</>
                        }
                    </button>
                    <button className="session-stop-btn" onClick={(e) => { e.stopPropagation(); onStop(session.sessionId); }}>
                        <FaStop style={{ marginRight: '5px' }} /> Parar
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Card de sessão finalizada ───────────────────────────────────────────────

function SessionCard({ session, onDelete, onViewHistory }) {
    const capital = parseFloat(session.capital) || 0;
    const balance = parseFloat(session.balance) || 0;
    const pnl = balance - capital;
    const pnlPct = capital > 0 ? (pnl / capital) * 100 : 0;
    const totalTrades = parseInt(session.total_trades) || 0;
    const wins = parseInt(session.wins) || 0;
    const losses = parseInt(session.losses) || 0;
    const winRate = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(0) : null;

    const formatDate = (iso) => {
        if (!iso) return '—';
        return new Date(iso).toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', year: '2-digit',
            hour: '2-digit', minute: '2-digit',
        });
    };

    // session in SessionCard might store mode directly or in config depending on backend schema,
    // let's fallback to manual if not found
    const modeLabel = getModeShortLabel(session.operation_mode || session.config?.operationMode || 'manual');

    return (
        <div className={`session-card ${pnl >= 0 ? 'card-win' : 'card-loss'}`} onClick={onViewHistory} style={{ cursor: 'pointer' }}>
            <div className="session-card-header">
                <div className="session-name-row">
                    <span className="session-card-exchange">{(session.exchange || 'binance').toUpperCase()}</span>
                    <span className="session-name">{session.session_name || `Bot #${session.id}`}</span>
                    {(session.session_name || '').startsWith('IA-') && (
                        <span title="Criado por IA" style={{ color: 'var(--accent-blue, #6c8eff)', fontSize: '12px', display: 'inline-flex', alignItems: 'center' }}>
                            <FaRobot />
                        </span>
                    )}
                </div>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <span className="session-card-badge" style={{ background: 'rgba(255,255,255,0.1)', color: 'var(--text-secondary)' }}>{modeLabel}</span>
                    <span className="session-card-badge badge-done">FINALIZADO</span>
                </div>
            </div>

            <div className="session-card-symbols">
                {(session.symbols || []).slice(0, 6).map(s => (
                    <span key={s} className="session-sym-tag">{s.replace('USDT', '')}</span>
                ))}
                {(session.symbols || []).length > 6 && (
                    <span className="session-sym-tag session-sym-more">+{(session.symbols || []).length - 6}</span>
                )}
                {(session.symbols || []).length === 0 && (
                    <span className="session-sym-empty">Sem símbolos</span>
                )}
            </div>

            <div className="session-card-pnl">
                <div className="session-pnl-row">
                    <span className="session-pnl-label">Capital inicial</span>
                    <span className="session-pnl-value">${capital.toFixed(2)}</span>
                </div>
                <div className="session-pnl-row">
                    <span className="session-pnl-label">Saldo final</span>
                    <span className="session-pnl-value">${balance.toFixed(2)}</span>
                </div>
                <div className="session-pnl-total">
                    <span className={`session-pnl-number ${pnl >= 0 ? 'positive' : 'negative'}`}>
                        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%)
                    </span>
                </div>
            </div>

            <div className="session-card-stats">
                <span className="session-stat">{totalTrades} trades</span>
                {totalTrades > 0 && (
                    <>
                        <span className="session-stat positive">{wins}W</span>
                        <span className="session-stat negative">{losses}L</span>
                        {winRate !== null && <span className="session-stat">{winRate}% win</span>}
                    </>
                )}
                <span className="session-stat">{session.leverage || 1}x</span>
                <span className="session-stat">{session.fee_type || 'maker'}</span>
                {session.stop_loss_pct != null && (
                    <span className="session-stat stop-loss-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaShieldHalved />
                        SL {session.stop_loss_pct}%
                    </span>
                )}
                {session.target_take_profit_pct != null && (
                    <span className="session-stat tp-badge" style={{ color: 'var(--success-color)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaBullseye />
                        TP {session.target_take_profit_pct}%
                    </span>
                )}
                {session.trailing_stop_pct != null && (
                    <span className="session-stat stop-loss-badge" style={{ color: 'var(--warning-color)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaArrowTrendDown />
                        TSL {session.trailing_stop_pct}%{session.trailing_start_profit_pct != null ? ` (ativa em +${session.trailing_start_profit_pct}%)` : ''}
                    </span>
                )}
                {session.min_profit_pct != null && (
                    <span className="session-stat min-profit-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <FaCircleCheck />
                        Min {session.min_profit_pct}%
                    </span>
                )}
            </div>

            <div className="session-card-dates">
                <span>Início: {formatDate(session.started_at)}</span>
                {session.ended_at && <span>Fim: {formatDate(session.ended_at)}</span>}
            </div>

                <button className="session-delete-btn" onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                        <FaTrashCan />
                        Excluir Sessão
                    </span>
                </button>
        </div>
    );
}
// ─── Modal de Histórico de Trades ───────────────────────────────────────────

function SessionHistoryModal({ session, onClose }) {
    const [sessionDetails, setSessionDetails] = useState(null);
    const [detailsLoading, setDetailsLoading] = useState(true);
    const [selectedSymbol, setSelectedSymbol] = useState(null);
    const [livePrices, setLivePrices] = useState({});
    const [manualSymbol, setManualSymbol] = useState('');
    const [manualTriggerLoading, setManualTriggerLoading] = useState(false);
    const [manualTriggerError, setManualTriggerError] = useState('');
    const [manualTriggerSuccess, setManualTriggerSuccess] = useState('');

    const sessionId = session.sessionId || session.id;
    const modalSession = sessionDetails || session;
    const trades = modalSession.trades || [];
    const rawPositions = modalSession.positions;
    const openPositions = Array.isArray(rawPositions)
        ? rawPositions
        : rawPositions && typeof rawPositions === 'object'
            ? Object.values(rawPositions)
            : [];
    const cfg = modalSession.config || modalSession;
    const exchange = cfg.exchange || 'binance';
    const isSessionActive = Boolean(modalSession.active);

    const uniqueSymbols = [];
    for (const t of trades) {
        const sym = String(t.symbol || '').toUpperCase();
        if (sym && !uniqueSymbols.includes(sym)) uniqueSymbols.push(sym);
    }
    const configuredSymbols = Array.isArray(cfg.symbols)
        ? cfg.symbols.map(s => String(s || '').toUpperCase()).filter(Boolean)
        : [];
    for (const p of openPositions) {
        const sym = String(p.symbol || '').toUpperCase();
        if (sym && !uniqueSymbols.includes(sym)) uniqueSymbols.push(sym);
    }
    for (const sym of configuredSymbols) {
        if (!uniqueSymbols.includes(sym)) uniqueSymbols.push(sym);
    }
    const availableSymbols = uniqueSymbols;

    useEffect(() => {
        let cancelled = false;
        const loadSessionDetails = async (silent = false) => {
            if (!sessionId) {
                setDetailsLoading(false);
                return;
            }
            if (!silent) setDetailsLoading(true);
            try {
                const res = await fetchRealSessionStatus(sessionId);
                if (!cancelled && res) {
                    setSessionDetails(res);
                }
            } catch (e) {
                if (!cancelled) {
                    console.error('Erro ao carregar detalhes da sessão', e);
                }
            } finally {
                if (!cancelled && !silent) setDetailsLoading(false);
            }
        };
        loadSessionDetails(false);
        const id = setInterval(() => {
            loadSessionDetails(true);
        }, 4000);
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [sessionId]);

    useEffect(() => {
        if (availableSymbols.length === 0) {
            setSelectedSymbol(null);
            return;
        }
        setSelectedSymbol(prev => (prev && availableSymbols.includes(prev) ? prev : availableSymbols[0]));
    }, [sessionId, availableSymbols.join('|')]);

    useEffect(() => {
        if (availableSymbols.length === 0) {
            setManualSymbol('');
            return;
        }
        setManualSymbol(prev => (prev && availableSymbols.includes(prev) ? prev : availableSymbols[0]));
    }, [sessionId, availableSymbols.join('|')]);

    useEffect(() => {
        let cancelled = false;
        const symbolsToTrack = openPositions
            .map(p => String(p.symbol || '').toUpperCase())
            .filter(Boolean);
        if (symbolsToTrack.length === 0) {
            setLivePrices({});
            return () => {
                cancelled = true;
            };
        }

        const symbolsSet = new Set(symbolsToTrack);
        const loadPrices = async () => {
            try {
                const res = await fetchFundingRates(exchange);
                if (cancelled) return;
                const map = {};
                for (const r of (res.data || [])) {
                    const sym = String(r.symbol || '').toUpperCase();
                    if (!symbolsSet.has(sym)) continue;
                    const px = Number(r.lastPrice);
                    if (Number.isFinite(px) && px > 0) {
                        map[sym] = px;
                    }
                }
                setLivePrices(map);
            } catch (e) {
                if (!cancelled) {
                    console.error('Erro ao carregar preços atuais para ordens abertas', e);
                }
            }
        };

        loadPrices();
        const id = setInterval(loadPrices, 30000);
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [exchange, openPositions.map(p => String(p.symbol || '').toUpperCase()).join('|')]);

    const parseBrtDateToUnixMs = (dateStr) => {
        if (!dateStr || typeof dateStr !== 'string') return null;
        const m = dateStr.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2}):(\d{2})$/);
        if (!m) return null;
        const [, dd, mm, yyyy, hh, mi, ss] = m;
        // String vem em BRT (UTC-3), converter para UTC.
        return Date.UTC(
            Number(yyyy),
            Number(mm) - 1,
            Number(dd),
            Number(hh) + 3,
            Number(mi),
            Number(ss),
        );
    };

    const toUnixMs = (value) => {
        const n = Number(value);
        if (!Number.isFinite(n) || n <= 0) return null;
        return n > 10_000_000_000 ? n : n * 1000;
    };

    const fmtNumber = (value, fallback = '—') => {
        const n = Number(value);
        if (!Number.isFinite(n)) return fallback;
        const abs = Math.abs(n);
        const decimals = abs >= 100 ? 2 : abs >= 1 ? 4 : abs >= 0.01 ? 6 : 8;
        return n.toFixed(decimals);
    };

    const formatSize = (value) => {
        const n = Number(value);
        if (!Number.isFinite(n) || n <= 0) return '—';
        const decimals = n >= 1000 ? 2 : n >= 1 ? 4 : 6;
        return n.toFixed(decimals);
    };

    const cfgFeeRate = Number(cfg.feeRate ?? cfg.fee_rate ?? (cfg.feeType === 'maker' || cfg.fee_type === 'maker' ? 0.0002 : 0.0005));
    const openRows = openPositions.map((p, idx) => {
        const symbol = String(p.symbol || '').toUpperCase();
        const direction = String(p.direction || '').toUpperCase();
        const entryPrice = Number(p.entryPrice ?? p.entry_price);
        const size = Number(p.size);
        const currentPrice = Number(livePrices[symbol]);
        const positionValue = Number(p.value);
        const baseNotional = Number.isFinite(positionValue) && positionValue > 0
            ? positionValue
            : (Number.isFinite(entryPrice) && Number.isFinite(size) ? entryPrice * size : null);
        const entryMargin = deriveEntryMargin({
            entryMargin: p.entryMargin ?? p.entry_margin,
            notional: baseNotional,
            leverage: cfg.leverage,
        });

        // Funding já recebido no settlement: abs(rate) * value
        const fundingRatePct = Number(p.fundingRatePct ?? p.funding_rate_pct);
        const fundingPnl = Number.isFinite(fundingRatePct) && Number.isFinite(positionValue) && positionValue > 0
            ? Math.abs(fundingRatePct / 100) * positionValue
            : null;

        let livePricePnl = null;
        let livePnl = null;
        let livePnlPct = null;
        let livePricePnlPct = null;
        if (Number.isFinite(entryPrice) && Number.isFinite(size) && Number.isFinite(currentPrice)) {
            const diff = direction === 'SHORT'
                ? entryPrice - currentPrice
                : currentPrice - entryPrice;
            livePricePnl = diff * size;
            livePnl = livePricePnl + (fundingPnl ?? 0);
            if (Number.isFinite(entryMargin) && entryMargin > 0) {
                livePnlPct = (livePnl / entryMargin) * 100;
                livePricePnlPct = (livePricePnl / entryMargin) * 100;
            }
        }

        return {
            rowId: `open-${symbol}-${idx}`,
            rowType: 'open',
            symbol,
            direction,
            openTime: p.openTime || p.open_time || '—',
            closeTime: 'EM ABERTO',
            orderSize: (size && entryPrice) ? (size * entryPrice) : null,
            entryMargin,
            entryPrice,
            exitOrCurrentPrice: currentPrice,
            fundingPnl,
            pricePnl: livePricePnl,
            pricePnlPct: livePricePnlPct,
            totalPnl: livePnl,
            totalPnlPct: livePnlPct,
            timestampMs: parseBrtDateToUnixMs(p.openTime || p.open_time),
        };
    });

    const closedRows = trades.map((t, idx) => {
        const symbol = String(t.symbol || '').toUpperCase();
        const entryPrice = Number(t.entryPrice ?? t.entry_price);
        const feeCost = Number(t.feeCost ?? t.fee_cost);
        const directSize = Number(t.size ?? t.orderSize ?? t.positionSize);
        let orderSize = Number.isFinite(directSize) && directSize > 0 ? directSize : null;
        if (!orderSize && Number.isFinite(feeCost) && feeCost > 0 && Number.isFinite(cfgFeeRate) && cfgFeeRate > 0 && Number.isFinite(entryPrice) && entryPrice > 0) {
            const estimatedValue = feeCost / (cfgFeeRate * 2);
            if (estimatedValue > 0) {
                orderSize = estimatedValue / entryPrice;
            }
        }

        // Calculate size in USDT
        const sizeInUsdt = (orderSize && entryPrice) ? (orderSize * entryPrice) : null;
        const entryMargin = deriveEntryMargin({
            entryMargin: t.entryMargin ?? t.entry_margin,
            notional: sizeInUsdt,
            leverage: cfg.leverage,
            totalPnl: t.totalPnl ?? t.total_pnl,
            totalPnlPct: t.totalPnlPct ?? t.total_pnl_pct,
            pricePnl: t.pricePnl ?? t.price_pnl,
            pricePnlPct: t.pricePnlPct ?? t.price_pnl_pct,
        });

        return {
            rowId: `closed-${t.id ?? idx}`,
            rowType: 'closed',
            symbol,
            direction: String(t.direction || '').toUpperCase(),
            openTime: t.openTime || t.open_time || '—',
            closeTime: t.closeTime || t.close_time || '—',
            orderSize: sizeInUsdt,
            entryMargin,
            entryPrice,
            exitOrCurrentPrice: Number(t.exitPrice ?? t.exit_price),
            fundingPnl: parseFloat(t.fundingPnl || t.funding_pnl || 0),
            pricePnl: parseFloat(t.pricePnl || t.price_pnl || 0),
            pricePnlPct: parseFloat(t.pricePnlPct || t.price_pnl_pct || 0),
            totalPnl: parseFloat(t.totalPnl || t.total_pnl || 0),
            totalPnlPct: parseFloat(t.totalPnlPct || t.total_pnl_pct || 0),
            timestampMs: toUnixMs(t.timestamp || t.trade_timestamp) || parseBrtDateToUnixMs(t.closeTime || t.close_time),
        };
    });

    const historyRows = [...openRows, ...closedRows].sort((a, b) => {
        if (a.rowType !== b.rowType) {
            return a.rowType === 'open' ? -1 : 1;
        }
        return (b.timestampMs || 0) - (a.timestampMs || 0);
    });

    const handleManualTrigger = async () => {
        if (!sessionId) return;
        const symbolToTrigger = (manualSymbol || selectedSymbol || availableSymbols[0] || '').toUpperCase();
        if (!symbolToTrigger) {
            setManualTriggerError('Selecione um símbolo para disparo manual.');
            return;
        }
        setManualTriggerLoading(true);
        setManualTriggerError('');
        setManualTriggerSuccess('');
        try {
            const res = await triggerRealManual(sessionId, { symbol: symbolToTrigger });
            setManualTriggerSuccess(res?.message || `Disparo manual enviado para ${symbolToTrigger}.`);
        } catch (e) {
            setManualTriggerError(e.message || 'Falha ao disparar operação manual.');
        } finally {
            setManualTriggerLoading(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content history-modal" style={{ height: 'min(82vh, 900px)', display: 'flex', flexDirection: 'column' }} onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h3 style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                        <FaFileLines />
                        Histórico Completo de Trades
                    </h3>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                         <span className="session-name-row" style={{ marginRight: '16px'}}>
                            <span className="session-card-exchange">{(exchange || 'binance').toUpperCase()}</span>
                            {modalSession.config?.presetName && PRESET_DISPLAY[modalSession.config.presetName] && (
                                <span style={{ fontSize: '11px', color: PRESET_DISPLAY[modalSession.config.presetName].color, fontWeight: 600 }}>
                                    · {PRESET_DISPLAY[modalSession.config.presetName].name}
                                </span>
                            )}
                            <span className="session-name" style={{ color: 'var(--text-primary)'}}>
                                {modalSession.sessionName || modalSession.session_name || `Bot #${sessionId}`}
                            </span>
                        </span>
                        <button className="modal-close" onClick={onClose} aria-label="Fechar">
                            <FaXmark />
                        </button>
                    </div>
                </div>
                <div className="modal-body" style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
                    {isSessionActive && (
                        <div className="history-manual-trigger">
                            <div className="history-manual-trigger-info">
                                <span className="session-stat" style={{ fontSize: '11px' }}>TIPO: MANUAL</span>
                                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                    Disparo imediato de operação com as regras do bot ativo.
                                </span>
                            </div>
                            <div className="history-manual-trigger-actions">
                                <select
                                    value={manualSymbol}
                                    onChange={(e) => setManualSymbol(e.target.value)}
                                    disabled={manualTriggerLoading || availableSymbols.length === 0}
                                >
                                    {availableSymbols.map(sym => (
                                        <option key={sym} value={sym}>{sym}</option>
                                    ))}
                                </select>
                                <button
                                    className="session-save-btn"
                                    onClick={handleManualTrigger}
                                    disabled={manualTriggerLoading || availableSymbols.length === 0}
                                >
                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                        <FaBolt />
                                        {manualTriggerLoading ? 'Disparando...' : 'Disparo Manual'}
                                    </span>
                                </button>
                            </div>
                        </div>
                    )}
                    {manualTriggerError && (
                        <div className="paper-error" style={{ margin: '0 24px 10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <FaTriangleExclamation />
                            {manualTriggerError}
                        </div>
                    )}
                    {manualTriggerSuccess && (
                        <div style={{
                            margin: '0 24px 10px',
                            padding: '10px 12px',
                            borderRadius: '8px',
                            border: '1px solid rgba(0, 230, 138, 0.35)',
                            background: 'rgba(0, 230, 138, 0.1)',
                            color: 'var(--accent-green)',
                            fontSize: '12px',
                            fontWeight: 600,
                        }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                <FaCircleCheck />
                                {manualTriggerSuccess}
                            </span>
                        </div>
                    )}
                    {detailsLoading && historyRows.length === 0 ? (
                        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>
                            Carregando histórico...
                        </div>
                    ) : historyRows.length === 0 ? (
                        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>
                            Nenhum trade/posição encontrado para esta sessão.
                        </div>
                    ) : (
                        <div style={{ padding: '0 24px' }}>
                            {/* Resumo rápido das ops fechadas */}
                            {(() => {
                                const closed = historyRows.filter(r => r.rowType === 'closed');
                                if (closed.length === 0) return null;
                                const sumPnl = closed.reduce((a, r) => a + (Number.isFinite(r.totalPnl) ? r.totalPnl : 0), 0);
                                const sumFunding = closed.reduce((a, r) => a + (r.fundingPnl != null ? Number(r.fundingPnl) : 0), 0);
                                const wins = closed.filter(r => r.totalPnl > 0).length;
                                const losses = closed.filter(r => r.totalPnl < 0).length;
                                return (
                                    <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', margin: '12px 0', padding: '10px 14px', background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '12px' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>
                                            {closed.length} ops
                                            {wins > 0 && <> · <span className="positive">{wins}W</span></>}
                                            {losses > 0 && <> · <span className="negative">{losses}L</span></>}
                                        </span>
                                        <span>Funding: <span className={sumFunding >= 0 ? 'positive' : 'negative'}>{sumFunding >= 0 ? '+' : ''}${sumFunding.toFixed(4)}</span></span>
                                        <span style={{ fontWeight: 700 }}>P&L Total: <span className={sumPnl >= 0 ? 'positive' : 'negative'} style={{ fontWeight: 700 }}>{sumPnl >= 0 ? '+' : ''}${sumPnl.toFixed(4)}</span></span>
                                    </div>
                                );
                            })()}
                            <div className="history-modal-table-wrap">
                                <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Símbolo</th>
                                        <th>Direção</th>
                                        <th>Hora Entrada</th>
                                        <th>Hora Saída</th>
                                        <th className="right">Tamanho</th>
                                        <th className="right">Margem</th>
                                        <th className="right">Preço Entrada</th>
                                        <th className="right">Preço Saída / Atual</th>
                                        <th className="right">Tx. Funding</th>
                                        <th className="right">L/P Preço</th>
                                        <th className="right">L/P Preço %</th>
                                        <th className="right">PNL Total</th>
                                        <th className="right">PNL Total %</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {historyRows.map(row => {
                                        const isOpen = row.rowType === 'open';
                                        const symbol = row.symbol;
                                        const totalPnl = row.totalPnl;
                                        const totalPnlPct = row.totalPnlPct;
                                        const hasPnl = Number.isFinite(totalPnl);
                                        const hasPnlPct = Number.isFinite(totalPnlPct);
                                        return (
                                            <tr
                                                key={row.rowId}
                                                className={`${symbol === selectedSymbol ? 'trade-row-active' : 'trade-row-clickable'} ${isOpen ? 'trade-row-open' : ''}`.trim()}
                                                onClick={() => setSelectedSymbol(symbol)}
                                            >
                                                <td className="bold">{symbol.replace('USDT', '')}</td>
                                                <td>
                                                    <span className={`badge ${row.direction === 'SHORT' ? 'badge-short' : 'badge-long'}`}>
                                                        {row.direction}
                                                    </span>
                                                </td>
                                                <td className="monospace muted">{row.openTime}</td>
                                                <td className="monospace muted">
                                                    {isOpen ? <span className="history-open-time">EM ABERTO</span> : row.closeTime}
                                                </td>
                                                <td className="right monospace">{formatSize(row.orderSize)}</td>
                                                <td className="right monospace">{fmtMarginUsd(row.entryMargin)}</td>
                                                <td className="right monospace">${fmtNumber(row.entryPrice)}</td>
                                                <td className="right monospace">
                                                    {isOpen ? '—' : Number.isFinite(row.exitOrCurrentPrice) ? (
                                                        <span>${fmtNumber(row.exitOrCurrentPrice)}</span>
                                                    ) : '—'}
                                                </td>
                                                <td className="right monospace">
                                                    {row.fundingPnl !== null && row.fundingPnl !== undefined ? (
                                                        <span className={row.fundingPnl > 0 ? 'positive' : 'negative'}>
                                                            ${Number(row.fundingPnl).toFixed(4)}
                                                        </span>
                                                    ) : '—'}
                                                </td>
                                                <td className="right monospace">
                                                    {row.pricePnl !== null && row.pricePnl !== undefined ? (
                                                        <span className={row.pricePnl >= 0 ? 'positive' : 'negative'}>
                                                            ${Number(row.pricePnl).toFixed(2)}
                                                        </span>
                                                    ) : '—'}
                                                </td>
                                                <td className="right monospace">
                                                    {row.pricePnlPct !== null && row.pricePnlPct !== undefined ? (
                                                        <span className={row.pricePnlPct >= 0 ? 'positive' : 'negative'}>
                                                            {Number(row.pricePnlPct).toFixed(2)}%
                                                        </span>
                                                    ) : '—'}
                                                </td>
                                                <td className="right monospace bold">
                                                    {hasPnl ? (
                                                        <span className={totalPnl >= 0 ? 'positive' : 'negative'}>
                                                          {totalPnl >= 0 ? '+' : ''}
                                                          ${totalPnl.toFixed(2)}
                                                        </span>
                                                    ) : (
                                                        <span className="muted">Calculando...</span>
                                                    )}
                                                </td>
                                                <td className="right monospace bold">
                                                    {hasPnlPct ? (
                                                        <span className={totalPnlPct >= 0 ? 'positive' : 'negative'}>
                                                          {totalPnlPct >= 0 ? '+' : ''}
                                                          {totalPnlPct.toFixed(2)}%
                                                        </span>
                                                    ) : (
                                                        <span className="muted">—</span>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                    {/* Linha de total */}
                                    {historyRows.filter(r => r.rowType === 'closed').length > 0 && (() => {
                                        const closed = historyRows.filter(r => r.rowType === 'closed');
                                        const sumPnl = closed.reduce((a, r) => a + (Number.isFinite(r.totalPnl) ? r.totalPnl : 0), 0);
                                        const sumFunding = closed.reduce((a, r) => a + (r.fundingPnl != null ? Number(r.fundingPnl) : 0), 0);
                                        return (
                                            <tr style={{ borderTop: '2px solid var(--border-color)', background: 'rgba(255,255,255,0.03)', fontWeight: 700 }}>
                                                <td colSpan={7} className="right monospace" style={{ fontSize: '12px', color: 'var(--text-muted)', paddingRight: '12px' }}>
                                                    TOTAL ({closed.length} ops fechadas)
                                                </td>
                                                <td className={`right monospace bold ${sumFunding >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '12px' }}>
                                                    {sumFunding >= 0 ? '+' : ''}${sumFunding.toFixed(4)}
                                                </td>
                                                <td colSpan={2} />
                                                <td className={`right monospace bold ${sumPnl >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '13px' }}>
                                                    {sumPnl >= 0 ? '+' : ''}${sumPnl.toFixed(4)}
                                                </td>
                                                <td />
                                            </tr>
                                        );
                                    })()}
                                </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>

                <div className="modal-footer" style={{ marginTop: '16px', borderTop: '1px solid var(--border-color)', paddingTop: '16px', padding: '0 24px 20px'}}>
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        <strong>Como funciona o fee Maker:</strong> Quando um bot configura "Maker", ele tenta adicionar a ordem no Order Book (Limit Order). Se o mercado for rápido e a ordem cruzar imediatamente (comprar/vender de quem já estava lá), a exchange te cobra a taxa de <strong>Taker</strong> mais alta. Em períodos de muita volatilidade como o Funding, garantir a taxa Maker é arriscado sem sistemas HFT (Alta frequência), por isso em Conta Real (Live) assumimos cenário Taker em simulações realistas e cobramos as taxas conforme o configurado.
                    </div>
                </div>
            </div>
        </div>
    );
}


// ─── Helpers para Logs e Estratégias ─────────────────────────────────────────

function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('pt-BR', {
        day: '2-digit', month: '2-digit', year: '2-digit',
        hour: '2-digit', minute: '2-digit',
    });
}
function fmtPnl(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${n >= 0 ? '+' : ''}$${n.toFixed(2)}`;
}
function fmtPct(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}
function buildStrategyConfig(session) {
    const cfg = session.config || session;
    const operationMode = cfg.operation_mode || cfg.operationMode || 'manual';
    const strategy = {
        operationMode: cfg.operation_mode || cfg.operationMode || 'manual',
        autoDirection: cfg.auto_direction || cfg.autoDirection || 'both',
        autoMaxSymbols: cfg.auto_max_symbols ?? cfg.autoMaxSymbols ?? 8,
        autoMinScore: cfg.auto_min_score ?? cfg.autoMinScore ?? 50,
        minFundingRatePct: cfg.min_funding_rate_pct ?? cfg.minFundingRatePct ?? 0.001,
        autoWindowMinutes: cfg.auto_window_minutes ?? cfg.autoWindowMinutes ?? 60,
        symbols: cfg.symbols || [],
        capital: parseFloat(cfg.capital) || 1000,
        leverage: cfg.leverage || 1,
        feeType: cfg.fee_type || cfg.feeType || 'maker',
        entrySeconds: cfg.entry_seconds ?? cfg.entrySeconds ?? 30,
        stopLossPct: cfg.stop_loss_pct ?? cfg.stopLossPct ?? null,
        stopLossUsd: cfg.stop_loss_usd ?? cfg.stopLossUsd ?? null,
        minProfitPct: cfg.min_profit_pct ?? cfg.minProfitPct ?? null,
        targetTakeProfitPct: cfg.target_take_profit_pct ?? cfg.targetTakeProfitPct ?? null,
        trailingStopPct: cfg.trailing_stop_pct ?? cfg.trailingStopPct ?? null,
        trailingStartProfitPct: cfg.trailing_start_profit_pct ?? cfg.trailingStartProfitPct ?? null,
        exchange: cfg.exchange || 'binance',
    };
    // Motivo: não persistir exitSeconds ao salvar estratégia de modo sem timeout.
    if (operationMode !== 'counter_trend' && operationMode !== 'post_funding_follow') {
        strategy.exitSeconds = cfg.exit_seconds ?? cfg.exitSeconds ?? 30;
    }
    return strategy;
}

// ─── Modal para salvar estratégia ───────────────────────────────────────────

function SaveStrategyModal({ config, onSave, onClose }) {
    const [name, setName] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    const handleSave = async () => {
        const trimmed = name.trim();
        if (!trimmed) { setError('Informe um nome para a estratégia'); return; }
        setSaving(true);
        setError('');
        try {
            await onSave(trimmed, config);
            onClose();
        } catch (e) {
            setError(e.message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose} style={{ zIndex: 10001 }}>
            <div className="modal-content" style={{ maxWidth: '420px', width: '90%' }} onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h3 style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                        <FaFloppyDisk />
                        Salvar Estratégia
                    </h3>
                    <button className="modal-close" onClick={onClose} aria-label="Fechar">
                        <FaXmark />
                    </button>
                </div>
                <div className="modal-body" style={{ padding: '20px 24px' }}>
                    <div className="config-field">
                        <label>Nome da Estratégia</label>
                        <input
                            type="text"
                            value={name}
                            onChange={e => setName(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') handleSave(); }}
                            placeholder="Ex: Funding Sniping 1h Agressivo"
                            maxLength={80}
                            autoFocus
                        />
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
                        Modo: <strong>{getModeLongLabel(config?.operationMode || 'manual')}</strong> ·
                        Capital: <strong>${parseFloat(config?.capital || 0).toFixed(0)}</strong> ·
                        Alavancagem: <strong>{config?.leverage || 1}x</strong>
                    </div>
                    {error && (
                        <div className="paper-error" style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <FaTriangleExclamation />
                            {error}
                        </div>
                    )}
                </div>
                <div className="modal-footer" style={{ padding: '0 24px 20px', display: 'flex', gap: '8px' }}>
                    <button className="session-save-btn" onClick={handleSave} disabled={saving}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <FaFloppyDisk />
                            {saving ? 'Salvando...' : 'Salvar'}
                        </span>
                    </button>
                    <button className="session-cancel-btn" onClick={onClose}>Cancelar</button>
                </div>
            </div>
        </div>
    );
}

// ─── Seção de Estratégias Salvas ─────────────────────────────────────────────

function SavedStrategiesSection({ strategies, onDelete, onUse }) {
    if (!strategies.length) return <div className="sessions-empty" style={{ marginTop: '12px' }}>Nenhuma estratégia salva.</div>;;

    return (
        <div className="sessions-grid" style={{ padding: '16px 24px' }}>
            {strategies.map(s => (
                <div key={s.id} className="session-card" style={{ cursor: 'default' }}>
                    <div className="session-card-header">
                        <span className="session-name">{s.name}</span>
                        <span className="session-card-badge" style={{ background: 'rgba(99,102,241,0.15)', color: '#818cf8' }}>
                            {(s.config?.exchange || 'binance').toUpperCase()}
                        </span>
                    </div>
                    <div className="session-card-stats" style={{ marginTop: '8px' }}>
                        <span className="session-stat">{getModeLongLabel(s.config?.operationMode || 'manual')}</span>
                        <span className="session-stat">${parseFloat(s.config?.capital || 0).toFixed(0)}</span>
                        <span className="session-stat">{s.config?.leverage || 1}x</span>
                        <span className="session-stat">{s.config?.feeType || 'maker'}</span>
                        {s.config?.stopLossPct != null && (
                            <span className="session-stat stop-loss-badge">SL {s.config.stopLossPct}%</span>
                        )}
                        {s.config?.targetTakeProfitPct != null && (
                            <span className="session-stat tp-badge">TP {s.config.targetTakeProfitPct}%</span>
                        )}
                        {s.config?.trailingStopPct != null && (
                            <span className="session-stat stop-loss-badge">
                                TSL {s.config.trailingStopPct}%{s.config?.trailingStartProfitPct != null ? ` @ +${s.config.trailingStartProfitPct}%` : ''}
                            </span>
                        )}
                    </div>
                    {s.config?.symbols?.length > 0 && (
                        <div className="session-card-symbols" style={{ marginTop: '8px' }}>
                            {s.config.symbols.slice(0, 6).map(sym => (
                                <span key={sym} className="session-sym-tag">{sym.replace('USDT', '')}</span>
                            ))}
                            {s.config.symbols.length > 6 && (
                                <span className="session-sym-tag session-sym-more">+{s.config.symbols.length - 6}</span>
                            )}
                        </div>
                    )}
                    <div className="session-card-dates" style={{ marginTop: '8px' }}>
                        Salva em: {fmtDate(s.createdAt)}
                    </div>
                    <div className="session-card-actions" style={{ marginTop: '12px' }}>
                        <button
                            className="session-edit-btn"
                            style={{ background: 'rgba(99,102,241,0.15)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.3)' }}
                            onClick={() => onUse(s.config)}
                        >
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                <FaCirclePlay />
                                Usar Estratégia
                            </span>
                        </button>
                        <button className="session-delete-btn" onClick={() => onDelete(s.id, s.name)}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                <FaTrashCan />
                                Remover
                            </span>
                        </button>
                    </div>
                </div>
            ))}
        </div>
    );
}

// ─── Tabela de Bots ──────────────────────────────────────────────────────────

function BotsTable({ sessions, onCopyStrategy, onSaveStrategy, onAIAnalyze }) {
    const [expanded, setExpanded] = useState(null);

    return (
        sessions.length === 0 ? (
            <div className="sessions-empty" style={{ marginTop: '12px' }}>Nenhum bot criado ainda.</div>
        ) : (
            <div style={{ overflowX: 'auto', padding: '16px 24px' }}>
                <table className="data-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Nome</th>
                            <th>Exchange</th>
                            <th>Modo</th>
                            <th>Capital</th>
                            <th>Saldo Final</th>
                            <th className="right">P&L</th>
                            <th>Trades</th>
                            <th>Status</th>
                            <th>Início</th>
                            <th>Fim</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sessions.map(s => {
                            const capital = parseFloat(s.capital) || 0;
                            const balance = parseFloat(s.balance) || 0;
                            const pnl = balance - capital;
                            const pnlPct = capital > 0 ? (pnl / capital) * 100 : 0;
                            const cfg = s.config || s;
                            const modeRaw = cfg.operation_mode || cfg.operationMode || 'manual';
                            const modeLabel = getModeLongLabel(modeRaw);
                            const isExp = expanded === (s.id || s.sessionId);

                            return [
                                <tr
                                    key={s.id || s.sessionId}
                                    className="trade-row-clickable"
                                    onClick={() => setExpanded(prev => prev === (s.id || s.sessionId) ? null : (s.id || s.sessionId))}
                                >
                                    <td className="monospace muted">{s.id || s.sessionId}</td>
                                    <td className="bold">{s.session_name || s.sessionName || `Bot #${s.id || s.sessionId}`}</td>
                                    <td>{(s.exchange || 'binance').toUpperCase()}</td>
                                    <td>
                                        <span className="session-stat" style={{ fontSize: '11px' }}>{modeLabel}</span>
                                    </td>
                                    <td className="monospace">${capital.toFixed(2)}</td>
                                    <td className="monospace">${balance.toFixed(2)}</td>
                                    <td className={`right monospace bold ${pnl >= 0 ? 'positive' : 'negative'}`}>
                                        {fmtPnl(pnl)} ({fmtPct(pnlPct)})
                                    </td>
                                    <td className="monospace">{s.total_trades || s.totalTrades || 0}</td>
                                    <td>
                                        {s.active
                                            ? <span className="status-badge status-badge--active">ATIVO</span>
                                            : <span className="status-badge status-badge--done">ENCERRADO</span>
                                        }
                                    </td>
                                    <td className="monospace muted" style={{ fontSize: '11px' }}>{fmtDate(s.started_at)}</td>
                                    <td className="monospace muted" style={{ fontSize: '11px' }}>{fmtDate(s.ended_at)}</td>
                                    <td>
                                        <div className="table-actions" onClick={e => e.stopPropagation()}>
                                            <button
                                                title="Análise IA"
                                                className="table-action-btn"
                                                style={{ padding: '4px 8px', background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.3)' }}
                                                onClick={() => onAIAnalyze?.(s.id || s.sessionId)}
                                            >
                                                <img src={aiIcon} alt="IA" style={{ width: '15px', height: '15px', verticalAlign: 'middle' }} />
                                            </button>
                                            <button
                                                title="Copiar estratégia para novo bot"
                                                className="table-action-btn"
                                                onClick={() => onCopyStrategy(buildStrategyConfig(s))}
                                            >
                                                Copiar
                                            </button>
                                            <button
                                                title="Salvar estratégia com nome"
                                                className="table-action-btn table-action-btn--save"
                                                onClick={() => onSaveStrategy(buildStrategyConfig(s))}
                                            >
                                                Salvar
                                            </button>
                                        </div>
                                    </td>
                                </tr>,
                                isExp && (
                                    <tr key={`exp-${s.id || s.sessionId}`}>
                                        <td colSpan={12} style={{ padding: '8px 16px', background: 'rgba(255,255,255,0.02)' }}>
                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', fontSize: '12px' }}>
                                                <span>Símbolos:</span>
                                                {(s.symbols || []).map(sym => (
                                                    <span key={sym} className="session-sym-tag">{sym.replace('USDT', '')}</span>
                                                ))}
                                                {(!s.symbols || s.symbols.length === 0) && <span className="muted">—</span>}
                                                <span style={{ marginLeft: '12px' }}>Alavancagem: <strong>{s.leverage || 1}x</strong></span>
                                                <span>Fee: <strong>{s.fee_type || 'maker'}</strong></span>
                                                {s.stop_loss_pct != null && <span>SL: <strong>{s.stop_loss_pct}%</strong></span>}
                                                {s.min_profit_pct != null && <span>Min Profit: <strong>{s.min_profit_pct}%</strong></span>}
                                                {s.target_take_profit_pct != null && <span>Take Profit: <strong>{s.target_take_profit_pct}%</strong></span>}
                                                {s.trailing_stop_pct != null && (
                                                    <span>
                                                        TSL: <strong>{s.trailing_stop_pct}%</strong>{s.trailing_start_profit_pct != null ? ` @ +${s.trailing_start_profit_pct}%` : ''}
                                                    </span>
                                                )}
                                                <span>Entrada: <strong>{s.entry_seconds ?? 30}s</strong></span>
                                                {s.operation_mode === 'counter_trend' || s.operation_mode === 'post_funding_follow'
                                                    ? <span>Saída: <strong>sem timeout</strong></span>
                                                    : <span>Saída: <strong>{s.exit_seconds ?? 30}s</strong></span>
                                                }
                                            </div>
                                        </td>
                                    </tr>
                                )
                            ];
                        })}
                    </tbody>
                </table>
            </div>
        )
    );
}

// ─── Tabela de Logs de Operações ─────────────────────────────────────────────

function TradesTable({ trades, total, limit, offset, onLoadMore, loadingMore }) {
    const closedTrades = trades.filter(t => !t.isOpen);
    const totalPnlSum = closedTrades.reduce((acc, t) => acc + (Number(t.totalPnl) || 0), 0);
    const totalFeeSum = closedTrades.reduce((acc, t) => acc + (Number(t.feeCost) || 0), 0);
    const totalFundingSum = closedTrades.reduce((acc, t) => acc + (Number(t.fundingPnl) || 0), 0);
    const wins = closedTrades.filter(t => Number(t.totalPnl) > 0).length;
    const losses = closedTrades.filter(t => Number(t.totalPnl) < 0).length;

    return (
        trades.length === 0 ? (
            <div className="sessions-empty" style={{ marginTop: '12px' }}>Nenhuma operação registrada ainda.</div>
        ) : (
            <div style={{ padding: '0 24px', flex: 1 }}>
                {/* Barra de resumo */}
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', margin: '12px 0', padding: '12px 16px', background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '12px' }}>
                    <span style={{ color: 'var(--text-muted)' }}>
                        {closedTrades.length} ops fechadas
                        {wins > 0 && <> · <span className="positive">{wins}W</span></>}
                        {losses > 0 && <> · <span className="negative">{losses}L</span></>}
                        {closedTrades.length > 0 && <> · Taxa: <span style={{ color: 'var(--text-primary)' }}>{((wins / closedTrades.length) * 100).toFixed(0)}%</span></>}
                    </span>
                    <span style={{ marginLeft: 'auto', display: 'flex', gap: '20px' }}>
                        <span>Funding: <span className={totalFundingSum >= 0 ? 'positive' : 'negative'}>{totalFundingSum >= 0 ? '+' : ''}${totalFundingSum.toFixed(4)}</span></span>
                        <span>Fees: <span style={{ color: 'var(--text-muted)' }}>-${totalFeeSum.toFixed(4)}</span></span>
                        <span style={{ fontWeight: 700 }}>P&L Total: <span className={totalPnlSum >= 0 ? 'positive' : 'negative'} style={{ fontWeight: 700 }}>{totalPnlSum >= 0 ? '+' : ''}${totalPnlSum.toFixed(4)}</span></span>
                    </span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Bot</th>
                                <th>Exchange</th>
                                <th>Símbolo</th>
                                <th>Direção</th>
                                <th>Entrada</th>
                                <th>Saída</th>
                                <th className="right">Margem</th>
                                <th className="right">P/Entrada</th>
                                <th className="right">P/Saída</th>
                                <th className="right">Funding</th>
                                <th className="right">Fee</th>
                                <th className="right">PNL</th>
                                <th className="right">PNL % (Mrg/Cap)</th>
                                <th>Motivo</th>
                            </tr>
                        </thead>
                        <tbody>
                            {trades.map(t => {
                                const pnl = Number(t.totalPnl);
                                const pnlPctMargin = Number(t.totalPnlPct);
                                const notional = Number(t.orderSize) > 0 && Number(t.entryPrice) > 0
                                    ? Number(t.orderSize) * Number(t.entryPrice)
                                    : null;
                                const entryMargin = deriveEntryMargin({
                                    entryMargin: t.entryMargin ?? t.entry_margin,
                                    notional,
                                    leverage: t.leverage,
                                    totalPnl: t.totalPnl,
                                    totalPnlPct: t.totalPnlPct,
                                    pricePnl: t.pricePnl,
                                    pricePnlPct: t.pricePnlPct,
                                });
                                const capital = Number(t.capital);
                                const pnlPctCapital = capital > 0 && Number.isFinite(pnl)
                                    ? (pnl / capital) * 100
                                    : NaN;
                                const pctSignal = Number.isFinite(pnlPctCapital) ? pnlPctCapital : pnlPctMargin;
                                const isOpen = t.isOpen;

                                return (
                                    <tr key={t.id || t.rowId} className={`trade-row-clickable ${isOpen ? 'trade-row-open' : ''}`}>
                                        <td className="monospace muted" style={{ fontSize: '11px' }}>{t.id || '—'}</td>
                                        <td style={{ fontSize: '11px', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {t.sessionName || t.session_name || (`Bot #${t.configId || t.config_id || ''}`)}
                                        </td>
                                        <td style={{ fontSize: '11px' }}>{(t.exchange || '—').toUpperCase()}</td>
                                        <td className="bold">{(t.symbol || '').replace('USDT', '')}</td>
                                        <td>
                                            <span className={`badge ${t.direction === 'SHORT' ? 'badge-short' : 'badge-long'}`}>
                                                {t.direction}
                                            </span>
                                        </td>
                                        <td className="monospace muted" style={{ fontSize: '11px' }}>{t.openTime || '—'}</td>
                                        <td className="monospace muted" style={{ fontSize: '11px' }}>
                                            {isOpen ? <span className="history-open-time">EM ABERTO</span> : (t.closeTime || '—')}
                                        </td>
                                        <td className="right monospace" style={{ fontSize: '11px' }}>{fmtMarginUsd(entryMargin)}</td>
                                        <td className="right monospace" style={{ fontSize: '11px' }}>${Number(t.entryPrice).toFixed(4)}</td>
                                        <td className="right monospace" style={{ fontSize: '11px' }}>
                                            {Number.isFinite(Number(t.exitPrice)) ? (
                                                <span className={isOpen ? 'history-live-price' : ''}>
                                                    ${Number(t.exitPrice).toFixed(4)}
                                                </span>
                                            ) : '—'}
                                        </td>
                                        <td className={`right monospace ${Number(t.fundingPnl) >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '11px' }}>
                                            ${Number(t.fundingPnl).toFixed(4)}
                                        </td>
                                        <td className="right monospace muted" style={{ fontSize: '11px' }}>
                                            ${Number(t.feeCost || 0).toFixed(4)}
                                        </td>
                                        <td className={`right monospace bold ${pnl >= 0 ? 'positive' : 'negative'}`}>
                                            {Number.isFinite(pnl) ? fmtPnl(pnl) : '—'}
                                        </td>
                                        <td className={`right monospace bold ${Number.isFinite(pctSignal) ? (pctSignal >= 0 ? 'positive' : 'negative') : 'muted'}`}>
                                            <div>
                                                {Number.isFinite(pnlPctMargin) ? `Mrg ${fmtPct(pnlPctMargin)}` : 'Mrg —'}
                                            </div>
                                            <div className="muted" style={{ fontSize: '10px', fontWeight: 600, marginTop: '2px' }}>
                                                {Number.isFinite(pnlPctCapital) ? `Cap ${fmtPct(pnlPctCapital)}` : 'Cap —'}
                                            </div>
                                        </td>
                                        <td style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                            {t.closeReason || '—'}
                                        </td>
                                    </tr>
                                );
                            })}
                            {/* Linha de totais */}
                            {closedTrades.length > 0 && (
                                <tr style={{ borderTop: '2px solid var(--border-color)', background: 'rgba(255,255,255,0.03)', fontWeight: 700 }}>
                                    <td colSpan={10} className="right monospace" style={{ fontSize: '12px', color: 'var(--text-muted)', paddingRight: '12px' }}>
                                        TOTAL ({closedTrades.length} ops)
                                    </td>
                                    <td className={`right monospace bold ${totalFundingSum >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '12px' }}>
                                        {totalFundingSum >= 0 ? '+' : ''}${totalFundingSum.toFixed(4)}
                                    </td>
                                    <td className="right monospace muted" style={{ fontSize: '12px' }}>
                                        ${totalFeeSum.toFixed(4)}
                                    </td>
                                    <td className={`right monospace bold ${totalPnlSum >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '13px' }}>
                                        {totalPnlSum >= 0 ? '+' : ''}${totalPnlSum.toFixed(4)}
                                    </td>
                                    <td colSpan={2} />
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
                {trades.length < (total ?? 0) && (
                    <div style={{ textAlign: 'center', marginTop: '16px', paddingBottom: '16px' }}>
                        <button className="refresh-btn" onClick={onLoadMore} disabled={loadingMore}>
                            {loadingMore ? 'Carregando...' : `↓ Carregar mais (${(total ?? 0) - trades.length} restantes)`}
                        </button>
                    </div>
                )}
            </div>
        )
    );
}

// ─── Guia de Estratégias ──────────────────────────────────────────────────────

function StrategyGuideTab() {
    const [openSection, setOpenSection] = useState('tp');

    const Section = ({ id, title, icon, children }) => (
        <div style={{ marginBottom: '12px', border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
            <button
                onClick={() => setOpenSection(openSection === id ? null : id)}
                style={{
                    width: '100%', textAlign: 'left', background: openSection === id ? 'rgba(99,102,241,0.08)' : 'var(--card-bg)',
                    border: 'none', padding: '14px 20px', cursor: 'pointer',
                    color: 'var(--text-primary)', fontWeight: '600', fontSize: '14px',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}
            >
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                    {icon}
                    <span>{title}</span>
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: '18px' }}>{openSection === id ? '−' : '+'}</span>
            </button>
            {openSection === id && (
                <div style={{ padding: '20px', background: 'var(--card-bg)', borderTop: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '13px', lineHeight: '1.7' }}>
                    {children}
                </div>
            )}
        </div>
    );

    const tableStyle = { width: '100%', borderCollapse: 'collapse', marginTop: '12px', fontSize: '12px' };
    const thStyle = { padding: '8px 12px', background: 'rgba(255,255,255,0.04)', textAlign: 'left', color: 'var(--text-muted)', fontWeight: '600', borderBottom: '1px solid var(--border-color)' };
    const tdStyle = { padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)' };
    const highlight = { color: 'var(--accent-color)', fontWeight: '700' };
    const green = { color: 'var(--accent-green)', fontWeight: '600' };
    const yellow = { color: '#f59e0b', fontWeight: '600' };
    const red = { color: 'var(--accent-red)', fontWeight: '600' };

    return (
        <div style={{ maxWidth: '820px', margin: '0 auto', padding: '0 4px' }}>
            <div style={{ marginBottom: '24px' }}>
                <h2 style={{ margin: '0 0 6px', fontSize: '18px', display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                    <FaBookOpen />
                    Guia de Estratégias
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                    Entenda como cada modo funciona, como o TP% é calculado e quando usar cada estratégia.
                </p>
            </div>

            {/* SEÇÃO 1: TP% */}
            <Section id="tp" icon={<FaBullseye />} title="Como funciona o Take Profit (TP%)">
                <p>
                    O <strong>TP%</strong> é calculado sobre a <strong style={highlight}>margem</strong> — seu dinheiro real em risco por moeda — e <strong>não</strong> sobre o capital total nem sobre o tamanho da posição.
                </p>

                <div style={{ background: 'rgba(99,102,241,0.07)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: '6px', padding: '14px 16px', marginTop: '12px' }}>
                    <strong>Fórmula:</strong>
                    <div style={{ fontFamily: 'monospace', marginTop: '8px', lineHeight: '2' }}>
                        Margem por moeda = Capital ÷ Nº de moedas<br/>
                        Posição = Margem × Alavancagem<br/>
                        Lucro alvo ($) = Margem × (TP% ÷ 100)<br/>
                        <span style={green}>Move de preço necessário ≈ TP% ÷ Alavancagem</span>
                    </div>
                </div>

                <p style={{ marginTop: '16px' }}>
                    <strong>Exemplo com os presets CT Padrão</strong> ($25 capital, 4 moedas, 10x leverage, TP 3%):
                </p>
                <div style={{ fontFamily: 'monospace', background: 'rgba(0,0,0,0.2)', padding: '12px 16px', borderRadius: '6px', lineHeight: '2', fontSize: '12px' }}>
                    Margem por moeda: $25 ÷ 4 = <strong style={highlight}>$6,25</strong><br/>
                    Posição: $6,25 × 10x = <strong>$62,50</strong><br/>
                    Lucro alvo: $6,25 × 3% = <strong style={green}>$0,19</strong><br/>
                    Fee estimado: $62,50 × 0,05% × 2 = $0,06<br/>
                    Preço precisa mover: ($0,19 + $0,06) ÷ $62,50 = <strong style={green}>~0,4%</strong>
                </div>

                <p style={{ marginTop: '16px' }}><strong>Comparação entre presets:</strong></p>
                <table style={tableStyle}>
                    <thead>
                        <tr>
                            <th style={thStyle}>Preset</th>
                            <th style={thStyle}>Leverage</th>
                            <th style={thStyle}>Posição</th>
                            <th style={thStyle}>TP%</th>
                            <th style={thStyle}>Lucro alvo</th>
                            <th style={thStyle}>Move de preço</th>
                            <th style={thStyle}>Lucro real $</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td style={tdStyle}>CT Leve</td>
                            <td style={tdStyle}>5x</td>
                            <td style={tdStyle}>$31,25</td>
                            <td style={tdStyle}>3%</td>
                            <td style={tdStyle}>$0,19</td>
                            <td style={{ ...tdStyle, ...green }}>~0,6%</td>
                            <td style={{ ...tdStyle, ...green }}>$0,13</td>
                        </tr>
                        <tr>
                            <td style={tdStyle}>CT Padrão</td>
                            <td style={tdStyle}>10x</td>
                            <td style={tdStyle}>$62,50</td>
                            <td style={tdStyle}>3%</td>
                            <td style={tdStyle}>$0,19</td>
                            <td style={{ ...tdStyle, ...green }}>~0,4%</td>
                            <td style={{ ...tdStyle, ...green }}>$0,13</td>
                        </tr>
                        <tr>
                            <td style={tdStyle}>CT Agressivo</td>
                            <td style={tdStyle}>20x</td>
                            <td style={tdStyle}>$125,00</td>
                            <td style={tdStyle}>5%</td>
                            <td style={tdStyle}>$0,31</td>
                            <td style={{ ...tdStyle, ...yellow }}>~0,25%</td>
                            <td style={{ ...tdStyle, ...green }}>$0,19</td>
                        </tr>
                    </tbody>
                </table>
                <p style={{ marginTop: '12px', color: 'var(--text-muted)', fontSize: '12px' }}>
                    * Lucro real = lucro alvo menos fee. Com 4 moedas simultaneamente, multiplique por 4 em caso de todos os trades fecharem no TP.
                </p>
            </Section>

            {/* SEÇÃO 2: Sniping de Funding */}
            <Section id="sniping" icon={<FaBolt />} title="Sniping de Funding (modos auto_expiring / auto_strongest / auto_highest_rate)">
                <p>
                    A estratégia principal do bot. O objetivo é <strong>capturar o pagamento de funding</strong> que acontece a cada 8 horas.
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ ...highlight, fontSize: '18px', minWidth: '30px', textAlign: 'center' }}>①</span>
                        <span>Bot detecta moeda com funding rate alta se aproximando da virada</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ ...highlight, fontSize: '18px', minWidth: '30px', textAlign: 'center' }}>②</span>
                        <span>Entra <strong>X segundos antes</strong> da virada (<em>entry_seconds</em>)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ ...highlight, fontSize: '18px', minWidth: '30px', textAlign: 'center' }}>③</span>
                        <span>Recebe o pagamento de funding no momento da virada</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ ...highlight, fontSize: '18px', minWidth: '30px', textAlign: 'center' }}>④</span>
                        <span>Aguarda <strong>X segundos após</strong> (<em>exit_seconds</em>) e fecha a posição</span>
                    </div>
                </div>

                <div style={{ marginTop: '16px', background: 'rgba(0,230,138,0.05)', border: '1px solid rgba(0,230,138,0.15)', borderRadius: '6px', padding: '12px 16px' }}>
                    <strong>Direção da posição:</strong><br/>
                    <span style={green}>Funding positivo (+)</span> → Longs pagando → Abrir <strong>SHORT</strong> para receber<br/>
                    <span style={red}>Funding negativo (−)</span> → Shorts pagando → Abrir <strong>LONG</strong> para receber
                </div>

                <p style={{ marginTop: '14px' }}>
                    <strong>Lucro principal:</strong> funding_pnl (pagamento recebido) + price_pnl (variação de preço) − fee<br/>
                    <strong>Risco:</strong> volatilidade de preço nos segundos ao redor da virada
                </p>
            </Section>

            {/* SEÇÃO 3: Counter-Trend */}
            <Section id="ct" icon={<FaArrowRotateLeft />} title="Contra-Tendência (counter_trend) — Por que o preço se move">
                <p>
                    Esta estratégia explora o <strong>desequilíbrio criado pelo próprio funding rate</strong>. Veja a lógica:
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
                    <div style={{ background: 'rgba(255,77,106,0.06)', border: '1px solid rgba(255,77,106,0.2)', borderRadius: '6px', padding: '14px' }}>
                        <div style={{ fontWeight: '700', marginBottom: '8px', color: 'var(--accent-red)' }}>Funding NEGATIVO (−)</div>
                        <div style={{ fontSize: '12px', lineHeight: '1.8' }}>
                            Shorts pagando longs<br/>
                            → Incentivo para abrir LONG<br/>
                            → Muitos longs artificiais acumulados<br/>
                            → Pressão compradora artificial<br/>
                            <strong>Na virada:</strong> longs fecham em massa<br/>
                            <span style={red}>→ Pressão vendedora → Preço CAIA</span><br/>
                            <strong>Bot abre: SHORT</strong>
                        </div>
                    </div>
                    <div style={{ background: 'rgba(0,230,138,0.06)', border: '1px solid rgba(0,230,138,0.2)', borderRadius: '6px', padding: '14px' }}>
                        <div style={{ fontWeight: '700', marginBottom: '8px', color: 'var(--accent-green)' }}>Funding POSITIVO (+)</div>
                        <div style={{ fontSize: '12px', lineHeight: '1.8' }}>
                            Longs pagando shorts<br/>
                            → Incentivo para abrir SHORT<br/>
                            → Muitos shorts artificiais acumulados<br/>
                            → Pressão vendedora artificial<br/>
                            <strong>Na virada:</strong> shorts fecham em massa<br/>
                            <span style={green}>→ Pressão compradora → Preço SOBE</span><br/>
                            <strong>Bot abre: LONG</strong>
                        </div>
                    </div>
                </div>

                <div style={{ marginTop: '16px', background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: '6px', padding: '12px 16px', fontSize: '12px' }}>
                    <strong style={yellow}>Por que existe essa volatilidade extra?</strong><br/>
                    Além do fechamento normal de posições, podem ocorrer <strong>liquidações em cascata</strong>: o fechamento em massa empurra o preço o suficiente para acionar stops de outros traders, amplificando o movimento.
                </div>

                <div style={{ marginTop: '14px' }}>
                    <strong>Parâmetros importantes para CT:</strong>
                    <table style={tableStyle}>
                        <thead>
                            <tr>
                                <th style={thStyle}>Campo</th>
                                <th style={thStyle}>No CT significa</th>
                                <th style={thStyle}>Recomendado</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td style={tdStyle}>Delay pós-virada (s)</td>
                                <td style={tdStyle}>Segundos para esperar após a virada antes de entrar</td>
                                <td style={{ ...tdStyle, ...green }}>3–10s</td>
                            </tr>
                            <tr>
                                <td style={tdStyle}>Timeout máximo</td>
                                <td style={tdStyle}>Não se aplica no CT: posição não expira por tempo</td>
                                <td style={{ ...tdStyle, ...green }}>Sem timeout</td>
                            </tr>
                            <tr>
                                <td style={tdStyle}>Take Profit (%)</td>
                                <td style={tdStyle}>% da margem de lucro alvo — sem funding neste modo</td>
                                <td style={{ ...tdStyle, ...green }}>3–5%</td>
                            </tr>
                            <tr>
                                <td style={tdStyle}>Stop Loss (%)</td>
                                <td style={tdStyle}>% da margem máxima de perda aceitável</td>
                                <td style={{ ...tdStyle, ...yellow }}>1,5–2%</td>
                            </tr>
                            <tr>
                                <td style={tdStyle}>Fee</td>
                                <td style={tdStyle}>Use Taker — entra depois da virada, precisa ser imediato</td>
                                <td style={{ ...tdStyle, ...yellow }}>Taker</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </Section>

            {/* SEÇÃO 4: Stop Loss */}
            <Section id="sl" icon={<FaStop />} title="Stop Loss — dois tipos disponíveis">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '6px', padding: '14px', border: '1px solid var(--border-color)' }}>
                        <div style={{ fontWeight: '700', marginBottom: '8px' }}>Stop Loss por Preço (%)</div>
                        <div style={{ fontSize: '12px', lineHeight: '1.8' }}>
                            Fecha se o <strong>preço</strong> se mover X% contra você.<br/>
                            Calculado sobre a margem.<br/><br/>
                            Exemplo: SL 1,5% com 10x<br/>
                            → Margem $6,25<br/>
                            → Fecha se price_pnl {'<'} −$0,09<br/>
                            → Preço move ~0,15% contra
                        </div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '6px', padding: '14px', border: '1px solid var(--border-color)' }}>
                        <div style={{ fontWeight: '700', marginBottom: '8px' }}>Stop Loss em USD ($)</div>
                        <div style={{ fontSize: '12px', lineHeight: '1.8' }}>
                            Fecha se a <strong>perda total</strong> (preço + funding − fee) ultrapassar $X.<br/><br/>
                            Exemplo: SL $5<br/>
                            → Fecha quando total_pnl {'<'} −$5<br/>
                            → Mais intuitivo para controle de risco
                        </div>
                    </div>
                </div>
                <p style={{ marginTop: '14px', fontSize: '12px', color: 'var(--text-muted)' }}>
                    Você pode configurar os dois ao mesmo tempo — o bot fecha ao primeiro que for atingido. No modo CT, prefira o Stop Loss por % pois é mais preciso para movimentos rápidos.
                </p>
            </Section>

            {/* SEÇÃO 5: Min Profit */}
            <Section id="min" icon={<FaCircleCheck />} title="Lucro Mínimo para Fechar (minProfitPct)">
                <p>
                    Após o <em>exit_seconds</em> (tempo de saída), o bot normalmente fecha a posição. Com <strong>Lucro Mínimo</strong> configurado, ele <strong>aguarda</strong> até que o lucro total atinja X% da margem antes de fechar.
                </p>
                <div style={{ marginTop: '12px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={{ background: 'rgba(0,230,138,0.05)', border: '1px solid rgba(0,230,138,0.15)', borderRadius: '6px', padding: '12px' }}>
                        <strong style={green}>Sem Min Profit</strong>
                        <div style={{ fontSize: '12px', marginTop: '6px', lineHeight: '1.8' }}>
                            Fecha no timeout, seja com lucro ou prejuízo.<br/>
                            Mais previsível, executa rápido.
                        </div>
                    </div>
                    <div style={{ background: 'rgba(99,102,241,0.05)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: '6px', padding: '12px' }}>
                        <strong style={highlight}>Com Min Profit 0.05%</strong>
                        <div style={{ fontSize: '12px', marginTop: '6px', lineHeight: '1.8' }}>
                            Aguarda atingir pelo menos 0,05% de lucro.<br/>
                            Evita sair no vermelho se o preço ainda pode recuperar.<br/>
                            <span style={yellow}>Atenção: pode manter a posição mais tempo.</span>
                        </div>
                    </div>
                </div>
                <p style={{ marginTop: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>
                    No modo Contra-Tendência, <strong>não</strong> é recomendado usar Min Profit — a volatilidade é rápida e pode reverter. Use TP + SL para controle preciso.
                </p>
            </Section>
        </div>
    );
}

// ─── Modal de Logs Global da Conta Real ──────────────────────────────────────

function RealLogsModal({ onClose, activeSessions, inactiveSessions, onCopyStrategy }) {
    const [trades, setTrades] = useState([]);
    const [tradesTotal, setTradesTotal] = useState(0);
    const [strategies, setStrategies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [error, setError] = useState('');
    const [saveModalConfig, setSaveModalConfig] = useState(null);
    const [activeTab, setActiveTab] = useState('bots'); // 'bots' | 'trades' | 'strategies' | 'ai'
    const [aiModalSessionId, setAiModalSessionId] = useState(null);

    // Combine current open positions across all active sessions dynamically
    const openPositions = useMemo(() => {
        let allOpens = [];
        for (const session of activeSessions) {
            const positionsArray = Array.isArray(session.positions)
                ? session.positions
                : session.positions && typeof session.positions === 'object'
                    ? Object.values(session.positions)
                    : [];

            for (const p of positionsArray) {
                // Approximate live numbers just to display it, you can add livePrices fetch if you want precision
                const entryPrice = Number(p.entryPrice ?? p.entry_price);
                const size = Number(p.size);
                const leverage = Number(session.config?.leverage ?? session.leverage ?? 0);
                const notional = Number.isFinite(entryPrice) && Number.isFinite(size) && entryPrice > 0 && size > 0
                    ? entryPrice * size
                    : null;
                const entryMargin = deriveEntryMargin({
                    entryMargin: p.entryMargin ?? p.entry_margin,
                    notional,
                    leverage,
                });

                allOpens.push({
                    isOpen: true,
                    rowId: `open-${p.symbol}-${session.sessionId}`,
                    id: `Aberto - ${session.sessionId}`,
                    sessionName: session.sessionName || `Bot #${session.sessionId}`,
                    configId: session.sessionId,
                    exchange: session.config?.exchange || 'binance',
                    symbol: p.symbol,
                    direction: p.direction,
                    openTime: p.openTime || p.open_time || '—',
                    closeTime: '—',
                    entryPrice: entryPrice,
                    exitPrice: p.currentPrice || entryPrice,
                    entryMargin,
                    fundingPnl: 0,
                    feeCost: 0,
                    totalPnl: 0,
                    totalPnlPct: 0,
                    leverage,
                    capital: Number(session.config?.capital ?? session.capital ?? 0),
                    closeReason: '—',
                    timestampMs: new Date().getTime(),
                });
            }
        }
        return allOpens;
    }, [activeSessions]);

    const LIMIT = 100;

    const loadAll = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const [tradesRes, stratRes] = await Promise.all([
                fetchRealLogs({ limit: LIMIT, offset: 0 }),
                fetchStrategies(),
            ]);
            setTrades(tradesRes.data || []);
            setTradesTotal(tradesRes.total ?? 0);
            setStrategies(stratRes.data || []);
        } catch (e) {
            setError(e.message || 'Erro ao carregar dados.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadAll(); }, [loadAll]);

    const handleLoadMoreTrades = async () => {
        setLoadingMore(true);
        try {
            const res = await fetchRealLogs({ limit: LIMIT, offset: trades.length });
            setTrades(prev => [...prev, ...(res.data || [])]);
        } catch (e) {
            alert(e.message);
        } finally {
            setLoadingMore(false);
        }
    };

    const handleSaveStrategy = async (name, config) => {
        await saveStrategy(name, config);
        const res = await fetchStrategies();
        setStrategies(res.data || []);
    };

    const handleDeleteStrategy = async (id, name) => {
        setModalConfig({
            title: 'Remover Estratégia',
            message: `Remover estratégia "${name}"?`,
            onConfirm: async () => {
                try {
                    await deleteStrategy(id);
                    setStrategies(prev => prev.filter(s => s.id !== id));
                    setModalConfig(null);
                } catch (e) {
                    setModalConfig({ isAlert: true, message: e.message, title: 'Erro' });
                }
            }
        });
    };

    const handleUseStrategy = (config) => {
        onCopyStrategy(config);
        onClose();
    };

    const allSessions = [...activeSessions, ...inactiveSessions].sort((a,b) => (b.id||b.sessionId) - (a.id||a.sessionId));
    const allTradesJoined = [...openPositions, ...trades];

    return (
        <div className="modal-overlay" onClick={onClose} style={{ zIndex: 9999 }}>
            <div className="modal-content history-modal" style={{ maxWidth: '1200px', width: '95%', height: '85vh', display: 'flex', flexDirection: 'column' }} onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h3 style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                        <FaTableList />
                        Logs — Conta Real
                    </h3>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <button className="refresh-btn" onClick={loadAll} disabled={loading}>
                            {loading ? 'Atualizando...' : 'Atualizar'}
                        </button>
                        <button className="modal-close" onClick={onClose} aria-label="Fechar">
                            <FaXmark />
                        </button>
                    </div>
                </div>

                <div className="modal-body" style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', padding: '16px 0' }}>
                    {error && <div className="error-message" style={{ margin: '0 24px 16px' }}>{error}</div>}
                    {loading && <div className="sessions-loading" style={{ margin: '0 24px' }}>Carregando...</div>}

                     {/* Abas */}
                    {!loading && (
                        <>
                            <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', borderBottom: '1px solid var(--border-color)', padding: '0 24px' }}>
                                {[
                                    { key: 'bots', label: `Bots (${allSessions.length})`, icon: <FaRobot /> },
                                    { key: 'trades', label: `Operações (${tradesTotal + openPositions.length})`, icon: <FaClipboard /> },
                                    { key: 'strategies', label: `Estratégias Salvas (${strategies.length})`, icon: <FaFloppyDisk /> },
                                    { key: 'ai', label: 'Análises IA', icon: <FaBrain /> },
                                ].map(tab => (
                                    <button
                                        key={tab.key}
                                        onClick={() => setActiveTab(tab.key)}
                                        style={{
                                            background: 'none',
                                            border: 'none',
                                            borderBottom: activeTab === tab.key ? '2px solid var(--accent-color)' : '2px solid transparent',
                                            color: activeTab === tab.key ? 'var(--text-primary)' : 'var(--text-muted)',
                                            padding: '8px 16px',
                                            cursor: 'pointer',
                                            fontSize: '13px',
                                            fontWeight: activeTab === tab.key ? '600' : '400',
                                            marginBottom: '-1px',
                                        }}
                                    >
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                            {tab.icon}
                                            {tab.label}
                                        </span>
                                    </button>
                                ))}
                            </div>

                            {activeTab === 'bots' && (
                                <BotsTable
                                    sessions={allSessions}
                                    onCopyStrategy={handleUseStrategy}
                                    onSaveStrategy={(config) => setSaveModalConfig(config)}
                                    onAIAnalyze={(sid) => setAiModalSessionId(sid)}
                                />
                            )}

                            {activeTab === 'trades' && (
                                <TradesTable
                                    trades={allTradesJoined}
                                    total={tradesTotal + openPositions.length}
                                    limit={LIMIT}
                                    offset={trades.length}
                                    onLoadMore={handleLoadMoreTrades}
                                    loadingMore={loadingMore}
                                />
                            )}

                            {activeTab === 'strategies' && (
                                <SavedStrategiesSection
                                    strategies={strategies}
                                    onDelete={handleDeleteStrategy}
                                    onUse={handleUseStrategy}
                                />
                            )}

                            {activeTab === 'ai' && (
                                <AIAnalysesTab sessions={allSessions} onOpenAnalysis={(sid) => setAiModalSessionId(sid)} />
                            )}
                        </>
                    )}
                </div>
            </div>

            {aiModalSessionId && (
                <AIAnalysisModal
                    sessionId={aiModalSessionId}
                    onClose={() => setAiModalSessionId(null)}
                    onApplied={() => loadAll()}
                />
            )}

            {saveModalConfig && (
                <SaveStrategyModal
                    config={saveModalConfig}
                    onSave={handleSaveStrategy}
                    onClose={() => setSaveModalConfig(null)}
                />
            )}
        </div>
    );
}


// ─── Modal de Análise IA ────────────────────────────────────────────────────────────

function AIAnalysisModal({ sessionId, onClose, onApplied }) {
    const [loading, setLoading] = useState(true);
    const [applying, setApplying] = useState(false);
    const [error, setError] = useState('');
    const [analysis, setAnalysis] = useState('');
    const [suggestedConfig, setSuggestedConfig] = useState({});
    const [currentConfig, setCurrentConfig] = useState({});
    const [analysisId, setAnalysisId] = useState(null);
    const [applied, setApplied] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            setLoading(true);
            setError('');
            try {
                const res = await requestBotAIAnalysis(sessionId);
                if (cancelled) return;
                setAnalysis(res.analysis || '');
                setSuggestedConfig(res.suggestedConfig || {});
                setCurrentConfig(res.currentConfig || {});
                setAnalysisId(res.id);
            } catch (e) {
                if (!cancelled) setError(e.message || 'Erro ao gerar análise IA');
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        run();
        return () => { cancelled = true; };
    }, [sessionId]);

    const handleApply = async () => {
        if (!suggestedConfig || Object.keys(suggestedConfig).length === 0) return;
        setApplying(true);
        try {
            await applyBotAISuggestions(sessionId, suggestedConfig, analysisId);
            setApplied(true);
            onApplied?.();
        } catch (e) {
            setError(e.message || 'Erro ao aplicar sugestões');
        } finally {
            setApplying(false);
        }
    };

    const configLabels = {
        entrySeconds: 'Entry Seconds',
        exitSeconds: 'Exit Seconds',
        stopLossPct: 'Stop Loss %',
        minProfitPct: 'Min Profit %',
        trailingStartProfitPct: 'Ativar Trailing após (%)',
        autoMaxSymbols: 'Máx Símbolos',
        leverage: 'Alavancagem',
        makerTimeoutSeconds: 'Maker Timeout (s)',
    };

    const hasSuggestions = suggestedConfig && Object.keys(suggestedConfig).length > 0;

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" style={{ maxWidth: '680px', width: '95%', maxHeight: '85vh', display: 'flex', flexDirection: 'column' }} onClick={e => e.stopPropagation()}>
                <div className="modal-header" style={{ background: 'linear-gradient(135deg, rgba(139,92,246,0.15), rgba(59,130,246,0.1))', borderBottom: '1px solid rgba(139,92,246,0.2)' }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <img src={aiIcon} alt="IA" style={{ width: '22px', height: '22px' }} />
                        Análise IA — Bot #{sessionId}
                    </h3>
                    <button className="modal-close" onClick={onClose} aria-label="Fechar">
                        <FaXmark />
                    </button>
                </div>

                <div className="modal-body" style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
                    {loading && (
                        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
                            <div style={{ marginBottom: '16px' }}>
                                <img src={aiIcon} alt="IA" style={{ width: '48px', height: '48px', animation: 'pulse 1.5s infinite' }} />
                            </div>
                            <div style={{ fontSize: '15px', color: 'var(--text-primary)', marginBottom: '8px' }}>
                                Analisando desempenho do bot...
                            </div>
                            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                A IA está avaliando seus trades e configurações
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="paper-error" style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <FaTriangleExclamation />
                            {error}
                        </div>
                    )}

                    {!loading && analysis && (
                        <>
                            <div style={{
                                background: 'rgba(139,92,246,0.05)',
                                border: '1px solid rgba(139,92,246,0.15)',
                                borderRadius: 'var(--radius-md)',
                                padding: '16px 20px',
                                marginBottom: '20px',
                                fontSize: '13px',
                                lineHeight: '1.7',
                                color: 'var(--text-primary)',
                                whiteSpace: 'pre-wrap',
                            }}>
                                {analysis}
                            </div>

                            {hasSuggestions && (
                                <>
                                    <h4 style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                            <FaWandMagicSparkles />
                                            Sugestões de Configuração
                                        </span>
                                    </h4>
                                    <div style={{ overflowX: 'auto' }}>
                                        <table className="data-table" style={{ fontSize: '12px' }}>
                                            <thead>
                                                <tr>
                                                    <th>Parâmetro</th>
                                                    <th>Atual</th>
                                                    <th>→</th>
                                                    <th>Sugestão IA</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {Object.entries(suggestedConfig).map(([key, value]) => (
                                                    <tr key={key}>
                                                        <td className="bold">{configLabels[key] || key}</td>
                                                        <td className="monospace muted">
                                                            {currentConfig[key] != null ? String(currentConfig[key]) : '—'}
                                                        </td>
                                                        <td style={{ textAlign: 'center', color: 'var(--accent-color)' }}>→</td>
                                                        <td className="monospace bold" style={{ color: '#a78bfa' }}>
                                                            {String(value)}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </>
                            )}

                            {!hasSuggestions && (
                                <div style={{
                                    textAlign: 'center', padding: '20px',
                                    color: 'var(--accent-green)', fontSize: '13px',
                                    background: 'rgba(16,185,129,0.05)',
                                    borderRadius: 'var(--radius-md)',
                                    border: '1px solid rgba(16,185,129,0.15)',
                                }}>
                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                        <FaCircleCheck />
                                        A IA não sugere alterações — a configuração atual está boa!
                                    </span>
                                </div>
                            )}
                        </>
                    )}
                </div>

                {!loading && hasSuggestions && (
                    <div className="modal-footer" style={{ padding: '16px 24px', borderTop: '1px solid var(--border-color)', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                        {applied ? (
                            <div style={{ color: 'var(--accent-green)', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <FaCircleCheck />
                                Sugestões aplicadas com sucesso!
                            </div>
                        ) : (
                            <>
                                <button className="session-cancel-btn" onClick={onClose}>Fechar</button>
                                <button
                                    className="session-save-btn"
                                    style={{ background: 'linear-gradient(135deg, #8b5cf6, #6366f1)', border: 'none' }}
                                    onClick={handleApply}
                                    disabled={applying}
                                >
                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                        <FaWandMagicSparkles />
                                        {applying ? 'Aplicando...' : 'Aplicar Sugestões'}
                                    </span>
                                </button>
                            </>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Aba de Análises IA (dentro do RealLogsModal) ───────────────────────────────

function AIAnalysesTab({ sessions, onOpenAnalysis }) {
    const [analyses, setAnalyses] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            setLoading(true);
            setError('');
            try {
                // Busca análises de todos os bots
                const { fetchBotAIAnalyses } = await import('../services/api');
                const allAnalyses = [];
                for (const s of sessions) {
                    const sid = s.id || s.sessionId;
                    try {
                        const res = await fetchBotAIAnalyses(sid, 20);
                        for (const a of (res.data || [])) {
                            allAnalyses.push({
                                ...a,
                                sessionId: sid,
                                sessionName: s.session_name || s.sessionName || `Bot #${sid}`,
                            });
                        }
                    } catch (_) { /* ignora bots sem análises */ }
                }
                allAnalyses.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                if (!cancelled) setAnalyses(allAnalyses);
            } catch (e) {
                if (!cancelled) setError(e.message || 'Erro ao carregar análises');
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        load();
        return () => { cancelled = true; };
    }, [sessions.length]);

    const fmtDate = (iso) => {
        if (!iso) return '—';
        return new Date(iso).toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', year: '2-digit',
            hour: '2-digit', minute: '2-digit',
        });
    };

    if (loading) return <div className="sessions-loading" style={{ padding: '40px 24px' }}>Carregando análises IA...</div>;
    if (error) {
        return (
            <div className="paper-error" style={{ margin: '16px 24px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <FaTriangleExclamation />
                {error}
            </div>
        );
    }

    return (
        <div style={{ padding: '0 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h4 style={{ margin: 0, fontSize: '14px', color: 'var(--text-secondary)' }}>
                    <img src={aiIcon} alt="IA" style={{ width: '18px', height: '18px', verticalAlign: 'middle', marginRight: '6px' }} />
                    Histórico de Análises IA ({analyses.length})
                </h4>
            </div>

            {analyses.length === 0 ? (
                <div style={{
                    textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)',
                    background: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-color)',
                }}>
                    <img src={aiIcon} alt="IA" style={{ width: '32px', height: '32px', opacity: 0.4, marginBottom: '12px' }} />
                    <div>Nenhuma análise IA realizada ainda.</div>
                    <div style={{ fontSize: '12px', marginTop: '4px' }}>Clique no ícone IA na tabela de bots para gerar uma análise.</div>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {analyses.map((a, idx) => (
                        <div key={a.id || idx} style={{
                            background: 'var(--card-bg)',
                            border: '1px solid var(--border-color)',
                            borderRadius: 'var(--radius-md)',
                            padding: '14px 18px',
                            cursor: 'pointer',
                        }}
                            onClick={() => onOpenAnalysis?.(a.sessionId)}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <img src={aiIcon} alt="IA" style={{ width: '14px', height: '14px' }} />
                                    <span style={{ fontWeight: 600, fontSize: '13px' }}>{a.sessionName}</span>
                                    <span className={`session-card-badge ${a.trigger_type === 'auto' ? 'badge-done' : 'badge-active'}`} style={{ fontSize: '10px' }}>
                                        {a.trigger_type === 'auto' ? 'AUTOMÁTICA' : 'MANUAL'}
                                    </span>
                                    {a.applied && (
                                        <span style={{ fontSize: '10px', color: 'var(--accent-green)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                            <FaCircleCheck />
                                            Aplicada
                                        </span>
                                    )}
                                </div>
                                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{fmtDate(a.created_at)}</span>
                            </div>
                            <div style={{
                                fontSize: '12px', lineHeight: '1.6', color: 'var(--text-secondary)',
                                whiteSpace: 'pre-wrap',
                                maxHeight: '80px', overflow: 'hidden',
                                maskImage: 'linear-gradient(to bottom, black 60%, transparent)',
                                WebkitMaskImage: 'linear-gradient(to bottom, black 60%, transparent)',
                            }}>
                                {a.analysis_text || 'Análise sem texto.'}
                            </div>
                            {a.suggested_config && Object.keys(a.suggested_config).length > 0 && (
                                <div style={{ marginTop: '8px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                                    {Object.entries(a.suggested_config).map(([k, v]) => (
                                        <span key={k} style={{
                                            fontSize: '10px', padding: '2px 8px',
                                            background: 'rgba(139,92,246,0.1)',
                                            border: '1px solid rgba(139,92,246,0.2)',
                                            borderRadius: '4px', color: '#a78bfa',
                                        }}>
                                            {k}: {String(v)}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
