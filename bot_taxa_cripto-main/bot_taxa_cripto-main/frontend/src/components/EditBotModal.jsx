import { useEffect, useMemo, useState } from 'react';
import {
    FaCircleInfo,
    FaCircleCheck,
    FaFilter,
    FaFloppyDisk,
    FaPenToSquare,
    FaShieldHalved,
    FaChartLine,
    FaTriangleExclamation,
    FaXmark,
} from 'react-icons/fa6';

function asNumberOrNull(value) {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
}

function asString(value) {
    return value === null || value === undefined ? '' : String(value);
}

function parseLocalizedNumber(raw, { label, integer = false, min = null, max = null, required = false }) {
    const input = asString(raw).trim();
    if (!input) {
        if (required) return { value: null, error: `${label} é obrigatório.` };
        return { value: null, error: '' };
    }

    const compact = input.replace(/\s+/g, '');
    if (!/^\d+(?:[.,]\d+)?$/.test(compact)) {
        return { value: null, error: `${label} inválido. Use apenas números (ex: 1,5 ou 1.5).` };
    }

    const parsed = Number(compact.replace(',', '.'));
    if (!Number.isFinite(parsed)) {
        return { value: null, error: `${label} inválido.` };
    }
    if (integer && !Number.isInteger(parsed)) {
        return { value: null, error: `${label} deve ser inteiro.` };
    }
    if (min !== null && parsed < min) {
        return { value: null, error: `${label} deve ser >= ${min}.` };
    }
    if (max !== null && parsed > max) {
        return { value: null, error: `${label} deve ser <= ${max}.` };
    }

    return { value: parsed, error: '' };
}

function sameValue(a, b) {
    if (a === null || a === undefined) return b === null || b === undefined;
    if (b === null || b === undefined) return false;
    if (typeof a === 'number' || typeof b === 'number') {
        return Number(a) === Number(b);
    }
    return String(a).trim() === String(b).trim();
}

function buildSnapshot(session) {
    const cfg = session?.config || {};
    return {
        sessionName: String(session?.sessionName || session?.session_name || ''),
        capital: asNumberOrNull(cfg.capital ?? session?.capital),
        stopLossPct: asNumberOrNull(cfg.stopLossPct ?? cfg.stop_loss_pct),
        stopLossUsd: asNumberOrNull(cfg.stopLossUsd ?? cfg.stop_loss_usd),
        minProfitPct: asNumberOrNull(cfg.minProfitPct ?? cfg.min_profit_pct),
        targetTakeProfitPct: asNumberOrNull(cfg.targetTakeProfitPct ?? cfg.target_take_profit_pct),
        trailingStopPct: asNumberOrNull(cfg.trailingStopPct ?? cfg.trailing_stop_pct),
        trailingStartProfitPct: asNumberOrNull(cfg.trailingStartProfitPct ?? cfg.trailing_start_profit_pct),
        entrySeconds: asNumberOrNull(cfg.entrySeconds ?? cfg.entry_seconds ?? 30),
        exitSeconds: asNumberOrNull(cfg.exitSeconds ?? cfg.exit_seconds ?? 30),
        makerTimeoutSeconds: asNumberOrNull(cfg.makerTimeoutSeconds ?? cfg.maker_timeout_seconds ?? 8),
        autoMaxSymbols: asNumberOrNull(cfg.autoMaxSymbols ?? cfg.auto_max_symbols ?? 8),
        autoMinScore: asNumberOrNull(cfg.autoMinScore ?? cfg.auto_min_score ?? 50),
        minFundingRatePct: asNumberOrNull(cfg.minFundingRatePct ?? cfg.min_funding_rate_pct ?? 0.001),
        ctSortCriteria: String(cfg.ctSortCriteria ?? cfg.ct_sort_criteria ?? 'score'),
        operationMode: String(cfg.operationMode ?? cfg.operation_mode ?? 'manual'),
        breakEvenAtPct: asNumberOrNull(cfg.breakEvenAtPct ?? cfg.break_even_at_pct),
    };
}

