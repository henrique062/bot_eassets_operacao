import { useState, useEffect, useCallback, Fragment, useMemo } from 'react';
import { deriveEntryMargin } from '../utils/trading';
import ConfirmModal from './ConfirmModal';
import {
    fetchRealSessions,
    fetchRealLogs,
    fetchStrategies,
    saveStrategy,
    deleteStrategy,
    requestBotAIAnalysis,
    applyBotAISuggestions,
    fetchBotAIAnalyses,
    fetchRealOrderLogs,
    fetchServerLogs,
} from '../services/api';
import aiIcon from '../assets/tecnologia-de-ia.png';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import {
    FaBrain,
    FaChartColumn,
    FaCircleCheck,
    FaCirclePlay,
    FaClipboard,
    FaClipboardList,
    FaFloppyDisk,
    FaMagnifyingGlass,
    FaMapPin,
    FaRobot,
    FaServer,
    FaTrashCan,
    FaTriangleExclamation,
    FaWandMagicSparkles,
    FaXmark,
} from 'react-icons/fa6';

// ─── Helpers ────────────────────────────────────────────────────────────────

const TRANSLATED_REASONS = {
    'timeout': 'Tempo Excedido',
    'stop_loss': 'Stop Loss',
    'stop_loss_pct': 'Stop Loss',
    'take_profit': 'Take Profit',
    'take_profit_pct': 'Take Profit',
    'min_profit': 'Lucro Mínimo',
    'min_profit_pct': 'Lucro Mínimo',
    'exchange_sync': 'Sinc. Exchange',
    'funding': 'Funding',
    'manual': 'Manual',
};

const TRANSLATED_MODE_VALUES = {
    'manual': 'Manual',
    'manual_position': 'Operação Manual',
    'test': 'Operação Manual',
    'auto_expiring': 'Auto Expirando',
    'auto_strongest': 'Auto Melhor Score',
    'auto_highest_rate': 'Auto Maior Taxa',
    'post_funding_follow': 'Pos Funding (Favor)',
    'counter_trend': 'Contra Tendência'
};

function translateReason(reason) {
    if (!reason) return '—';
    return TRANSLATED_REASONS[reason] || reason;
}

function translateOperationMode(mode) {
    return TRANSLATED_MODE_VALUES[mode] || mode || 'Manual';
}

const PRESET_DISPLAY = {
    ct_precisa:       { name: 'CT Precisa',      color: '#22c55e' },
    ct_balanceada:    { name: 'CT Balanceada',    color: '#3b82f6' },
    coleta_segura:    { name: 'Coleta Segura',    color: '#8b5cf6' },
    coleta_expirando: { name: 'Coleta Expirando', color: '#f59e0b' },
};

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




function fmtMarginUsd(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return '—';
    return `$${n.toFixed(n >= 100 ? 2 : 4)}`;
}


function buildStrategyConfig(session) {
    const cfg = session.config || session;
    const operationMode = cfg.operation_mode || cfg.operationMode || 'manual';
    const strategy = {
        operationMode: cfg.operation_mode || cfg.operationMode || 'manual',
        autoDirection: cfg.auto_direction || cfg.autoDirection || 'both',
        autoMaxSymbols: cfg.auto_max_symbols ?? cfg.autoMaxSymbols ?? 8,
        autoMinScore: cfg.auto_min_score ?? cfg.autoMinScore ?? 50,
        autoWindowMinutes: cfg.auto_window_minutes ?? cfg.autoWindowMinutes ?? 60,
        symbols: cfg.symbols || [],
        capital: parseFloat(cfg.capital) || 1000,
        leverage: cfg.leverage || 1,
        feeType: cfg.fee_type || cfg.feeType || 'maker',
        entrySeconds: cfg.entry_seconds ?? cfg.entrySeconds ?? 30,
        stopLossPct: cfg.stop_loss_pct ?? cfg.stopLossPct ?? null,
        stopLossUsd: cfg.stop_loss_usd ?? cfg.stopLossUsd ?? null,
        minProfitPct: cfg.min_profit_pct ?? cfg.minProfitPct ?? null,
        trailingStopPct: cfg.trailing_stop_pct ?? cfg.trailingStopPct ?? null,
        trailingStartProfitPct: cfg.trailing_start_profit_pct ?? cfg.trailingStartProfitPct ?? null,
        exchange: cfg.exchange || 'binance',
    };
    // Motivo: não persistir exitSeconds ao copiar estratégia de modo sem timeout.
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
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" style={{ maxWidth: '420px', width: '90%' }} onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h3 className="icon-inline">
                        <FaFloppyDisk aria-hidden="true" />
                        Salvar Estratégia
                    </h3>
                    <button className="modal-close" onClick={onClose}>
                        <FaXmark aria-hidden="true" />
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
                        Modo: <strong>{translateOperationMode(config?.operationMode)}</strong> ·
                        Capital: <strong>${parseFloat(config?.capital || 0).toFixed(0)}</strong> ·
                        Alavancagem: <strong>{config?.leverage || 1}x</strong>
                    </div>
                    {error && (
                        <div className="paper-error icon-inline" style={{ marginTop: '12px' }}>
                            <FaTriangleExclamation aria-hidden="true" />
                            {error}
                        </div>
                    )}
                </div>
                <div className="modal-footer" style={{ padding: '0 24px 20px', display: 'flex', gap: '8px' }}>
                    <button className="session-save-btn" onClick={handleSave} disabled={saving}>
                        {saving ? 'Salvando...' : (
                            <span className="icon-inline">
                                <FaFloppyDisk aria-hidden="true" />
                                Salvar
                            </span>
                        )}
                    </button>
                    <button className="session-cancel-btn" onClick={onClose}>Cancelar</button>
                </div>
            </div>
        </div>
    );
}

// ─── Seção de Estratégias Salvas ─────────────────────────────────────────────