export default function EditBotModal({ session, onSave, onClose }) {
    const snapshot = useMemo(() => buildSnapshot(session), [session]);
    const isCounterTrend = snapshot.operationMode === 'counter_trend';
    // Motivo: esconder/ignorar exitSeconds em modos que não expiram por tempo.
    const isNoTimeoutMode = isCounterTrend || snapshot.operationMode === 'post_funding_follow';
    const sessionId = session?.sessionId || session?.id;

    const [sessionName, setSessionName] = useState(snapshot.sessionName);
    const [capital, setCapital] = useState(asString(snapshot.capital));
    const [stopLossPct, setStopLossPct] = useState(asString(snapshot.stopLossPct));
    const [stopLossUsd, setStopLossUsd] = useState(asString(snapshot.stopLossUsd));
    const [minProfitPct, setMinProfitPct] = useState(asString(snapshot.minProfitPct));
    const [targetTakeProfitPct, setTargetTakeProfitPct] = useState(asString(snapshot.targetTakeProfitPct));
    const [trailingStopPct, setTrailingStopPct] = useState(asString(snapshot.trailingStopPct));
    const [trailingStartProfitPct, setTrailingStartProfitPct] = useState(asString(snapshot.trailingStartProfitPct));
    const [entrySeconds, setEntrySeconds] = useState(asString(snapshot.entrySeconds ?? 30));
    const [exitSeconds, setExitSeconds] = useState(asString(snapshot.exitSeconds ?? 30));
    const [makerTimeoutSeconds, setMakerTimeoutSeconds] = useState(asString(snapshot.makerTimeoutSeconds ?? 8));
    const [autoMaxSymbols, setAutoMaxSymbols] = useState(asString(snapshot.autoMaxSymbols ?? 8));
    const [autoMinScore, setAutoMinScore] = useState(asString(snapshot.autoMinScore ?? 50));
    const [minFundingRatePct, setMinFundingRatePct] = useState(asString(snapshot.minFundingRatePct ?? 0.001));
    const [ctSortCriteria, setCtSortCriteria] = useState(snapshot.ctSortCriteria);
    const [breakEvenAtPct, setBreakEvenAtPct] = useState(asString(snapshot.breakEvenAtPct));
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onClose]);

    useEffect(() => {
        setSessionName(snapshot.sessionName);
        setCapital(asString(snapshot.capital));
        setStopLossPct(asString(snapshot.stopLossPct));
        setStopLossUsd(asString(snapshot.stopLossUsd));
        setMinProfitPct(asString(snapshot.minProfitPct));
        setTargetTakeProfitPct(asString(snapshot.targetTakeProfitPct));
        setTrailingStopPct(asString(snapshot.trailingStopPct));
        setTrailingStartProfitPct(asString(snapshot.trailingStartProfitPct));
        setEntrySeconds(asString(snapshot.entrySeconds ?? 30));
        setExitSeconds(asString(snapshot.exitSeconds ?? 30));
        setMakerTimeoutSeconds(asString(snapshot.makerTimeoutSeconds ?? 8));
        setAutoMaxSymbols(asString(snapshot.autoMaxSymbols ?? 8));
        setAutoMinScore(asString(snapshot.autoMinScore ?? 50));
        setMinFundingRatePct(asString(snapshot.minFundingRatePct ?? 0.001));
        setCtSortCriteria(snapshot.ctSortCriteria);
        setBreakEvenAtPct(asString(snapshot.breakEvenAtPct));
        setError('');
        setSuccess('');
    }, [snapshot]);

    if (!session || !sessionId) return null;

    const handleSave = async () => {
        setError('');
        setSuccess('');

        const capitalP = parseLocalizedNumber(capital, { label: 'Capital Base', min: 0.01, required: true });
        const stopLossPctP = parseLocalizedNumber(stopLossPct, { label: 'Stop Loss Preço (%)', min: 0 });
        const stopLossUsdP = parseLocalizedNumber(stopLossUsd, { label: 'Stop Loss (USDT)', min: 0 });
        const minProfitPctP = parseLocalizedNumber(minProfitPct, { label: 'Lucro Mínimo (%)', min: 0 });
        const targetTakeProfitPctP = parseLocalizedNumber(targetTakeProfitPct, { label: 'Take Profit Alvo (%)', min: 0 });
        const trailingStopPctP = parseLocalizedNumber(trailingStopPct, { label: 'Trailing Stop (%)', min: 0 });
        const trailingStartProfitPctP = parseLocalizedNumber(trailingStartProfitPct, { label: 'Ativar Trailing após Lucro (%)', min: 0 });
        const entrySecondsP = parseLocalizedNumber(entrySeconds, { label: 'Tempo Entrada (s)', integer: true, min: 1, max: 32767, required: true });
        const exitSecondsP = parseLocalizedNumber(exitSeconds, { label: 'Tempo Saída (s)', integer: true, min: 1, max: 32767, required: !isNoTimeoutMode });
        // Motivo: alinhar edição com novo limite de timeout maker aceito pelo backend (até 900s).
        const makerTimeoutP = parseLocalizedNumber(makerTimeoutSeconds, { label: 'Timeout Maker (s)', integer: true, min: 2, max: 900, required: true });
        const autoMaxSymbolsP = parseLocalizedNumber(autoMaxSymbols, { label: 'Max Símbolos', integer: true, min: 1, max: 30, required: true });
        const autoMinScoreP = parseLocalizedNumber(autoMinScore, { label: 'Score Mínimo', min: 0, max: 100, required: true });
        // Motivo: permitir editar o gate minimo de funding para novas entradas.
        const minFundingRatePctP = parseLocalizedNumber(minFundingRatePct, { label: 'Funding Minimo (%)', min: 0, max: 5, required: true });
        const breakEvenAtPctP = parseLocalizedNumber(breakEvenAtPct, { label: 'Break-Even (%)', min: 0 });

        const validationError = [
            capitalP.error,
            stopLossPctP.error,
            stopLossUsdP.error,
            minProfitPctP.error,
            targetTakeProfitPctP.error,
            trailingStopPctP.error,
            trailingStartProfitPctP.error,
            entrySecondsP.error,
            !isNoTimeoutMode ? exitSecondsP.error : '',
            makerTimeoutP.error,
            autoMaxSymbolsP.error,
            autoMinScoreP.error,
            minFundingRatePctP.error,
            breakEvenAtPctP.error,
        ].find(Boolean);
        if (validationError) {
            setError(validationError);
            return;
        }

        const normalized = {
            sessionName: sessionName.trim(),
            capital: capitalP.value,
            stopLossPct: stopLossPctP.value,
            stopLossUsd: stopLossUsdP.value,
            minProfitPct: minProfitPctP.value,
            targetTakeProfitPct: targetTakeProfitPctP.value,
            trailingStopPct: trailingStopPctP.value,
            trailingStartProfitPct: trailingStartProfitPctP.value,
            entrySeconds: entrySecondsP.value,
            makerTimeoutSeconds: makerTimeoutP.value,
            autoMaxSymbols: autoMaxSymbolsP.value,
            autoMinScore: autoMinScoreP.value,
            minFundingRatePct: minFundingRatePctP.value,
            ctSortCriteria,
            breakEvenAtPct: breakEvenAtPctP.value,
        };
        if (!isNoTimeoutMode) {
            normalized.exitSeconds = exitSecondsP.value;
        }

        const payload = {};
        const compareAndAdd = (key) => {
            if (!sameValue(snapshot[key], normalized[key])) {
                payload[key] = normalized[key];
            }
        };

        compareAndAdd('sessionName');
        compareAndAdd('capital');
        compareAndAdd('stopLossPct');
        compareAndAdd('stopLossUsd');
        compareAndAdd('minProfitPct');
        compareAndAdd('targetTakeProfitPct');
        compareAndAdd('trailingStopPct');
        compareAndAdd('trailingStartProfitPct');
        compareAndAdd('entrySeconds');
        compareAndAdd('makerTimeoutSeconds');
        compareAndAdd('autoMaxSymbols');
        compareAndAdd('autoMinScore');
        compareAndAdd('minFundingRatePct');
        compareAndAdd('breakEvenAtPct');
        if (isCounterTrend) {
            compareAndAdd('ctSortCriteria');
        } else if (!isNoTimeoutMode) {
            compareAndAdd('exitSeconds');
        }

        if (Object.keys(payload).length === 0) {
            setSuccess('Nenhuma alteração detectada para salvar.');
            return;
        }

        setSaving(true);
        try {
            await onSave(sessionId, payload, normalized);
            setSuccess('Configurações salvas com sucesso.');
        } catch (e) {
            setError(e?.message || 'Falha ao salvar alterações.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose} style={{ zIndex: 10000 }}>
            <div className="modal-content edit-bot-modal" onClick={(e) => e.stopPropagation()}>
                <div className="modal-header edit-bot-modal-header">
                    <h2 className="modal-title">
                        <FaPenToSquare />
                        <span>Editar Configurações do Bot</span>
                    </h2>
                    <button className="modal-close" onClick={onClose} aria-label="Fechar modal">
                        <FaXmark />
                    </button>
                </div>

                <div className="modal-body edit-bot-form">
                    <div className="edit-bot-help">
                        <FaCircleInfo />
                        <span>Aceita decimal com vírgula ou ponto (ex: 1,5 ou 1.5).</span>
                    </div>

                    <div className="edit-bot-grid">
                        <div className="config-field">
                            <label>Nome do Bot</label>
                            <input
                                type="text"
                                value={sessionName}
                                onChange={(e) => setSessionName(e.target.value)}
                                placeholder="Ex: Bot Binance 09:57"
                                maxLength={80}
                            />
                        </div>
                        <div className="config-field">
                            <label>Capital Base (USDT)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={capital}
                                onChange={(e) => setCapital(e.target.value)}
                                placeholder="Ex: 35"
                            />
                        </div>
                    </div>

                    <div className="edit-bot-grid">
                        <div className="config-field">
                            <label>Stop Loss Preço (%)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={stopLossPct}
                                onChange={(e) => setStopLossPct(e.target.value)}
                                placeholder="Ex: 2,0"
                            />
                        </div>
                        <div className="config-field">
                            <label>Stop Loss (USDT)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={stopLossUsd}
                                onChange={(e) => setStopLossUsd(e.target.value)}
                                placeholder="Ex: 15"
                            />
                        </div>
                    </div>

                    <div className="edit-bot-grid">
                        <div className="config-field">
                            <label>Lucro Mínimo (%)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={minProfitPct}
                                onChange={(e) => setMinProfitPct(e.target.value)}
                                placeholder="Ex: 0,15"
                            />
                        </div>
                        <div className="config-field">
                            <label>Take Profit Alvo (%)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={targetTakeProfitPct}
                                onChange={(e) => setTargetTakeProfitPct(e.target.value)}
                                placeholder="Ex: 0,50"
                            />
                        </div>
                    </div>

                    <div className="edit-bot-grid">
                        <div className="config-field">
                            <label>Break-Even em lucro (% de preço)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={breakEvenAtPct}
                                onChange={(e) => setBreakEvenAtPct(e.target.value)}
                                placeholder="Ex: 0,30"
                            />
                        </div>
                        <div className="config-field">
                        </div>
                    </div>

                    <div className="edit-bot-grid">
                        <div className="config-field">
                            <label>Trailing Stop (% do preço)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={trailingStopPct}
                                onChange={(e) => setTrailingStopPct(e.target.value)}
                                placeholder="Ex: 1,5"
                            />
                        </div>
                        <div className="config-field">
                            <label>Ativar Trailing após (% do preço)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={trailingStartProfitPct}
                                onChange={(e) => setTrailingStartProfitPct(e.target.value)}
                                placeholder="Ex: 3"
                            />
                        </div>
                    </div>

                    <div className="edit-bot-grid">
                        <div className="config-field">
                            <label>Tempo Entrada (s)</label>
                            <input
                                type="text"
                                inputMode="numeric"
                                value={entrySeconds}
                                onChange={(e) => setEntrySeconds(e.target.value)}
                                placeholder="Ex: 30"
                            />
                        </div>
                        {!isNoTimeoutMode && (
                            <div className="config-field">
                                <label>Tempo Saída (s)</label>
                                <input
                                    type="text"
                                    inputMode="numeric"
                                    value={exitSeconds}
                                    onChange={(e) => setExitSeconds(e.target.value)}
                                    placeholder="Ex: 30"
                                />
                            </div>
                        )}
                    </div>

                    <div className="edit-bot-grid">
                        <div className="config-field">
                            <label>Timeout Maker (s)</label>
                            <input
                                type="text"
                                inputMode="numeric"
                                value={makerTimeoutSeconds}
                                onChange={(e) => setMakerTimeoutSeconds(e.target.value)}
                                placeholder="Ex: 8"
                            />
                        </div>
                        <div className="config-field">
                            <label>Max Símbolos</label>
                            <input
                                type="text"
                                inputMode="numeric"
                                value={autoMaxSymbols}
                                onChange={(e) => setAutoMaxSymbols(e.target.value)}
                                placeholder="Ex: 8"
                            />
                        </div>
                    </div>

                    <div className="edit-bot-grid">
                        <div className="config-field">
                            <label>Score Mínimo</label>
                            <input
                                type="text"
                                inputMode="numeric"
                                value={autoMinScore}
                                onChange={(e) => setAutoMinScore(e.target.value)}
                                placeholder="Ex: 50"
                            />
                        </div>
                        <div className="config-field">
                            <label>Funding Minimo (%)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                value={minFundingRatePct}
                                onChange={(e) => setMinFundingRatePct(e.target.value)}
                                placeholder="Ex: 0,12"
                            />
                        </div>
                    </div>

                    {isCounterTrend && (
                        <div className="config-field">
                            <label>
                                <FaFilter />
                                <span>Critério de Seleção</span>
                            </label>
                            <div className="edit-bot-criteria">
                                {[
                                    { value: 'score', label: 'Score', icon: <FaShieldHalved /> },
                                    { value: 'funding_rate', label: 'Funding Rate', icon: <FaChartLine /> },
                                ].map((opt) => (
                                    <button
                                        key={opt.value}
                                        type="button"
                                        className={`edit-bot-criteria-btn${ctSortCriteria === opt.value ? ' active' : ''}`}
                                        onClick={() => setCtSortCriteria(opt.value)}
                                    >
                                        {opt.icon}
                                        <span>{opt.label}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="paper-error edit-bot-feedback">
                            <FaTriangleExclamation />
                            <span>{error}</span>
                        </div>
                    )}
                    {success && (
                        <div className="edit-bot-success edit-bot-feedback">
                            <FaCircleCheck />
                            <span>{success}</span>
                        </div>
                    )}
                </div>

                <div className="modal-footer edit-bot-actions">
                    <button className="session-cancel-btn" onClick={onClose} disabled={saving}>
                        Cancelar
                    </button>
                    <button className="session-save-btn" onClick={handleSave} disabled={saving}>
                        <FaFloppyDisk />
                        <span>{saving ? 'Salvando...' : 'Salvar Alterações'}</span>
                    </button>
                </div>
            </div>
        </div>
    );
}