function SavedStrategiesSection({ strategies, onDelete, onUse }) {
    if (!strategies.length) return null;

    return (
        <div className="section-block" style={{ marginBottom: '24px' }}>
            <div className="section-header">
                <h2 className="icon-inline">
                    <FaMapPin aria-hidden="true" />
                    Estratégias Salvas ({strategies.length})
                </h2>
            </div>
            <div className="sessions-grid" style={{ marginTop: '12px' }}>
                {strategies.map(s => (
                    <div key={s.id} className="session-card" style={{ cursor: 'default' }}>
                        <div className="session-card-header">
                            <span className="session-name">{s.name}</span>
                            <span className="session-card-badge" style={{ background: 'rgba(99,102,241,0.15)', color: '#818cf8' }}>
                                {(s.config?.exchange || 'binance').toUpperCase()}
                            </span>
                        </div>
                        <div className="session-card-stats" style={{ marginTop: '8px' }}>
                            <span className="session-stat">{translateOperationMode(s.config?.operationMode)}</span>
                            <span className="session-stat">${parseFloat(s.config?.capital || 0).toFixed(0)}</span>
                            <span className="session-stat">{s.config?.leverage || 1}x</span>
                            <span className="session-stat">{s.config?.feeType || 'maker'}</span>
                            {s.config?.stopLossPct != null && (
                                <span className="session-stat stop-loss-badge">SL {s.config.stopLossPct}%</span>
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
                                <span className="icon-inline">
                                    <FaCirclePlay aria-hidden="true" />
                                    Usar Estratégia
                                </span>
                            </button>
                            <button className="session-delete-btn" onClick={() => onDelete(s.id, s.name)}>
                                <span className="icon-inline">
                                    <FaTrashCan aria-hidden="true" />
                                    Remover
                                </span>
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ─── Tabela de Bots ──────────────────────────────────────────────────────────

function BotsTable({ sessions, onCopyStrategy, onSaveStrategy, onAIAnalyze }) {
    const [expanded, setExpanded] = useState(null);
    const [sortConfig, setSortConfig] = useState(null);
    const [filterPreset, setFilterPreset] = useState('');

    const sortedSessions = useMemo(() => {
        let sortableItems = [...sessions].filter(s => {
            if (!filterPreset) return true;
            if (filterPreset === '__none__') return !s.preset_name;
            return s.preset_name === filterPreset;
        });
        if (sortConfig !== null) {
            sortableItems.sort((a, b) => {
                let aValue = 0, bValue = 0;
                switch (sortConfig.key) {
                    case 'id': aValue = parseInt(a.id || a.sessionId) || 0; bValue = parseInt(b.id || b.sessionId) || 0; break;
                    case 'name': aValue = (a.session_name || a.sessionName || '').toLowerCase(); bValue = (b.session_name || b.sessionName || '').toLowerCase(); break;
                    case 'exchange': aValue = (a.exchange || '').toLowerCase(); bValue = (b.exchange || '').toLowerCase(); break;
                    case 'mode': {
                        const aCfg = a.config || a; const bCfg = b.config || b;
                        aValue = translateOperationMode(aCfg.operation_mode || aCfg.operationMode || 'manual');
                        bValue = translateOperationMode(bCfg.operation_mode || bCfg.operationMode || 'manual');
                        break;
                    }
                    case 'capital': aValue = parseFloat(a.capital) || 0; bValue = parseFloat(b.capital) || 0; break;
                    case 'balance': aValue = parseFloat(a.balance) || 0; bValue = parseFloat(b.balance) || 0; break;
                    case 'pnl': {
                        const aCap = parseFloat(a.capital) || 0; const aBal = parseFloat(a.balance) || 0;
                        const bCap = parseFloat(b.capital) || 0; const bBal = parseFloat(b.balance) || 0;
                        aValue = aBal - aCap; bValue = bBal - bCap; break;
                    }
                    case 'trades': aValue = parseInt(a.total_trades || a.totalTrades) || 0; bValue = parseInt(b.total_trades || b.totalTrades) || 0; break;
                    case 'status': aValue = a.active ? 1 : 0; bValue = b.active ? 1 : 0; break;
                    case 'start': aValue = new Date(a.started_at || 0).getTime(); bValue = new Date(b.started_at || 0).getTime(); break;
                    case 'end': aValue = new Date(a.ended_at || 0).getTime(); bValue = new Date(b.ended_at || 0).getTime(); break;
                    default: return 0;
                }
                if (aValue < bValue) return sortConfig.direction === 'ascending' ? -1 : 1;
                if (aValue > bValue) return sortConfig.direction === 'ascending' ? 1 : -1;
                return 0;
            });
        }
        return sortableItems;
    }, [sessions, sortConfig]);

    const requestSort = (key) => {
        let direction = 'ascending';
        if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascending') {
            direction = 'descending';
        }
        setSortConfig({ key, direction });
    };

    return (
        <div className="section-block" style={{ marginBottom: '24px' }}>
            <div className="section-header">
                <h2 className="icon-inline">
                    <FaRobot aria-hidden="true" />
                    Histórico de Bots ({sessions.length})
                </h2>
            </div>
            {sessions.length === 0 ? (
                <div className="sessions-empty" style={{ marginTop: '12px' }}>Nenhum bot criado ainda.</div>
            ) : (
                <div style={{ overflowX: 'auto', marginTop: '12px' }}>
                    <div style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <FaWandMagicSparkles style={{ color: 'var(--text-secondary)', fontSize: '12px' }} />
                        <select
                            value={filterPreset}
                            onChange={e => setFilterPreset(e.target.value)}
                            style={{ fontSize: '13px', padding: '4px 8px', background: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: '6px' }}
                        >
                            <option value="">Todas as estratégias</option>
                            <option value="ct_precisa">CT Precisa</option>
                            <option value="ct_balanceada">CT Balanceada</option>
                            <option value="coleta_segura">Coleta Segura</option>
                            <option value="coleta_expirando">Coleta Expirando</option>
                            <option value="__none__">Sem preset</option>
                        </select>
                    </div>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th onClick={() => requestSort('id')} style={{cursor:'pointer'}}>#{sortConfig?.key === 'id' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('name')} style={{cursor:'pointer'}}>Nome{sortConfig?.key === 'name' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('exchange')} style={{cursor:'pointer'}}>Exchange{sortConfig?.key === 'exchange' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('mode')} style={{cursor:'pointer'}}>Modo{sortConfig?.key === 'mode' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('capital')} style={{cursor:'pointer'}}>Capital{sortConfig?.key === 'capital' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('balance')} style={{cursor:'pointer'}}>Saldo Final{sortConfig?.key === 'balance' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('pnl')} style={{cursor:'pointer'}} className="right">P&L{sortConfig?.key === 'pnl' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('trades')} style={{cursor:'pointer'}}>Trades{sortConfig?.key === 'trades' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('status')} style={{cursor:'pointer'}}>Status{sortConfig?.key === 'status' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('start')} style={{cursor:'pointer'}}>Início{sortConfig?.key === 'start' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th onClick={() => requestSort('end')} style={{cursor:'pointer'}}>Fim{sortConfig?.key === 'end' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                <th>Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sortedSessions.map(s => {
                                const capital = parseFloat(s.capital) || 0;
                                const balance = parseFloat(s.balance) || 0;
                                const pnl = balance - capital;
                                const pnlPct = capital > 0 ? (pnl / capital) * 100 : 0;
                                const cfg = s.config || s;
                                const mode = translateOperationMode(cfg.operation_mode || cfg.operationMode || 'manual');
                                const isExp = expanded === (s.id || s.sessionId);

                                return [
                                    <tr
                                        key={s.id || s.sessionId}
                                        className="trade-row-clickable"
                                        onClick={() => setExpanded(prev => prev === (s.id || s.sessionId) ? null : (s.id || s.sessionId))}
                                    >
                                        <td className="monospace muted">{s.id || s.sessionId}</td>
                                        <td className="bold">
                                            {s.session_name || s.sessionName || `Bot #${s.id || s.sessionId}`}
                                            {s.preset_name && PRESET_DISPLAY[s.preset_name] && (
                                                <span style={{ marginLeft: '6px', fontSize: '10px', fontWeight: 600, padding: '1px 6px', borderRadius: '4px', background: PRESET_DISPLAY[s.preset_name].color + '22', color: PRESET_DISPLAY[s.preset_name].color, border: `1px solid ${PRESET_DISPLAY[s.preset_name].color}55` }}>
                                                    {PRESET_DISPLAY[s.preset_name].name}
                                                </span>
                                            )}
                                        </td>
                                        <td>{(s.exchange || 'binance').toUpperCase()}</td>
                                        <td>
                                            <span className="session-stat" style={{ fontSize: '11px' }}>{mode}</span>
                                        </td>
                                        <td className="monospace">${capital.toFixed(2)}</td>
                                        <td className="monospace">${balance.toFixed(2)}</td>
                                        <td className={`right monospace bold ${pnl >= 0 ? 'positive' : 'negative'}`}>
                                            {fmtPnl(pnl)} ({fmtPct(pnlPct)})
                                        </td>
                                        <td className="monospace">{s.total_trades || s.totalTrades || 0}</td>
                                        <td>
                                            {s.active
                                                ? (
                                                    <span className="status-badge status-badge--active">
                                                        <FaCirclePlay className="status-badge__icon" />
                                                        ATIVO
                                                    </span>
                                                )
                                                : (
                                                    <span className="status-badge status-badge--done">
                                                        <FaCircleCheck className="status-badge__icon" />
                                                        FINALIZADO
                                                    </span>
                                                )
                                            }
                                        </td>
                                        <td className="monospace muted" style={{ fontSize: '11px' }}>{fmtDate(s.started_at)}</td>
                                        <td className="monospace muted" style={{ fontSize: '11px' }}>{fmtDate(s.ended_at)}</td>
                                        <td>
                                            <div style={{ display: 'flex', gap: '4px' }} onClick={e => e.stopPropagation()}>
                                                <button
                                                    title="Análise IA"
                                                    className="session-edit-btn"
                                                    style={{ padding: '3px 8px', background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.3)' }}
                                                    onClick={() => onAIAnalyze?.(s.id || s.sessionId)}
                                                >
                                                    <img src={aiIcon} alt="IA" style={{ width: '14px', height: '14px', verticalAlign: 'middle' }} />
                                                </button>
                                                <button
                                                    title="Copiar estratégia para novo bot"
                                                    className="session-edit-btn"
                                                    style={{ padding: '3px 8px', fontSize: '11px' }}
                                                    onClick={() => onCopyStrategy(buildStrategyConfig(s))}
                                                >
                                                    <span className="icon-inline">
                                                        <FaClipboard aria-hidden="true" />
                                                        Copiar
                                                    </span>
                                                </button>
                                                <button
                                                    title="Salvar estratégia com nome"
                                                    className="session-edit-btn"
                                                    style={{ padding: '3px 8px', fontSize: '11px', background: 'rgba(16,185,129,0.1)', color: '#34d399', border: '1px solid rgba(16,185,129,0.25)' }}
                                                    onClick={() => onSaveStrategy(buildStrategyConfig(s))}
                                                >
                                                    <span className="icon-inline">
                                                        <FaFloppyDisk aria-hidden="true" />
                                                        Salvar
                                                    </span>
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
                                                    {s.trailing_stop_pct != null && (
                                                        <span>
                                                            TSL: <strong>{s.trailing_stop_pct}%</strong>{s.trailing_start_profit_pct != null ? ` @ +${s.trailing_start_profit_pct}%` : ''}
                                                        </span>
                                                    )}
                                                    {s.min_profit_pct != null && <span>Min Profit: <strong>{s.min_profit_pct}%</strong></span>}
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
            )}
        </div>
    );
}

// ─── Tabela de Logs de Operações ─────────────────────────────────────────────

function TradesTable({ trades, total, limit, offset, onLoadMore, loadingMore }) {
    const [sortConfig, setSortConfig] = useState(null);

    const sortedTrades = useMemo(() => {
        let sortableItems = [...trades];
        if (sortConfig !== null) {
            sortableItems.sort((a, b) => {
                let aValue = 0, bValue = 0;
                switch (sortConfig.key) {
                    case 'id': aValue = parseInt(a.id) || 0; bValue = parseInt(b.id) || 0; break;
                    case 'bot': aValue = (a.sessionName || '').toLowerCase(); bValue = (b.sessionName || '').toLowerCase(); break;
                    case 'exchange': aValue = (a.exchange || '').toLowerCase(); bValue = (b.exchange || '').toLowerCase(); break;
                    case 'symbol': aValue = (a.symbol || '').toLowerCase(); bValue = (b.symbol || '').toLowerCase(); break;
                    case 'direction': aValue = (a.direction || '').toLowerCase(); bValue = (b.direction || '').toLowerCase(); break;
                    case 'entry': aValue = new Date(a.openTime || 0).getTime(); bValue = new Date(b.openTime || 0).getTime(); break;
                    case 'exit': aValue = new Date(a.closeTime || 0).getTime(); bValue = new Date(b.closeTime || 0).getTime(); break;
                    case 'margin': {
                        aValue = Number(
                            deriveEntryMargin({
                                entryMargin: a.entryMargin ?? a.entry_margin,
                                totalPnl: a.totalPnl,
                                totalPnlPct: a.totalPnlPct,
                                pricePnl: a.pricePnl,
                                pricePnlPct: a.pricePnlPct,
                                leverage: a.leverage,
                            })
                        ) || 0;
                        bValue = Number(
                            deriveEntryMargin({
                                entryMargin: b.entryMargin ?? b.entry_margin,
                                totalPnl: b.totalPnl,
                                totalPnlPct: b.totalPnlPct,
                                pricePnl: b.pricePnl,
                                pricePnlPct: b.pricePnlPct,
                                leverage: b.leverage,
                            })
                        ) || 0;
                        break;
                    }
                    case 'p_entry': aValue = Number(a.entryPrice) || 0; bValue = Number(b.entryPrice) || 0; break;
                    case 'p_exit': aValue = Number(a.exitPrice) || 0; bValue = Number(b.exitPrice) || 0; break;
                    case 'funding_rate': aValue = Number(a.fundingRate) || 0; bValue = Number(b.fundingRate) || 0; break;
                    case 'funding': aValue = Number(a.fundingPnl) || 0; bValue = Number(b.fundingPnl) || 0; break;
                    case 'fee': aValue = Number(a.feeCost) || 0; bValue = Number(b.feeCost) || 0; break;
                    case 'pnl': aValue = Number(a.totalPnl) || 0; bValue = Number(b.totalPnl) || 0; break;
                    case 'pnl_pct': aValue = Number(a.totalPnlPct) || 0; bValue = Number(b.totalPnlPct) || 0; break;
                    case 'reason': aValue = (translateReason(a.closeReason) || '').toLowerCase(); bValue = (translateReason(b.closeReason) || '').toLowerCase(); break;
                    default: return 0;
                }
                if (aValue < bValue) return sortConfig.direction === 'ascending' ? -1 : 1;
                if (aValue > bValue) return sortConfig.direction === 'ascending' ? 1 : -1;
                return 0;
            });
        }
        return sortableItems;
    }, [trades, sortConfig]);

    const requestSort = (key) => {
        let direction = 'ascending';
        if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascending') {
            direction = 'descending';
        }
        setSortConfig({ key, direction });
    };

    return (
        <div className="section-block">
            <div className="section-header">
                <h2 className="icon-inline">
                    <FaClipboardList aria-hidden="true" />
                    Histórico de Operações ({total ?? trades.length})
                </h2>
            </div>
            {trades.length === 0 ? (
                <div className="sessions-empty" style={{ marginTop: '12px' }}>Nenhuma operação registrada ainda.</div>
            ) : (
                <>
                    <div style={{ overflowX: 'auto', marginTop: '12px' }}>
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th onClick={() => requestSort('id')} style={{cursor:'pointer'}}>#{sortConfig?.key === 'id' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('bot')} style={{cursor:'pointer'}}>Bot{sortConfig?.key === 'bot' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('exchange')} style={{cursor:'pointer'}}>Exchange{sortConfig?.key === 'exchange' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('symbol')} style={{cursor:'pointer'}}>Símbolo{sortConfig?.key === 'symbol' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('direction')} style={{cursor:'pointer'}}>Direção{sortConfig?.key === 'direction' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('entry')} style={{cursor:'pointer'}}>Entrada{sortConfig?.key === 'entry' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('exit')} style={{cursor:'pointer'}}>Saída{sortConfig?.key === 'exit' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('margin')} style={{cursor:'pointer'}} className="right">Margem{sortConfig?.key === 'margin' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('p_entry')} style={{cursor:'pointer'}} className="right">P/Entrada{sortConfig?.key === 'p_entry' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('p_exit')} style={{cursor:'pointer'}} className="right">P/Saída{sortConfig?.key === 'p_exit' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('funding_rate')} style={{cursor:'pointer'}} className="right">Taxa FR{sortConfig?.key === 'funding_rate' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('funding')} style={{cursor:'pointer'}} className="right">Funding{sortConfig?.key === 'funding' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('fee')} style={{cursor:'pointer'}} className="right">Fee{sortConfig?.key === 'fee' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('pnl')} style={{cursor:'pointer'}} className="right">PNL{sortConfig?.key === 'pnl' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('pnl_pct')} style={{cursor:'pointer'}} className="right">PNL % (Cap/Mrg){sortConfig?.key === 'pnl_pct' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                    <th onClick={() => requestSort('reason')} style={{cursor:'pointer'}}>Motivo{sortConfig?.key === 'reason' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedTrades.map(t => {
                                    const pnl = Number(t.totalPnl);
                                    const pnlPctMargin = Number(t.totalPnlPct);
                                    const entryMargin = deriveEntryMargin({
                                        entryMargin: t.entryMargin ?? t.entry_margin,
                                        totalPnl: t.totalPnl,
                                        totalPnlPct: t.totalPnlPct,
                                        pricePnl: t.pricePnl,
                                        pricePnlPct: t.pricePnlPct,
                                        leverage: t.leverage,
                                    });
                                    const capital = Number(t.capital);
                                    const pnlPctCapital = capital > 0 && Number.isFinite(pnl)
                                        ? (pnl / capital) * 100
                                        : NaN;
                                    const pctSignal = Number.isFinite(pnlPctCapital) ? pnlPctCapital : pnlPctMargin;
                                    return (
                                        <tr key={t.id} className="trade-row-clickable">
                                            <td className="monospace muted" style={{ fontSize: '11px' }}>{t.id}</td>
                                            <td style={{ fontSize: '11px', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {t.sessionName}
                                            </td>
                                            <td style={{ fontSize: '11px' }}>{(t.exchange || '—').toUpperCase()}</td>
                                            <td className="bold">{(t.symbol || '').replace('USDT', '')}</td>
                                            <td>
                                                <span className={`badge ${t.direction === 'SHORT' ? 'badge-short' : 'badge-long'}`}>
                                                    {t.direction}
                                                </span>
                                            </td>
                                            <td className="monospace muted" style={{ fontSize: '11px' }}>{t.openTime || '—'}</td>
                                            <td className="monospace muted" style={{ fontSize: '11px' }}>{t.closeTime || '—'}</td>
                                            <td className="right monospace" style={{ fontSize: '11px' }}>{fmtMarginUsd(entryMargin)}</td>
                                            <td className="right monospace" style={{ fontSize: '11px' }}>${Number(t.entryPrice).toFixed(4)}</td>
                                            <td className="right monospace" style={{ fontSize: '11px' }}>${Number(t.exitPrice).toFixed(4)}</td>
                                            <td className="right monospace muted" style={{ fontSize: '11px' }}>
                                                {Number(t.fundingRate) !== 0
                                                    ? `${Number(t.fundingRate).toFixed(4)}%`
                                                    : '—'}
                                            </td>
                                            <td className={`right monospace ${Number(t.fundingPnl) >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '11px' }}>
                                                ${Number(t.fundingPnl).toFixed(4)}
                                            </td>
                                            <td className="right monospace muted" style={{ fontSize: '11px' }}>
                                                ${Number(t.feeCost).toFixed(4)}
                                            </td>
                                            <td className={`right monospace bold ${pnl >= 0 ? 'positive' : 'negative'}`}>
                                                {Number.isFinite(pnl) ? fmtPnl(pnl) : '—'}
                                            </td>
                                            <td className={`right monospace bold ${Number.isFinite(pctSignal) ? (pctSignal >= 0 ? 'positive' : 'negative') : 'muted'}`}>
                                                {/* Motivo: usuário pediu inversão visual para mostrar Cap na primeira linha e Mrg na segunda. */}
                                                <div>
                                                    {Number.isFinite(pnlPctCapital) ? `Cap ${fmtPct(pnlPctCapital)}` : 'Cap —'}
                                                </div>
                                                <div className="muted" style={{ fontSize: '10px', fontWeight: 600, marginTop: '2px' }}>
                                                    {Number.isFinite(pnlPctMargin) ? `Mrg ${fmtPct(pnlPctMargin)}` : 'Mrg —'}
                                                </div>
                                            </td>
                                            <td style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                                {translateReason(t.closeReason)}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                    {trades.length < (total ?? 0) && (
                        <div style={{ textAlign: 'center', marginTop: '16px' }}>
                            <button className="refresh-btn" onClick={onLoadMore} disabled={loadingMore}>
                                {loadingMore ? 'Carregando...' : `↓ Carregar mais (${(total ?? 0) - trades.length} restantes)`}
                            </button>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

// ─── Componente principal ────────────────────────────────────────────────────

export default function LogsPage({ onCopyStrategy }) {
    const [sessions, setSessions] = useState([]);
    const [trades, setTrades] = useState([]);
    const [tradesTotal, setTradesTotal] = useState(0);
    const [strategies, setStrategies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [error, setError] = useState('');
    const [saveModalConfig, setSaveModalConfig] = useState(null);
    const [activeTab, setActiveTab] = useState('bots'); // 'bots' | 'trades' | 'strategies' | 'ai'
    const [modalConfig, setModalConfig] = useState(null);
    const [aiModalSessionId, setAiModalSessionId] = useState(null);

    const LIMIT = 100;

    const loadAll = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const [sessRes, tradesRes, stratRes] = await Promise.all([
                fetchRealSessions(),
                fetchRealLogs({ limit: LIMIT, offset: 0 }),
                fetchStrategies(),
            ]);
            setSessions(sessRes.data || []);
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
    };

    // P&L Total: usa trades_pnl (soma real dos trades por sessão, vindo do backend)
    // Isso evita distorção quando balance foi inicializado incorretamente
    const totalPnl = sessions.reduce((acc, s) => acc + (parseFloat(s.trades_pnl) || 0), 0);
    // Base para %: apenas capital de sessões que executaram pelo menos 1 trade
    const capitalDeployed = sessions
        .filter(s => (parseInt(s.total_trades) || 0) > 0)
        .reduce((acc, s) => acc + (parseFloat(s.capital) || 0), 0);
    const totalPnlPct = capitalDeployed > 0 ? (totalPnl / capitalDeployed) * 100 : 0;

    const totalTrades = sessions.reduce((acc, s) => acc + (parseInt(s.total_trades) || 0), 0);
    const activeBots = sessions.filter(s => s.active).length;
    // Base de capital ativo (bots atualmente rodando) — usada para % do dia
    const activeCapital = sessions
        .filter(s => s.active)
        .reduce((acc, s) => acc + (parseFloat(s.capital) || 0), 0);
    const now = new Date();
    const todayStartMs = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const todayEndMs = todayStartMs + 24 * 60 * 60 * 1000;
    const todayTrades = trades.filter(t => {
        const ts = Number(t.tradeTimestamp ?? t.trade_timestamp);
        return Number.isFinite(ts) && ts >= todayStartMs && ts < todayEndMs;
    });
    const todayPnl = todayTrades.reduce((acc, t) => acc + (Number(t.totalPnl ?? t.total_pnl) || 0), 0);
    // % do dia em relação ao capital atualmente ativo (bots rodando)
    const todayPnlPct = activeCapital > 0 ? (todayPnl / activeCapital) * 100 : 0;

    return (
        <div className="paper-page">
            {/* Header com resumo */}
            <div className="section-block" style={{ marginBottom: '24px' }}>
                <div className="section-header" style={{ marginBottom: '16px' }}>
                    <h2 className="icon-inline">
                        <FaChartColumn aria-hidden="true" />
                        Painel de Logs & Histórico
                    </h2>
                    <button className="refresh-btn" onClick={loadAll} disabled={loading}>↻ Atualizar</button>
                </div>
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                    <div className="stat-card" style={{ flex: '1', minWidth: '130px' }}>
                        <div className="stat-label">Total de Bots</div>
                        <div className="stat-value">{sessions.length}</div>
                    </div>
                    <div className="stat-card" style={{ flex: '1', minWidth: '130px' }}>
                        <div className="stat-label">Bots Ativos</div>
                        <div className="stat-value positive">{activeBots}</div>
                    </div>
                    <div className="stat-card" style={{ flex: '1', minWidth: '130px' }}>
                        <div className="stat-label">Total de Trades</div>
                        <div className="stat-value">{totalTrades}</div>
                    </div>
                    <div className="stat-card" style={{ flex: '1', minWidth: '130px' }}>
                        <div className="stat-label">P&L Total</div>
                        <div className={`stat-value ${totalPnl >= 0 ? 'positive' : 'negative'}`}>
                            {fmtPnl(totalPnl)}
                        </div>
                    </div>
                    <div className="stat-card" style={{ flex: '1', minWidth: '130px' }}>
                        <div className="stat-label">P&L Total %</div>
                        <div className={`stat-value ${totalPnlPct >= 0 ? 'positive' : 'negative'}`}>
                            {fmtPct(totalPnlPct)}
                        </div>
                    </div>
                    <div className="stat-card" style={{ flex: '1', minWidth: '130px' }}>
                        <div className="stat-label">Lucro do Dia</div>
                        <div className={`stat-value ${todayPnl >= 0 ? 'positive' : 'negative'}`}>
                            {fmtPnl(todayPnl)}
                        </div>
                    </div>
                    <div className="stat-card" style={{ flex: '1', minWidth: '130px' }}>
                        <div className="stat-label">Lucro do Dia %</div>
                        <div className={`stat-value ${todayPnlPct >= 0 ? 'positive' : 'negative'}`}>
                            {fmtPct(todayPnlPct)}
                        </div>
                    </div>
                </div>
            </div>

            {error && <div className="error-message" style={{ marginBottom: '16px' }}>{error}</div>}
            {loading && <div className="sessions-loading">Carregando...</div>}

            {/* Abas */}
            {!loading && (
                <>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', borderBottom: '1px solid var(--border-color)', paddingBottom: '0' }}>
                        {[
                            { key: 'bots', label: `Bots (${sessions.length})`, icon: FaRobot },
                            { key: 'trades', label: `Operações (${tradesTotal})`, icon: FaClipboardList },
                            { key: 'strategies', label: `Estratégias Salvas (${strategies.length})`, icon: FaMapPin },
                            { key: 'ai', label: 'Análises IA', icon: FaBrain },
                            { key: 'order_logs', label: 'Logs de Ordens', icon: FaMagnifyingGlass },
                            { key: 'server_logs', label: 'Logs do Servidor', icon: FaServer },
                        ].map(({ key, label, icon: Icon }) => (
                            <button
                                key={key}
                                onClick={() => setActiveTab(key)}
                                style={{
                                    background: 'none',
                                    border: 'none',
                                    borderBottom: activeTab === key ? '2px solid var(--accent-color)' : '2px solid transparent',
                                    color: activeTab === key ? 'var(--text-primary)' : 'var(--text-muted)',
                                    padding: '8px 16px',
                                    cursor: 'pointer',
                                    fontSize: '13px',
                                    fontWeight: activeTab === key ? '600' : '400',
                                    marginBottom: '-1px',
                                }}
                            >
                                <span className="icon-inline">
                                    <Icon aria-hidden="true" />
                                    {label}
                                </span>
                            </button>
                        ))}
                    </div>

                    {activeTab === 'bots' && (
                        <BotsTable
                            sessions={sessions}
                            onCopyStrategy={handleUseStrategy}
                            onSaveStrategy={(config) => setSaveModalConfig(config)}
                            onAIAnalyze={(sid) => setAiModalSessionId(sid)}
                        />
                    )}

                    {activeTab === 'trades' && (
                        <TradesTable
                            trades={trades}
                            total={tradesTotal}
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
                        <AIAnalysesTab sessions={sessions} onOpenAnalysis={(sid) => setAiModalSessionId(sid)} />
                    )}

                    {activeTab === 'order_logs' && (
                        <OrderLogsTab sessions={sessions} />
                    )}

                    {activeTab === 'server_logs' && (
                        <ServerLogsTab />
                    )}
                </>
            )}

            {saveModalConfig && (
                <SaveStrategyModal
                    config={saveModalConfig}
                    onSave={handleSaveStrategy}
                    onClose={() => setSaveModalConfig(null)}
                />
            )}

            {modalConfig && (
                <ConfirmModal
                    title={modalConfig.title}
                    message={modalConfig.message}
                    isAlert={modalConfig.isAlert}
                    onConfirm={() => {
                        if (modalConfig.onConfirm) modalConfig.onConfirm();
                        else setModalConfig(null);
                    }}
                    onCancel={() => setModalConfig(null)}
                />
            )}

            {aiModalSessionId && (
                <AIAnalysisModal
                    sessionId={typeof aiModalSessionId === 'object' ? aiModalSessionId.sessionId : aiModalSessionId}
                    initialData={typeof aiModalSessionId === 'object' ? aiModalSessionId : null}
                    onClose={() => setAiModalSessionId(null)}
                    onApplied={() => loadAll()}
                />
            )}
        </div>
    );
}


// ─── Modal de Análise IA ─────────────────────────────────────────────────────────────

const TRANSLATED_PARAMS = {
    'entrySeconds': 'Seg. p/ Entrada',
    'exitSeconds': 'Seg. p/ Saída',
    'stopLossPct': 'Stop Loss (%)',
    'minProfitPct': 'Take Profit (%)',
    'trailingStartProfitPct': 'Ativar Trailing após (%)',
    'autoMaxSymbols': 'Máx. Símbolos (Auto)',
    'leverage': 'Alavancagem (x)',
    'makerTimeoutSeconds': 'Timeout Maker (s)',
    'operationMode': 'Modo de Operação',
    'feeType': 'Tipo de Taxa (Fee)'
};

function translateParam(param) {
    if (!param) return '—';
    return TRANSLATED_PARAMS[param] || param;
}

function translateParamValue(param, value) {
    if (param === 'operationMode' && TRANSLATED_MODE_VALUES[value]) {
        return TRANSLATED_MODE_VALUES[value];
    }
    return String(value ?? '—');
}

function AIAnalysisModal({ sessionId, onClose, onApplied, initialData }) {
    const [loading, setLoading] = useState(true);
    const [applying, setApplying] = useState(false);
    const [error, setError] = useState('');
    const [analysis, setAnalysis] = useState('');
    const [suggestedConfig, setSuggestedConfig] = useState({});
    const [currentConfig, setCurrentConfig] = useState({});
    const [analysisId, setAnalysisId] = useState(null);
    const [applied, setApplied] = useState(false);

    useEffect(() => {
        if (initialData) {
            setAnalysis(initialData.analysis_text || '');
            setSuggestedConfig(initialData.suggested_config || {});
            setCurrentConfig({});
            setAnalysisId(initialData.id);
            setApplied(!!initialData.applied);
            setLoading(false);
            return;
        }

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
                if (!cancelled) setError(e.message || 'Erro ao gerar análise');
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        run();
        return () => { cancelled = true; };
    }, [sessionId, initialData]);

    const handleApply = async () => {
        setApplying(true);
        try {
            await applyBotAISuggestions(sessionId, suggestedConfig, analysisId);
            setApplied(true);
            onApplied?.();
        } catch (e) {
            alert(e.message || 'Erro ao aplicar sugestões');
        } finally {
            setApplying(false);
        }
    };

    const configKeys = Object.keys(suggestedConfig);

    const parts = analysis.split('<!-- MORE -->');
    const summaryStr = parts[0];
    const detailsStr = parts.length > 1 ? parts[1] : '';

    return (
        <div className="modal-overlay" onClick={onClose} style={{ zIndex: 10000 }}>
            <div className="modal-content" style={{ maxWidth: '850px', width: '90%', maxHeight: '85vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <img src={aiIcon} alt="IA" style={{ width: '22px', height: '22px' }} />
                        Análise IA — Bot #{sessionId}
                    </h3>
                    <button className="modal-close" onClick={onClose}>
                        <FaXmark aria-hidden="true" />
                    </button>
                </div>

                <div className="modal-body" style={{ padding: '24px' }}>
                    {loading && (
                        <div style={{ textAlign: 'center', padding: '40px 0' }}>
                            <img src={aiIcon} alt="IA" style={{ width: '40px', height: '40px', animation: 'pulse 1.5s infinite', opacity: 0.6 }} />
                            <div style={{ marginTop: '12px', color: 'var(--text-muted)' }}>Gerando análise com IA...</div>
                        </div>
                    )}

                    {error && <div className="paper-error" style={{ margin: '16px 0' }}>{error}</div>}

                    {!loading && !error && (
                        <>
                            <div
                                className="ai-markdown-content"
                                style={{ lineHeight: '1.7', fontSize: '14px', marginBottom: detailsStr ? '16px' : '24px', color: 'var(--text-primary)' }}
                                dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked(summaryStr)) }}
                            />

                            {detailsStr && (
                                <details className="ai-details-toggle" style={{ marginBottom: '24px', background: 'var(--bg-card)', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
                                    <summary style={{ cursor: 'pointer', color: '#a78bfa', fontWeight: 600, fontSize: '13.5px', userSelect: 'none' }}>
                                        Detalhes Completos da Análise
                                    </summary>
                                    <div
                                        className="ai-markdown-content"
                                        style={{ marginTop: '16px', lineHeight: '1.6', fontSize: '13px', color: 'var(--text-secondary)' }}
                                        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked(detailsStr)) }}
                                    />
                                </details>
                            )}

                            {configKeys.length > 0 && (
                                <>
                                    <h4 className="icon-inline" style={{ margin: '0 0 12px', fontSize: '14px', color: 'var(--text-primary)' }}>
                                        <FaWandMagicSparkles aria-hidden="true" />
                                        Sugestões de Configuração
                                    </h4>
                                    <table className="data-table" style={{ fontSize: '12px', marginBottom: '20px', width: '100%' }}>
                                        <thead>
                                            <tr>
                                                <th>Parâmetro</th>
                                                <th className="right">Atual</th>
                                                <th className="right">Sugestão IA</th>
                                                <th style={{ paddingLeft: '24px' }}>Motivo</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {configKeys.map(k => {
                                                const currentValRaw = currentConfig[k];
                                                const suggestedRaw = suggestedConfig[k];
                                                let suggestedVal = suggestedRaw;
                                                let reasoning = '';

                                                if (suggestedRaw && typeof suggestedRaw === 'object' && suggestedRaw.value !== undefined) {
                                                     suggestedVal = suggestedRaw.value;
                                                     reasoning = suggestedRaw.reason || '';
                                                }

                                                return (
                                                    <tr key={k}>
                                                        <td>{translateParam(k)}</td>
                                                        <td className="right monospace" style={{ color: 'var(--text-muted)' }}>{translateParamValue(k, currentValRaw)}</td>
                                                        <td className="right monospace bold" style={{ color: '#00e68a' }}>{translateParamValue(k, suggestedVal)}</td>
                                                        <td className="muted" style={{ paddingLeft: '24px', fontSize: '12px', lineHeight: '1.4', maxWidth: '300px', whiteSpace: 'normal', color: 'var(--text-secondary)' }}>
                                                            {reasoning || '—'}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>

                                    {!applied ? (
                                        <button
                                            className="session-edit-btn"
                                            style={{ width: '100%', padding: '10px', background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.4)', color: '#a78bfa', fontWeight: 600 }}
                                            onClick={handleApply}
                                            disabled={applying}
                                        >
                                            {applying ? 'Aplicando...' : (
                                                <span className="icon-inline">
                                                    <FaCircleCheck aria-hidden="true" />
                                                    Aplicar Sugestões
                                                </span>
                                            )}
                                        </button>
                                    ) : (
                                        <div className="icon-inline" style={{ textAlign: 'center', padding: '10px', color: 'var(--accent-green)', fontWeight: 600, justifyContent: 'center' }}>
                                            <FaCircleCheck aria-hidden="true" />
                                            Sugestões aplicadas com sucesso!
                                        </div>
                                    )}
                                </>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}


// ─── Aba de Logs de Ordens ────────────────────────────────────────────────────────────

const EVENT_LABELS = {
    open_attempt:     'Tentativa de Abertura',
    open_success:     'Abertura com Sucesso',
    close_attempt:    'Tentativa de Fechamento',
    close_success:    'Fechamento com Sucesso',
    direction_skip:   'Direção Bloqueada',
    symbol_not_found: 'Símbolo não Encontrado',
    // Motivo: exibir eventos específicos do ciclo de entrada limit manual pendente.
    pending_entry_created: 'Entrada Limit Criada',
    pending_entry_filled: 'Entrada Limit Preenchida',
    pending_entry_canceled: 'Entrada Limit Cancelada',
    error:            'Erro',
    api_error:        'Erro de API',
    maker_fallback:   'Fallback para Taker',
    tp_cancelled:     'TP Cancelada',
    tp_reorder:       'TP Re-colocada',
    tp_reorder_failed:'TP Falhou Re-colocar',
    tp_create_failed: 'TP Falhou Criar',
    close_retry:      'Retry Fechamento',
    break_even_activated: 'Break-Even Ativado',
};

const LEVEL_COLORS = {
    INFO:  { bg: 'rgba(59,130,246,0.15)',  color: '#60a5fa' },
    WARN:  { bg: 'rgba(234,179,8,0.15)',   color: '#fbbf24' },
    ERROR: { bg: 'rgba(239,68,68,0.15)',   color: '#f87171' },
};

function fmtLogDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// ─── ServerLogsTab ───────────────────────────────────────────────────────────

function ServerLogsTab() {
    const LIMIT = 100;
    const [logs, setLogs] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [levelFilter, setLevelFilter] = useState('');
    const [search, setSearch] = useState('');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [autoRefresh, setAutoRefresh] = useState(false);
    const [lastUpdate, setLastUpdate] = useState(null);
    const [sortConfig, setSortConfig] = useState(null);
    const [moduleFilter, setModuleFilter] = useState('');

    const sortedLogs = useMemo(() => {
        let sortableItems = [...logs];
        if (sortConfig !== null) {
            sortableItems.sort((a, b) => {
                let aValue = 0, bValue = 0;
                switch (sortConfig.key) {
                    case 'time': aValue = new Date(a.createdAt || 0).getTime(); bValue = new Date(b.createdAt || 0).getTime(); break;
                    case 'level': aValue = (a.level || '').toLowerCase(); bValue = (b.level || '').toLowerCase(); break;
                    case 'module': aValue = (a.module || '').toLowerCase(); bValue = (b.module || '').toLowerCase(); break;
                    case 'message': aValue = (a.message || '').toLowerCase(); bValue = (b.message || '').toLowerCase(); break;
                    default: return 0;
                }
                if (aValue < bValue) return sortConfig.direction === 'ascending' ? -1 : 1;
                if (aValue > bValue) return sortConfig.direction === 'ascending' ? 1 : -1;
                return 0;
            });
        }
        return sortableItems;
    }, [logs, sortConfig]);

    const requestSort = (key) => {
        let direction = 'ascending';
        if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascending') {
            direction = 'descending';
        }
        setSortConfig({ key, direction });
    };

    const fmtGmt3 = (isoStr) => {
        if (!isoStr) return '—';
        return new Date(isoStr).toLocaleString('pt-BR', {
            timeZone: 'America/Sao_Paulo',
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
    };

    const toUtcIso = (localStr) => {
        if (!localStr) return null;
        return new Date(localStr).toISOString();
    };

    const doLoad = useCallback(async (reset = true, currentLogs = []) => {
        setLoading(true);
        const offset = reset ? 0 : currentLogs.length;
        try {
            const res = await fetchServerLogs({
                limit: LIMIT, offset,
                level: levelFilter,
                dateFrom: toUtcIso(dateFrom),
                dateTo: toUtcIso(dateTo),
                search,
                module: moduleFilter,
            });
            if (reset) {
                setLogs(res.data || []);
            } else {
                setLogs(prev => [...prev, ...(res.data || [])]);
            }
            setTotal(res.total ?? 0);
            setLastUpdate(new Date());
        } catch (_) {
            // silencia erro de rede
        } finally {
            setLoading(false);
        }
    }, [levelFilter, search, dateFrom, dateTo, moduleFilter]); // eslint-disable-line react-hooks/exhaustive-deps

    // Recarrega ao montar e sempre que filtros mudam.
    // doLoad é recriado pelo useCallback quando levelFilter/search/dateFrom/dateTo mudam,
    // portanto este efeito dispara automaticamente nas duas situações.
    useEffect(() => { doLoad(true); }, [doLoad]);

    // Auto-refresh a cada 30s
    useEffect(() => {
        if (!autoRefresh) return;
        const timer = setInterval(() => doLoad(true), 30000);
        return () => clearInterval(timer);
    }, [autoRefresh, doLoad]);

    const handleClear = () => {
        setLevelFilter('');
        setModuleFilter('');
        setSearch('');
        setDateFrom('');
        setDateTo('');
    };

    const levelStyle = (level) => {
        switch ((level || '').toUpperCase()) {
            case 'ERROR':
            case 'CRITICAL':
                return { background: 'rgba(239,68,68,0.15)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)' };
            case 'WARNING':
                return { background: 'rgba(234,179,8,0.15)', color: '#facc15', border: '1px solid rgba(234,179,8,0.3)' };
            case 'DEBUG':
                return { background: 'rgba(100,116,139,0.15)', color: '#94a3b8', border: '1px solid rgba(100,116,139,0.3)' };
            default: // INFO
                return { background: 'rgba(59,130,246,0.15)', color: '#60a5fa', border: '1px solid rgba(59,130,246,0.3)' };
        }
    };

    const inputStyle = {
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        color: 'var(--text-primary)',
        borderRadius: '6px',
        padding: '5px 10px',
        fontSize: '12px',
    };

    const MODULE_CATEGORIES = {
        'RealTrading': { label: 'Trading', color: '#4ade80', bg: 'rgba(74,222,128,0.12)', border: 'rgba(74,222,128,0.3)' },
        'real_trader': { label: 'Trading', color: '#4ade80', bg: 'rgba(74,222,128,0.12)', border: 'rgba(74,222,128,0.3)' },
        'CounterTrend': { label: 'Trading', color: '#4ade80', bg: 'rgba(74,222,128,0.12)', border: 'rgba(74,222,128,0.3)' },
        'RealManual': { label: 'Trading', color: '#4ade80', bg: 'rgba(74,222,128,0.12)', border: 'rgba(74,222,128,0.3)' },
        'RealTest': { label: 'Trading', color: '#4ade80', bg: 'rgba(74,222,128,0.12)', border: 'rgba(74,222,128,0.3)' },
        'Order': { label: 'Exchange', color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)' },
        'UserDataWS': { label: 'Exchange', color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)' },
        'Webhook': { label: 'Exchange', color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)' },
        'Snapshot': { label: 'Dados', color: '#2dd4bf', bg: 'rgba(45,212,191,0.12)', border: 'rgba(45,212,191,0.3)' },
        'Reconcile': { label: 'Dados', color: '#2dd4bf', bg: 'rgba(45,212,191,0.12)', border: 'rgba(45,212,191,0.3)' },
        'WS Market': { label: 'Dados', color: '#2dd4bf', bg: 'rgba(45,212,191,0.12)', border: 'rgba(45,212,191,0.3)' },
        'Blacklist': { label: 'Dados', color: '#2dd4bf', bg: 'rgba(45,212,191,0.12)', border: 'rgba(45,212,191,0.3)' },
        'Symbol Syncer': { label: 'Sistema', color: '#94a3b8', bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.3)' },
        'SyncLoop': { label: 'Sistema', color: '#94a3b8', bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.3)' },
        'Server': { label: 'Sistema', color: '#94a3b8', bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.3)' },
        'app': { label: 'Sistema', color: '#94a3b8', bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.3)' },
        'asyncio': { label: 'Infra', color: '#f87171', bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)' },
        'root': { label: 'Infra', color: '#f87171', bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)' },
    };

    const getModuleBadge = (mod) => {
        const cat = MODULE_CATEGORIES[mod];
        if (!cat) return { label: mod || 'server', color: '#a1a1aa', bg: 'rgba(161,161,170,0.12)', border: 'rgba(161,161,170,0.3)' };
        return cat;
    };

    return (
        <div>
            {/* Barra de filtros */}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '14px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Nível:</span>
                <select value={levelFilter} onChange={e => setLevelFilter(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                    <option value="">Todos</option>
                    <option value="INFO">INFO</option>
                    <option value="WARNING">WARNING</option>
                    <option value="ERROR">ERROR</option>
                    <option value="DEBUG">DEBUG</option>
                </select>

                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Módulo:</span>
                <select value={moduleFilter} onChange={e => setModuleFilter(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                    <option value="">Todos</option>
                    <option value="RealTrading">RealTrading</option>
                    <option value="CounterTrend">CounterTrend</option>
                    <option value="Order">Order</option>
                    <option value="Webhook">Webhook</option>
                    <option value="Snapshot">Snapshot</option>
                    <option value="Symbol Syncer">Symbol Syncer</option>
                    <option value="UserDataWS">UserDataWS</option>
                    <option value="Reconcile">Reconcile</option>
                    <option value="SyncLoop">SyncLoop</option>
                    <option value="WS Market">WS Market</option>
                    <option value="Blacklist">Blacklist</option>
                    <option value="asyncio">asyncio</option>
                </select>

                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>De:</span>
                <input
                    type="datetime-local"
                    value={dateFrom}
                    onChange={e => setDateFrom(e.target.value)}
                    style={{ ...inputStyle, colorScheme: 'dark', cursor: 'pointer' }}
                />
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Até:</span>
                <input
                    type="datetime-local"
                    value={dateTo}
                    onChange={e => setDateTo(e.target.value)}
                    style={{ ...inputStyle, colorScheme: 'dark', cursor: 'pointer' }}
                />

                <input
                    type="text"
                    placeholder="Buscar mensagem ou módulo..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    style={{ ...inputStyle, minWidth: '200px' }}
                />

                {(levelFilter || moduleFilter || search || dateFrom || dateTo) && (
                    <button onClick={handleClear} style={{ ...inputStyle, cursor: 'pointer', color: 'var(--text-muted)' }}>
                        <span className="icon-inline">
                            <FaXmark aria-hidden="true" />
                            Limpar
                        </span>
                    </button>
                )}

                <div style={{ marginLeft: 'auto', display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <label style={{ display: 'flex', gap: '6px', alignItems: 'center', fontSize: '12px', color: 'var(--text-muted)', cursor: 'pointer' }}>
                        <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
                        Auto 30s
                    </label>
                    {lastUpdate && (
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            Atualizado às {lastUpdate.toLocaleTimeString('pt-BR', { timeZone: 'America/Sao_Paulo' })}
                        </span>
                    )}
                    <button
                        onClick={() => doLoad(true)}
                        disabled={loading}
                        style={{ ...inputStyle, background: 'var(--accent-color)', color: '#fff', border: 'none', cursor: loading ? 'not-allowed' : 'pointer' }}
                    >
                        {loading ? '...' : '↻ Atualizar'}
                    </button>
                </div>
            </div>

            {/* Contagem */}
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '10px' }}>
                {total} log{total !== 1 ? 's' : ''} encontrado{total !== 1 ? 's' : ''} · exibindo {logs.length}
            </div>

            {/* Tabela */}
            <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                            <th onClick={() => requestSort('time')} style={{ textAlign: 'left', padding: '8px 10px', color: 'var(--text-muted)', fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer' }}>Horário (GMT-3){sortConfig?.key === 'time' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                            <th onClick={() => requestSort('level')} style={{ textAlign: 'left', padding: '8px 10px', color: 'var(--text-muted)', fontWeight: 600, cursor: 'pointer' }}>Nível{sortConfig?.key === 'level' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                            <th style={{ textAlign: 'left', padding: '8px 10px', color: 'var(--text-muted)', fontWeight: 600 }}>Tag</th>
                            <th onClick={() => requestSort('module')} style={{ textAlign: 'left', padding: '8px 10px', color: 'var(--text-muted)', fontWeight: 600, cursor: 'pointer' }}>Módulo{sortConfig?.key === 'module' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                            <th onClick={() => requestSort('message')} style={{ textAlign: 'left', padding: '8px 10px', color: 'var(--text-muted)', fontWeight: 600, cursor: 'pointer' }}>Mensagem{sortConfig?.key === 'message' ? (sortConfig.direction === 'ascending' ? ' ↑' : ' ↓') : ''}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading && logs.length === 0 && (
                            <tr><td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>Carregando...</td></tr>
                        )}
                        {!loading && logs.length === 0 && (
                            <tr><td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>Nenhum log encontrado.</td></tr>
                        )}
                        {sortedLogs.map(log => (
                            <tr key={log.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '7px 10px', color: 'var(--text-muted)', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: '11px' }}>
                                    {fmtGmt3(log.createdAt)}
                                </td>
                                <td style={{ padding: '7px 10px' }}>
                                    <span style={{
                                        ...levelStyle(log.level),
                                        padding: '2px 8px', borderRadius: '4px',
                                        fontSize: '11px', fontWeight: 700, whiteSpace: 'nowrap',
                                    }}>
                                        {log.level}
                                    </span>
                                </td>
                                <td style={{ padding: '7px 10px' }}>
                                    {(() => {
                                        const badge = getModuleBadge(log.module);
                                        return (
                                            <span style={{
                                                background: badge.bg,
                                                color: badge.color,
                                                border: `1px solid ${badge.border}`,
                                                padding: '2px 7px',
                                                borderRadius: '4px',
                                                fontSize: '10px',
                                                fontWeight: 600,
                                                whiteSpace: 'nowrap',
                                            }}>
                                                {badge.label}
                                            </span>
                                        );
                                    })()}
                                </td>
                                <td style={{ padding: '7px 10px', color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '11px', whiteSpace: 'nowrap' }}>
                                    {log.module}
                                </td>
                                <td style={{ padding: '7px 10px', color: 'var(--text-primary)', wordBreak: 'break-word', maxWidth: '600px' }}>
                                    {log.message}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Carregar mais */}
            {logs.length < total && (
                <div style={{ textAlign: 'center', marginTop: '16px' }}>
                    <button
                        onClick={() => doLoad(false, logs)}
                        disabled={loading}
                        style={{
                            background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)', borderRadius: '6px', padding: '8px 24px',
                            cursor: loading ? 'not-allowed' : 'pointer', fontSize: '12px',
                        }}
                    >
                        {loading ? 'Carregando...' : `Carregar mais (${total - logs.length} restantes)`}
                    </button>
                </div>
            )}
        </div>
    );
}


function OrderLogsTab({ sessions }) {
    const [selectedId, setSelectedId] = useState(() => {
        const first = sessions[0];
        return first ? (first.id || first.sessionId) : null;
    });
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(false);
    const [levelFilter, setLevelFilter] = useState('');
    const [eventFilter, setEventFilter] = useState('');
    const [expanded, setExpanded] = useState(null);

    useEffect(() => {
        if (!selectedId) return;
        let cancelled = false;
        setLoading(true);
        setLogs([]);
        fetchRealOrderLogs(selectedId, { level: levelFilter, event: eventFilter })
            .then(res => { if (!cancelled) setLogs(res.data || []); })
            .catch(() => { if (!cancelled) setLogs([]); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [selectedId, levelFilter, eventFilter]);

    const selectStyle = {
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        color: 'var(--text-primary)',
        borderRadius: '6px',
        padding: '5px 10px',
        fontSize: '12px',
        cursor: 'pointer',
    };

    return (
        <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
            {/* Painel esquerdo — lista de sessões */}
            <div style={{
                width: '220px', flexShrink: 0,
                background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                borderRadius: '10px', overflow: 'hidden',
            }}>
                <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-color)', fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Sessões
                </div>
                {sessions.length === 0 && (
                    <div style={{ padding: '16px', fontSize: '13px', color: 'var(--text-muted)' }}>Nenhuma sessão encontrada.</div>
                )}
                {sessions.map(s => {
                    const sid = s.id || s.sessionId;
                    const name = s.session_name || s.sessionName || `Bot #${sid}`;
                    const exch = (s.exchange || 'binance').toUpperCase();
                    const isActive = s.active;
                    const isSelected = sid === selectedId;
                    return (
                        <div
                            key={sid}
                            onClick={() => setSelectedId(sid)}
                            style={{
                                padding: '10px 14px', cursor: 'pointer',
                                background: isSelected ? 'rgba(99,102,241,0.12)' : 'transparent',
                                borderLeft: isSelected ? '3px solid #818cf8' : '3px solid transparent',
                                transition: 'background 0.15s',
                            }}
                        >
                            <div style={{ fontSize: '12px', fontWeight: 600, color: isSelected ? '#c7d2fe' : 'var(--text-primary)', marginBottom: '2px' }}>{name}</div>
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', gap: '6px', alignItems: 'center' }}>
                                {exch}
                                {isActive && <span style={{ color: '#4ade80', fontWeight: 600 }}>● ATIVO</span>}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Painel direito — logs */}
            <div style={{ flex: 1, minWidth: 0 }}>
                {/* Filtros */}
                <div style={{ display: 'flex', gap: '10px', marginBottom: '14px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Filtrar:</span>
                    <select value={levelFilter} onChange={e => setLevelFilter(e.target.value)} style={selectStyle}>
                        <option value="">Todos os níveis</option>
                        <option value="INFO">INFO</option>
                        <option value="WARN">WARN</option>
                        <option value="ERROR">ERROR</option>
                    </select>
                    <select value={eventFilter} onChange={e => setEventFilter(e.target.value)} style={selectStyle}>
                        <option value="">Todos os eventos</option>
                        {Object.entries(EVENT_LABELS).map(([k, v]) => (
                            <option key={k} value={k}>{v}</option>
                        ))}
                    </select>
                    {logs.length > 0 && (
                        <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: 'auto' }}>{logs.length} registro(s)</span>
                    )}
                </div>

                {/* Estados */}
                {!selectedId && (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px', fontSize: '14px' }}>
                        Selecione um bot na lista ao lado.
                    </div>
                )}
                {selectedId && loading && (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px', fontSize: '14px' }}>
                        Carregando logs...
                    </div>
                )}
                {selectedId && !loading && logs.length === 0 && (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px', fontSize: '14px' }}>
                        Nenhum log encontrado para esta sessão.
                    </div>
                )}

                {/* Tabela */}
                {selectedId && !loading && logs.length > 0 && (
                    <div style={{ overflowX: 'auto' }}>
                        <table className="data-table" style={{ fontSize: '12px' }}>
                            <thead>
                                <tr>
                                    <th>Horário</th>
                                    <th>Nível</th>
                                    <th>Evento</th>
                                    <th>Símbolo</th>
                                    <th>Dir.</th>
                                    <th>Mensagem</th>
                                    <th>Detalhes</th>
                                </tr>
                            </thead>
                            <tbody>
                                {logs.map(log => {
                                    const levelStyle = LEVEL_COLORS[log.level] || LEVEL_COLORS.INFO;
                                    const rowBg = log.level === 'ERROR'
                                        ? 'rgba(239,68,68,0.06)'
                                        : log.level === 'WARN'
                                            ? 'rgba(234,179,8,0.05)'
                                            : undefined;
                                    const hasDetails = log.details && Object.keys(log.details).length > 0;
                                    const isExpanded = expanded === log.id;
                                    return (
                                        <Fragment key={log.id}>
                                            <tr style={{ background: rowBg }}>
                                                <td className="monospace" style={{ whiteSpace: 'nowrap', color: 'var(--text-muted)', fontSize: '11px' }}>
                                                    {fmtLogDate(log.createdAt)}
                                                </td>
                                                <td>
                                                    <span style={{
                                                        display: 'inline-block', padding: '2px 7px', borderRadius: '4px',
                                                        fontSize: '10px', fontWeight: 700, letterSpacing: '0.04em',
                                                        background: levelStyle.bg, color: levelStyle.color,
                                                    }}>
                                                        {log.level}
                                                    </span>
                                                </td>
                                                <td style={{ whiteSpace: 'nowrap', fontSize: '12px' }}>
                                                    {EVENT_LABELS[log.event] || log.event}
                                                </td>
                                                <td style={{ fontWeight: 600, fontSize: '12px', color: 'var(--text-primary)' }}>
                                                    {log.symbol ? log.symbol.replace('USDT', '') : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                                                </td>
                                                <td>
                                                    {log.direction ? (
                                                        <span className={`badge ${log.direction === 'SHORT' ? 'badge-short' : 'badge-long'}`} style={{ fontSize: '10px', padding: '2px 6px' }}>
                                                            {log.direction}
                                                        </span>
                                                    ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                                                </td>
                                                <td style={{ fontSize: '12px', maxWidth: '380px' }}>
                                                    {log.message || <span style={{ color: 'var(--text-muted)' }}>—</span>}
                                                </td>
                                                <td>
                                                    {hasDetails ? (
                                                        <button
                                                            onClick={e => { e.stopPropagation(); setExpanded(isExpanded ? null : log.id); }}
                                                            style={{
                                                                background: isExpanded ? 'rgba(99,102,241,0.2)' : 'rgba(255,255,255,0.06)',
                                                                border: '1px solid var(--border-color)',
                                                                color: isExpanded ? '#c7d2fe' : 'var(--text-muted)',
                                                                borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: '11px',
                                                            }}
                                                        >
                                                            {'{ }'}
                                                        </button>
                                                    ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                                                </td>
                                            </tr>
                                            {isExpanded && (
                                                <tr style={{ background: 'rgba(99,102,241,0.06)' }}>
                                                    <td colSpan={7} style={{ padding: '0 12px 10px 12px' }}>
                                                        <pre style={{
                                                            margin: 0, padding: '10px 12px',
                                                            background: 'rgba(0,0,0,0.3)', borderRadius: '6px',
                                                            fontSize: '11px', color: '#a5b4fc',
                                                            whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                                                            fontFamily: "'Roboto Mono', monospace",
                                                        }}>
                                                            {JSON.stringify(log.details, null, 2)}
                                                        </pre>
                                                    </td>
                                                </tr>
                                            )}
                                        </Fragment>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}


// ─── Aba de Análises IA ───────────────────────────────────────────────────────────────

function AIAnalysesTab({ sessions, onOpenAnalysis }) {
    const [analyses, setAnalyses] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedBotId, setSelectedBotId] = useState(null);

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            setLoading(true);
            setError('');
            try {
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
                if (!cancelled) {
                    setAnalyses(allAnalyses);
                    if (allAnalyses.length > 0) {
                        setSelectedBotId(allAnalyses[0].sessionId);
                    }
                }
            } catch (e) {
                if (!cancelled) setError(e.message || 'Erro ao carregar análises');
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        load();
        return () => { cancelled = true; };
    }, [sessions.length]);

    const fmtDateAI = (iso) => {
        if (!iso) return '—';
        return new Date(iso).toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', year: '2-digit',
            hour: '2-digit', minute: '2-digit',
        });
    };

    if (loading) return <div className="sessions-loading" style={{ padding: '40px 0' }}>Carregando análises IA...</div>;
    if (error) {
        return (
            <div className="paper-error icon-inline" style={{ margin: '16px 0' }}>
                <FaTriangleExclamation aria-hidden="true" />
                {error}
            </div>
        );
    }

    const grouped = {};
    analyses.forEach(a => {
        if (!grouped[a.sessionId]) {
            grouped[a.sessionId] = {
                name: a.sessionName,
                items: []
            };
        }
        grouped[a.sessionId].items.push(a);
    });

    const botIds = Object.keys(grouped);

    return (
        <div className="section-block">
            <div className="section-header">
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    Histórico de Análises IA ({analyses.length})
                </h2>
            </div>

            {botIds.length === 0 ? (
                <div style={{
                    textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)',
                    background: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-color)', marginTop: '12px',
                }}>
                    <img src={aiIcon} alt="IA" style={{ width: '32px', height: '32px', opacity: 0.4, marginBottom: '12px' }} />
                    <div>Nenhuma análise IA realizada ainda.</div>
                    <div style={{ fontSize: '12px', marginTop: '4px' }}>Clique no ícone IA na tabela de bots para gerar uma análise.</div>
                </div>
            ) : (
                <div style={{ display: 'flex', gap: '24px', marginTop: '16px', alignItems: 'flex-start' }}>

                    {/* Lateral Esquerda - Lista de Bots */}
                    <div style={{ width: '280px', display: 'flex', flexDirection: 'column', gap: '8px', flexShrink: 0 }}>
                        <div className="icon-inline" style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, paddingBottom: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '4px' }}>
                            <FaRobot aria-hidden="true" />
                            Bots Avaliados
                        </div>
                        {botIds.map(id => {
                            const botData = grouped[id];
                            const isActive = String(selectedBotId) === String(id);
                            return (
                                <div
                                    key={id}
                                    onClick={() => setSelectedBotId(id)}
                                    style={{
                                        padding: '12px 16px',
                                        background: isActive ? 'rgba(139,92,246,0.1)' : 'var(--bg-secondary)',
                                        border: `1px solid ${isActive ? 'rgba(139,92,246,0.4)' : 'var(--border-color)'}`,
                                        borderRadius: 'var(--radius-sm)',
                                        cursor: 'pointer',
                                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                        transition: 'all 0.2s',
                                        color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)'
                                    }}
                                >
                                    <span style={{ fontWeight: 600, fontSize: '13px', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                                        {botData.name}
                                    </span>
                                    <span style={{ background: 'rgba(255,255,255,0.05)', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', flexShrink: 0 }}>
                                        {botData.items.length}
                                    </span>
                                </div>
                            );
                        })}
                    </div>

                    {/* Lateral Direita - Análises do Bot */}
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '12px', minWidth: 0 }}>
                        <div className="icon-inline" style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, paddingBottom: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '4px' }}>
                            <FaChartColumn aria-hidden="true" />
                            Análises Detalhadas ({grouped[selectedBotId]?.items.length})
                        </div>
                        {grouped[selectedBotId]?.items.map((a, idx) => {
                             const textParts = (a.analysis_text || '').split('<!-- MORE -->');
                             const briefSummary = textParts[0];

                             return (
                                <div key={a.id || idx} style={{
                                    background: 'var(--bg-card)',
                                    border: '1px solid var(--border-color)',
                                    borderRadius: 'var(--radius-md)',
                                    padding: '16px 20px',
                                    cursor: 'pointer',
                                    transition: 'border-color 0.2s'
                                }}
                                    className="ai-card-hover"
                                    onClick={() => onOpenAnalysis?.(a)}
                                    title="Clique para abrir todos os detalhes"
                                >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                            <img src={aiIcon} alt="IA" style={{ width: '16px', height: '16px' }} />
                                            <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>Análise #{a.id || idx}</span>
                                            {a.applied && (
                                                <span className="icon-inline" style={{ fontSize: '10px', color: 'var(--accent-green)', background: 'rgba(0,230,138,0.1)', padding: '2px 6px', borderRadius: '4px', border: '1px solid rgba(0,230,138,0.2)' }}>
                                                    <FaCircleCheck aria-hidden="true" />
                                                    Aplicada
                                                </span>
                                            )}
                                        </div>
                                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{fmtDateAI(a.created_at)}</span>
                                    </div>

                                    <div
                                        className="ai-markdown-content"
                                        style={{
                                            fontSize: '13px', lineHeight: '1.6', color: 'var(--text-secondary)',
                                            maxHeight: '60px', overflow: 'hidden',
                                            maskImage: 'linear-gradient(to bottom, black 50%, transparent)',
                                            WebkitMaskImage: 'linear-gradient(to bottom, black 50%, transparent)',
                                        }}
                                        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(briefSummary ? marked(briefSummary) : 'Análise sem texto.') }}
                                    />

                                    {a.suggested_config && Object.keys(a.suggested_config).length > 0 && (
                                        <div style={{ marginTop: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                            {Object.entries(a.suggested_config).map(([k, vRaw]) => {
                                                const vValue = (typeof vRaw === 'object' && vRaw !== null) ? vRaw.value : vRaw;
                                                return (
                                                    <span key={k} style={{
                                                        fontSize: '11px', padding: '4px 10px',
                                                        background: 'rgba(139,92,246,0.1)',
                                                        border: '1px solid rgba(139,92,246,0.3)',
                                                        borderRadius: '6px', color: '#a78bfa',
                                                    }}>
                                                        {translateParam(k)}: <strong>{translateParamValue(k, vValue)}</strong>
                                                    </span>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

// ─── Modal Confirm ───────────────────────────────────────────────────────────────────
