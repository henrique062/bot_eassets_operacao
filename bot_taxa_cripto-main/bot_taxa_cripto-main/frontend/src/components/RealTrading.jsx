import { useState, useEffect, useMemo } from 'react';
import {
    FaArrowRotateLeft,
    FaArrowTrendDown,
    FaArrowTrendUp,
    FaBolt,
    FaBullseye,
    FaChartLine,
    FaChevronDown,
    FaCircleCheck,
    FaClock,
    FaFloppyDisk,
    FaLightbulb,
    FaPen,
    FaPlay,
    FaRocket,
    FaShieldHalved,
    FaTriangleExclamation,
    FaTrophy,
    FaXmark,
} from 'react-icons/fa6';
import { startReal, fetchFundingRates, fetchStrategies, saveStrategy } from '../services/api';

const PRESET_STRATEGIES = [
    {
        // Baseada nos trades CT mais lucrativos do período (win rate 88.9%, PF 104.6)
        // Funding rate criterion + trailing otimizado + break-even 0.3%
        id: 'ct_precisa',
        name: 'CT Precisa',
        icon: FaArrowRotateLeft,
        description: 'Contra-tendência com stops otimizados — 5x, funding extremo (≥0.15%), trailing 0.5% após 1.3%',
        badge: 'Recomendada',
        badgeClass: 'preset-badge--recommended',
        config: {
            operationMode: 'counter_trend',
            ctSortCriteria: 'funding_rate',
            autoDirection: 'both',
            autoMaxSymbols: 3,
            autoMinScore: 85,
            leverage: 5,
            capital: 25,
            feeType: 'maker',
            entrySeconds: 15,
            makerTimeout: 8,
            stopLossPct: '',
            stopLossUsd: '3',
            trailingStopPct: '0.5',
            trailingStartProfitPct: '1.3',
            breakEvenAtPct: '0.3',
            partialTpPct: '1.0',
            partialTpSize: '50',
            targetTakeProfitPct: '',
            minProfitPct: '',
        },
    },
    {
        // CT com mais slots e critério de score — para diversificar entre moedas bem ranqueadas
        id: 'ct_balanceada',
        name: 'CT Balanceada',
        icon: FaArrowRotateLeft,
        description: 'Contra-tendência por score CT — 10x, 4 moedas, trailing 0.5% após 1.0%',
        badge: 'Popular',
        badgeClass: 'preset-badge--popular',
        config: {
            operationMode: 'counter_trend',
            ctSortCriteria: 'score',
            autoDirection: 'both',
            autoMaxSymbols: 4,
            autoMinScore: 80,
            leverage: 10,
            capital: 25,
            feeType: 'maker',
            entrySeconds: 10,
            makerTimeout: 8,
            stopLossPct: '',
            stopLossUsd: '2',
            trailingStopPct: '0.5',
            trailingStartProfitPct: '1.0',
            breakEvenAtPct: '0.3',
            partialTpPct: '1.0',
            partialTpSize: '50',
            targetTakeProfitPct: '',
            minProfitPct: '',
        },
    },
    {
        // Coleta de taxa sem alavancagem — apenas moedas com score ≥82 (próximo do máximo 85)
        // Filtro mais rígido reduz perdas de preço que destroem o funding coletado
        id: 'coleta_segura',
        name: 'Coleta Segura',
        icon: FaShieldHalved,
        description: 'Coleta de funding sem alavancagem — apenas score ≥82, TP 0.30%, SL 1%',
        badge: 'Conservadora',
        badgeClass: 'preset-badge--expert',
        config: {
            operationMode: 'auto_strongest',
            autoDirection: 'both',
            autoMaxSymbols: 3,
            autoMinScore: 82,
            autoWindowMinutes: 60,
            leverage: 1,
            capital: 25,
            feeType: 'maker',
            entrySeconds: 20,
            exitSeconds: 30,
            makerTimeout: 8,
            stopLossPct: '1.0',
            stopLossUsd: '',
            targetTakeProfitPct: '0.30',
            minProfitPct: '0.08',
            trailingStopPct: '',
            trailingStartProfitPct: '',
            breakEvenAtPct: '',
            partialTpPct: '',
            partialTpSize: '50',
        },
    },
    {
        // Entrada precisa próxima ao vencimento — janela curta de 30min, 2x leverage
        id: 'coleta_expirando',
        name: 'Coleta Expirando',
        icon: FaClock,
        description: 'Foco em fundings expirando em 30min — 2x leverage, score ≥80, TP 0.25%',
        badge: 'Especialista',
        badgeClass: 'preset-badge--expert',
        config: {
            operationMode: 'auto_expiring',
            autoDirection: 'both',
            autoMaxSymbols: 3,
            autoMinScore: 80,
            autoWindowMinutes: 30,
            leverage: 2,
            capital: 25,
            feeType: 'maker',
            entrySeconds: 20,
            exitSeconds: 35,
            makerTimeout: 8,
            stopLossPct: '1.0',
            stopLossUsd: '',
            targetTakeProfitPct: '0.25',
            minProfitPct: '0.08',
            trailingStopPct: '',
            trailingStartProfitPct: '',
            breakEvenAtPct: '',
            partialTpPct: '',
            partialTpSize: '50',
        },
    },
];

const loadLocalNum = (key, def) => { const v = localStorage.getItem('real_' + key); return v !== null ? Number(v) : def; };
const loadLocalStr = (key, def) => { const v = localStorage.getItem('real_' + key); return v !== null ? v : def; };
const normalizeSeconds = (value, fallback = 30) => {
    let parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    parsed = Math.trunc(parsed);

    // Compatibilidade com configs antigas em milissegundos (ex.: 70000ms -> 70s)
    if (parsed > 32767 && parsed % 1000 === 0) {
        const asSeconds = parsed / 1000;
        if (Number.isInteger(asSeconds)) parsed = asSeconds;
    }

    return Math.max(1, Math.min(300, parsed));
};
const normalizeMakerTimeout = (value, fallback = 8) => {
    let parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    parsed = Math.trunc(parsed);

    // Motivo: aceitar payload legado em ms e alinhar novo teto de timeout maker (900s).
    if (parsed > 900 && parsed % 1000 === 0) {
        const asSeconds = parsed / 1000;
        if (Number.isInteger(asSeconds)) parsed = asSeconds;
    }

    return Math.max(2, Math.min(900, parsed));
};

export default function RealTrading({ exchange, onSessionCreated, prefilledConfig }) {
    const [selectedSymbols, setSelectedSymbols] = useState(() => {
        try { const v = localStorage.getItem('real_symbols'); return v ? JSON.parse(v) : []; } catch(e) { return []; }
    });
    const [sessionName, setSessionName] = useState('');
    const [customSymbolInput, setCustomSymbolInput] = useState('');
    const [formCollapsed, setFormCollapsed] = useState(true);
    const [symbolsCollapsed, setSymbolsCollapsed] = useState(true);
    const [operationMode, setOperationMode] = useState(() => loadLocalStr('operationMode', 'auto_expiring'));
    const [autoDirection, setAutoDirection] = useState(() => loadLocalStr('autoDirection', 'both'));
    const [autoMaxSymbols, setAutoMaxSymbols] = useState(() => loadLocalNum('autoMaxSymbols', 8));
    const [autoMinScore, setAutoMinScore] = useState(() => loadLocalNum('autoMinScore', 50));
    // Motivo: filtro minimo de funding (%) configuravel na abertura do bot.
    const [minFundingRatePct, setMinFundingRatePct] = useState(() => loadLocalNum('minFundingRatePct', 0.001));
    const [autoWindowMinutes, setAutoWindowMinutes] = useState(() => loadLocalNum('autoWindowMinutes', 60));
    const [capitalInput, setCapitalInput] = useState(() => loadLocalNum('capitalInput', 1000));
    const [leverageInput, setLeverageInput] = useState(() => loadLocalNum('leverageInput', 1));
    const [feeInput, setFeeInput] = useState(() => loadLocalStr('feeInput', 'maker'));
    const [entrySeconds, setEntrySeconds] = useState(() => normalizeSeconds(loadLocalNum('entrySeconds', 30), 30));
    const [exitSeconds, setExitSeconds] = useState(() => normalizeSeconds(loadLocalNum('exitSeconds', 30), 30));
    const [makerTimeout, setMakerTimeout] = useState(() => normalizeMakerTimeout(loadLocalNum('makerTimeout', 8), 8));
    const [stopLossPct, setStopLossPct] = useState(() => loadLocalStr('stopLossPct', '1.5'));
    const [stopLossUsd, setStopLossUsd] = useState(() => loadLocalStr('stopLossUsd', ''));
    const [minProfitPct, setMinProfitPct] = useState(() => loadLocalStr('minProfitPct', '0.15'));
    const [targetTakeProfitPct, setTargetTakeProfitPct] = useState(() => loadLocalStr('targetTakeProfitPct', ''));
    const [trailingStopPct, setTrailingStopPct] = useState(() => loadLocalStr('trailingStopPct', ''));
    const [trailingStartProfitPct, setTrailingStartProfitPct] = useState(() => loadLocalStr('trailingStartProfitPct', ''));
    const [breakEvenAtPct, setBreakEvenAtPct] = useState(() => loadLocalStr('breakEvenAtPct', ''));
    const [partialTpPct, setPartialTpPct] = useState(() => loadLocalStr('partialTpPct', ''));
    const [partialTpSize, setPartialTpSize] = useState(() => loadLocalStr('partialTpSize', '50'));
    const [ctSortCriteria, setCtSortCriteria] = useState(() => loadLocalStr('ctSortCriteria', 'score'));
    const [loading, setLoading] = useState(false);
    const [topSymbols, setTopSymbols] = useState([]);
    const [fundingUniverse, setFundingUniverse] = useState([]);
    const [error, setError] = useState('');
    const [savedStrategies, setSavedStrategies] = useState([]);
    const [selectedPreset, setSelectedPreset] = useState(null);
    const [showSaveInput, setShowSaveInput] = useState(false);
    const [saveNameInput, setSaveNameInput] = useState('');
    const [savingStrategy, setSavingStrategy] = useState(false);
    const [saveFeedback, setSaveFeedback] = useState(null); // { type: 'success'|'error', msg: string }

    useEffect(() => {
        fetchFundingRates(exchange, '', 'score', 'desc').then(res => {
            const universe = res.data || [];
            setFundingUniverse(universe);
            const top = (res.data || [])
                .filter(r => r.scoreData?.shouldOpen && (r.scoreData?.confidence === 'FORTE' || r.scoreData?.confidence === 'MODERADO'))
                .slice(0, 12)
                .map(r => ({
                    symbol: r.symbol,
                    score: r.scoreData?.score || 0,
                    confidence: r.scoreData?.confidence || '',
                    signal: r.scoreData?.signal || '',
                    fr: r.fundingRatePercent,
                    interval: r.fundingInterval || 8,
                }));
            setTopSymbols(top);
        }).catch(console.error);
    }, [exchange]);

    // Carrega estratégias salvas
    useEffect(() => {
        fetchStrategies().then(res => setSavedStrategies(res.data || [])).catch(() => {});
    }, []);

    // Aplica config pré-preenchida (vinda de "Copiar Estratégia")
    useEffect(() => {
        if (!prefilledConfig) return;
        applyConfig(prefilledConfig);
        setFormCollapsed(false);
    }, [prefilledConfig]);

    const applyConfig = (cfg) => {
        if (!cfg) return;
        setOperationMode(cfg.operationMode || 'auto_expiring');
        setAutoDirection(cfg.autoDirection || 'both');
        setAutoMaxSymbols(cfg.autoMaxSymbols ?? 8);
        setAutoMinScore(cfg.autoMinScore ?? 50);
        setMinFundingRatePct(cfg.minFundingRatePct ?? cfg.min_funding_rate_pct ?? 0.001);
        setAutoWindowMinutes(cfg.autoWindowMinutes ?? 60);
        setSelectedSymbols(cfg.symbols || []);
        setCapitalInput(parseFloat(cfg.capital) || 1000);
        setLeverageInput(cfg.leverage || 1);
        setFeeInput(cfg.feeType || 'maker');
        setEntrySeconds(normalizeSeconds(cfg.entrySeconds ?? 30, 30));
        setExitSeconds(normalizeSeconds(cfg.exitSeconds ?? 30, 30));
        setMakerTimeout(normalizeMakerTimeout(cfg.makerTimeout ?? 8, 8));
        setStopLossPct(cfg.stopLossPct != null ? String(cfg.stopLossPct) : '');
        setStopLossUsd(cfg.stopLossUsd != null ? String(cfg.stopLossUsd) : '');
        setMinProfitPct(cfg.minProfitPct != null ? String(cfg.minProfitPct) : '');
        setTargetTakeProfitPct(cfg.targetTakeProfitPct != null ? String(cfg.targetTakeProfitPct) : '');
        setTrailingStopPct(cfg.trailingStopPct != null ? String(cfg.trailingStopPct) : '');
        setTrailingStartProfitPct(cfg.trailingStartProfitPct != null ? String(cfg.trailingStartProfitPct) : '');
        setBreakEvenAtPct(cfg.breakEvenAtPct != null ? String(cfg.breakEvenAtPct) : '');
        setPartialTpPct(cfg.partialTpPct != null ? String(cfg.partialTpPct) : '');
        setPartialTpSize(cfg.partialTpSize != null ? String(cfg.partialTpSize) : '50');
        if (cfg.ctSortCriteria) setCtSortCriteria(cfg.ctSortCriteria);
    };

    const handleSelectPreset = (preset) => {
        setSelectedPreset(preset.id);
        applyConfig(preset.config);
        setFormCollapsed(false);
    };

    const handleSaveStrategy = async () => {
        if (!saveNameInput.trim()) return;
        setSavingStrategy(true);
        setSaveFeedback(null);
        try {
            const safeEntrySeconds = normalizeSeconds(entrySeconds, 30);
            const safeExitSeconds = normalizeSeconds(exitSeconds, 30);
            const safeMakerTimeout = normalizeMakerTimeout(makerTimeout, 8);
            // Motivo: modos pós-virada não usam timeout por tempo.
            const isNoTimeoutMode = operationMode === 'counter_trend' || operationMode === 'post_funding_follow';
            const config = {
                operationMode,
                autoDirection,
                autoMaxSymbols,
                autoMinScore,
                minFundingRatePct,
                autoWindowMinutes,
                leverage: leverageInput,
                feeType: feeInput,
                entrySeconds: safeEntrySeconds,
                makerTimeout: safeMakerTimeout,
                stopLossPct: stopLossPct !== '' ? parseFloat(stopLossPct) : null,
                stopLossUsd: stopLossUsd !== '' ? parseFloat(stopLossUsd) : null,
                minProfitPct: minProfitPct !== '' ? parseFloat(minProfitPct) : null,
                targetTakeProfitPct: targetTakeProfitPct !== '' ? parseFloat(targetTakeProfitPct) : null,
                trailingStopPct: trailingStopPct !== '' ? parseFloat(trailingStopPct) : null,
                trailingStartProfitPct: trailingStartProfitPct !== '' ? parseFloat(trailingStartProfitPct) : null,
                breakEvenAtPct: breakEvenAtPct !== '' ? parseFloat(breakEvenAtPct) : null,
                partialTpPct: partialTpPct !== '' ? parseFloat(partialTpPct) : null,
                partialTpSize: partialTpSize !== '' ? parseFloat(partialTpSize) : 50,
            };
            if (!isNoTimeoutMode) {
                config.exitSeconds = safeExitSeconds;
            }
            await saveStrategy(saveNameInput.trim(), config);
            setSaveFeedback({ type: 'success', msg: 'Estratégia salva com sucesso!' });
            setSaveNameInput('');
            setShowSaveInput(false);
            // Recarrega a lista de estratégias salvas
            fetchStrategies().then(res => setSavedStrategies(res.data || [])).catch(() => {});
        } catch (e) {
            setSaveFeedback({ type: 'error', msg: e.message || 'Erro ao salvar estratégia' });
        }
        setSavingStrategy(false);
        // Limpa o feedback após 4s
        setTimeout(() => setSaveFeedback(null), 4000);
    };

    const normalizeSymbol = rawSymbol => {
        const clean = (rawSymbol || '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
        if (!clean) return '';
        return clean.endsWith('USDT') ? clean : `${clean}USDT`;
    };

    const addSymbol = sym => {
        const normalized = normalizeSymbol(sym);
        if (!normalized) return;
        if (!selectedSymbols.includes(normalized)) {
            setSelectedSymbols(prev => [...prev, normalized]);
        }
    };
    const removeSymbol = sym => setSelectedSymbols(prev => prev.filter(s => s !== sym));

    const buildAutoStrategyKey = () => {
        return [
            exchange,
            operationMode,
            autoDirection,
            Math.max(1, Number(autoMaxSymbols) || 1),
            Number(autoMinScore || 0).toFixed(2),
            Math.max(0, Number(minFundingRatePct) || 0).toFixed(6),
            Math.max(5, Number(autoWindowMinutes) || 60),
        ].join('|');
    };

    const autoPreviewSymbols = useMemo(() => {
        if (!Array.isArray(fundingUniverse) || fundingUniverse.length === 0) return [];
        if (operationMode === 'manual') return [];

        const now = Date.now();
        const minScore = Math.max(0, Math.min(100, Number(autoMinScore) || 0));
        const minFunding = Math.max(0, Number(minFundingRatePct) || 0);
        const maxCount = Math.max(1, Math.min(30, Number(autoMaxSymbols) || 1));
        const windowMs = Math.max(5, Number(autoWindowMinutes) || 60) * 60 * 1000;

        const directionAllowed = (fundingRate) => {
            const fr = Number(fundingRate || 0);
            const direction = fr > 0 ? 'SHORT' : fr < 0 ? 'LONG' : 'NEUTRO';
            if (direction === 'NEUTRO') return false;
            if (autoDirection === 'both') return true;
            if (autoDirection === 'long') return direction === 'LONG';
            if (autoDirection === 'short') return direction === 'SHORT';
            return true;
        };

        // Modo maior funding rate ou counter_trend: sem filtro de score, ordena por taxa absoluta
        if (operationMode === 'auto_highest_rate' || operationMode === 'counter_trend') {
            const filtered = fundingUniverse.filter(item => {
                const fr = Number(item?.fundingRatePercent || 0);
                if (Math.abs(fr) < minFunding) return false;
                return true; // counter_trend entra na direção oposta — não filtra por direção aqui
            });
            return [...filtered]
                .sort((a, b) => Math.abs(Number(b?.fundingRatePercent || 0)) - Math.abs(Number(a?.fundingRatePercent || 0)))
                .slice(0, maxCount)
                .map(item => normalizeSymbol(item.symbol))
                .filter(Boolean);
        }

        const filtered = fundingUniverse.filter(item => {
            const score = Number(item?.scoreData?.score || 0);
            const fr = Number(item?.fundingRatePercent || 0);
            if (Math.abs(fr) < minFunding) return false;
            if (!item?.scoreData?.shouldOpen) return false;
            if (score < minScore) return false;
            if (!directionAllowed(item.fundingRate)) return false;

            if (operationMode === 'auto_expiring') {
                const nextFunding = Number(item.nextFundingTime || 0);
                if (!nextFunding) return false;
                const msLeft = nextFunding - now;
                return msLeft > 0 && msLeft <= windowMs;
            }

            return true;
        });

        const sorted = [...filtered].sort((a, b) => {
            const scoreA = Number(a?.scoreData?.score || 0);
            const scoreB = Number(b?.scoreData?.score || 0);
            const absFa = Math.abs(Number(a?.fundingRatePercent || 0));
            const absFb = Math.abs(Number(b?.fundingRatePercent || 0));
            const leftA = Number(a?.nextFundingTime || 0) - now;
            const leftB = Number(b?.nextFundingTime || 0) - now;

            if (operationMode === 'auto_expiring') {
                if (leftA !== leftB) return leftA - leftB;
                if (scoreA !== scoreB) return scoreB - scoreA;
                return absFb - absFa;
            }

            if (scoreA !== scoreB) return scoreB - scoreA;
            if (absFa !== absFb) return absFb - absFa;
            return leftA - leftB;
        });

        return sorted
            .slice(0, maxCount)
            .map(item => normalizeSymbol(item.symbol))
            .filter(Boolean);
    }, [
        fundingUniverse,
        operationMode,
        autoDirection,
        autoMaxSymbols,
        autoMinScore,
        minFundingRatePct,
        autoWindowMinutes,
    ]);

    const handleAddCustomSymbol = () => {
        const normalized = normalizeSymbol(customSymbolInput);
        if (!normalized) {
            setError('Digite um símbolo válido. Ex: BTC ou BTCUSDT.');
            return;
        }
        if (selectedSymbols.includes(normalized)) {
            setError(`O símbolo ${normalized} já foi adicionado.`);
            return;
        }
        addSymbol(normalized);
        setCustomSymbolInput('');
        setError('');
    };

    const handleCreate = async () => {
        const isManualMode = operationMode === 'manual';
        const strategySymbols = isManualMode ? selectedSymbols : autoPreviewSymbols;
        if (isManualMode && !strategySymbols.length) {
            setError('Selecione pelo menos um símbolo no modo manual.');
            return;
        }
        setError('');
        setLoading(true);
        try {
            const isCounterTrendMode = operationMode === 'counter_trend';
            // Motivo: modos pós-virada não usam timeout por tempo.
            const isNoTimeoutMode = isCounterTrendMode || operationMode === 'post_funding_follow';
            const safeEntrySeconds = normalizeSeconds(entrySeconds, 30);
            const safeExitSeconds = normalizeSeconds(exitSeconds, 30);
            const safeMakerTimeout = normalizeMakerTimeout(makerTimeout, 8);
            // Motivo: garantir range valido para filtro minimo de funding no payload.
            const safeMinFundingRatePct = Math.max(0, Math.min(5, Number(minFundingRatePct) || 0));
            const config = {
                sessionName: sessionName || `Bot ${exchange.charAt(0).toUpperCase() + exchange.slice(1)} ${new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`,
                symbols: strategySymbols,
                operationMode,
                autoMode: !isManualMode,
                autoDirection,
                autoMaxSymbols: Math.max(1, Number(autoMaxSymbols) || 1),
                autoMinScore: Number(autoMinScore) || 0,
                minFundingRatePct: safeMinFundingRatePct,
                autoWindowMinutes: Math.max(5, Number(autoWindowMinutes) || 60),
                preselectedSymbols: strategySymbols,
                preselectedKey: buildAutoStrategyKey(),
                capital: capitalInput,
                leverage: leverageInput,
                feeType: feeInput,
                entrySeconds: safeEntrySeconds,
                makerTimeout: safeMakerTimeout,
                stopLossPct: stopLossPct !== '' ? parseFloat(stopLossPct) : null,
                stopLossUsd: stopLossUsd !== '' ? parseFloat(stopLossUsd) : null,
                minProfitPct: minProfitPct !== '' ? parseFloat(minProfitPct) : null,
                targetTakeProfitPct: targetTakeProfitPct !== '' ? parseFloat(targetTakeProfitPct) : null,
                trailingStopPct: trailingStopPct !== '' ? parseFloat(trailingStopPct) : null,
                trailingStartProfitPct: trailingStartProfitPct !== '' ? parseFloat(trailingStartProfitPct) : null,
                breakEvenAtPct: breakEvenAtPct !== '' ? parseFloat(breakEvenAtPct) : null,
                partialTpPct: partialTpPct !== '' ? parseFloat(partialTpPct) : null,
                partialTpSize: partialTpSize !== '' ? parseFloat(partialTpSize) : 50,
                ctSortCriteria,
                presetName: selectedPreset || null,
            };
            if (!isNoTimeoutMode) {
                config.exitSeconds = safeExitSeconds;
            }
            // Salva no localStorage as configs (exceto o reset do form de sucesso abaixo)
            localStorage.setItem('real_symbols', JSON.stringify(strategySymbols));
            localStorage.setItem('real_operationMode', operationMode);
            localStorage.setItem('real_autoDirection', autoDirection);
            localStorage.setItem('real_autoMaxSymbols', autoMaxSymbols);
            localStorage.setItem('real_autoMinScore', autoMinScore);
            localStorage.setItem('real_minFundingRatePct', safeMinFundingRatePct);
            localStorage.setItem('real_autoWindowMinutes', autoWindowMinutes);
            localStorage.setItem('real_capitalInput', capitalInput);
            localStorage.setItem('real_leverageInput', leverageInput);
            localStorage.setItem('real_feeInput', feeInput);
            localStorage.setItem('real_entrySeconds', safeEntrySeconds);
            if (!isNoTimeoutMode) {
                localStorage.setItem('real_exitSeconds', safeExitSeconds);
            }
            localStorage.setItem('real_makerTimeout', safeMakerTimeout);
            localStorage.setItem('real_stopLossPct', stopLossPct);
            localStorage.setItem('real_stopLossUsd', stopLossUsd);
            localStorage.setItem('real_minProfitPct', minProfitPct);
            localStorage.setItem('real_targetTakeProfitPct', targetTakeProfitPct);
            localStorage.setItem('real_trailingStopPct', trailingStopPct);
            localStorage.setItem('real_trailingStartProfitPct', trailingStartProfitPct);
            localStorage.setItem('real_breakEvenAtPct', breakEvenAtPct);
            localStorage.setItem('real_partialTpPct', partialTpPct);
            localStorage.setItem('real_partialTpSize', partialTpSize);
            localStorage.setItem('real_ctSortCriteria', ctSortCriteria);

            await startReal(exchange, config);
            
            // Notification / UI success logic
            setSessionName('');
            setCustomSymbolInput('');
            setFormCollapsed(true);
            setSymbolsCollapsed(true);
            setEntrySeconds(30);
            setExitSeconds(30);
            setMakerTimeout(8);
            setStopLossPct('1.5');
            setStopLossUsd('');
            setMinProfitPct('0.15');
            setTargetTakeProfitPct('');
            setTrailingStopPct('');
            setTrailingStartProfitPct('');
            onSessionCreated?.();
        } catch (e) {
            setError(e.message);
        }
        setLoading(false);
    };

    const handlePrimaryAction = () => {
        if (formCollapsed) {
            setFormCollapsed(false);
            return;
        }
        handleCreate();
    };

    const isManualMode = operationMode === 'manual';
    const isCounterTrend = operationMode === 'counter_trend';
    // Motivo: distinguir o novo modo de entrada pós-virada na direção recomendada do funding.
    const isPostFundingFollow = operationMode === 'post_funding_follow';
    const effectiveSymbols = isManualMode ? selectedSymbols : autoPreviewSymbols;
    const capitalPerSymbol = effectiveSymbols.length > 0 ? (capitalInput / effectiveSymbols.length) : capitalInput;
    const canStartWhenExpanded = isManualMode ? selectedSymbols.length > 0 : true;

    return (
        <div className="paper-create-panel">
            <div className="paper-create-header">
                <h2 style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                    <FaBolt />
                    Novo Bot Conta Real
                </h2>
            </div>

            {formCollapsed ? (
                <div className="paper-create-collapsed-note">
                    Clique em <strong>Expandir para configurar estratégia</strong>.
                </div>
            ) : (
                <>
                    {/* Estratégias salvas */}
                    {savedStrategies.length > 0 && (
                        <div className="config-field" style={{ marginBottom: '4px' }}>
                            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                <FaFloppyDisk />
                                Carregar Estratégia Salva
                            </label>
                            <select
                                defaultValue=""
                                onChange={e => {
                                    const selected = savedStrategies.find(s => String(s.id) === e.target.value);
                                    if (selected) {
                                        applyConfig(selected.config);
                                        setSelectedPreset(null);
                                    }
                                    e.target.value = '';
                                }}
                            >
                                <option value="" disabled>— Selecionar estratégia salva —</option>
                                {savedStrategies.map(s => (
                                    <option key={s.id} value={s.id}>{s.name}</option>
                                ))}
                            </select>
                            <span className="config-hint">Ao selecionar, os campos serão preenchidos automaticamente</span>
                        </div>
                    )}

                    {/* Estratégias pré-definidas */}
                    <div className="preset-strategies-section">
                        <span className="preset-strategies-title">Estratégias Recomendadas</span>
                        <div className="preset-strategies-grid">
                            {PRESET_STRATEGIES.map(preset => (
                                <button
                                    key={preset.id}
                                    type="button"
                                    className={`preset-card ${selectedPreset === preset.id ? 'selected' : ''}`}
                                    onClick={() => handleSelectPreset(preset)}
                                    aria-pressed={selectedPreset === preset.id}
                                >
                                    <div className="preset-card-header">
                                        <span className="preset-card-name">
                                            {preset.icon ? <preset.icon className="preset-card-icon" /> : null}
                                            <span>{preset.name}</span>
                                        </span>
                                        <span className={`preset-badge ${preset.badgeClass}`}>{preset.badge}</span>
                                    </div>
                                    <p className="preset-card-desc">{preset.description}</p>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Nome da sessão */}
                    <div className="config-field paper-name-field">
                        <label>Nome do Bot (opcional)</label>
                        <input
                            type="text"
                            value={sessionName}
                            onChange={e => setSessionName(e.target.value)}
                            placeholder="Ex: AWEUSDT Sniping 4h"
                            maxLength={80}
                        />
                    </div>

                    {/* Estratégia pronta */}
                    <div className="config-section-title">
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <FaBullseye />
                            Estratégia Pronta
                        </span>
                    </div>
                    <div className="config-row paper-strategy-row">
                        <div className="config-field" style={{ minWidth: '100%', flex: 'none' }}>
                            <label>Modo de Operação</label>
                            <div className="op-mode-grid">
                                {[
                                    { value: 'auto_strongest', label: 'Mais Fortes', icon: FaTrophy, desc: 'Maior score' },
                                    { value: 'auto_highest_rate', label: 'Maior Rate', icon: FaChartLine, desc: 'Maior funding' },
                                    { value: 'auto_expiring', label: 'Expirando', icon: FaClock, desc: 'Vencendo em 1h' },
                                    { value: 'post_funding_follow', label: 'Pós Funding', icon: FaRocket, desc: 'Pós-virada favor' },
                                    { value: 'counter_trend', label: 'Contra-Tendência', icon: FaArrowRotateLeft, desc: 'Pós-virada' },
                                    { value: 'manual', label: 'Manual', icon: FaPen, desc: 'Selecionar moedas' },
                                ].map(m => {
                                    const ModeIcon = m.icon;
                                    return (
                                        <button
                                            key={m.value}
                                            type="button"
                                            className={`op-mode-btn${operationMode === m.value ? ' active' : ''}${m.value === 'counter_trend' ? ' ct' : ''}`}
                                            onClick={() => setOperationMode(m.value)}
                                        >
                                            <span className="op-mode-icon"><ModeIcon /></span>
                                            <span className="op-mode-label">{m.label}</span>
                                            <span className="op-mode-desc">{m.desc}</span>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                        {isCounterTrend && (
                            <div className="config-hint" style={{ gridColumn: '1 / -1', background: 'rgba(255,200,0,0.08)', border: '1px solid rgba(255,200,0,0.25)', borderRadius: '6px', padding: '8px 12px', color: 'var(--text-secondary)', fontSize: '0.82rem', lineHeight: '1.5' }}>
                                <strong>Estratégia Contra-Tendência:</strong> Entra na direção <em>oposta</em> ao funding anterior, logo após a virada do ciclo.
                                Se o funding era <strong>negativo</strong> (muitos longs abertos), o bot abre <strong>SHORT</strong> na virada. Se era <strong>positivo</strong> (muitos shorts), abre <strong>LONG</strong>.
                                Selecione os símbolos manualmente e configure Take Profit e Stop Loss.
                            </div>
                        )}
                        {isPostFundingFollow && (
                            <div className="config-hint" style={{ gridColumn: '1 / -1', background: 'rgba(34,197,94,0.10)', border: '1px solid rgba(34,197,94,0.30)', borderRadius: '6px', padding: '8px 12px', color: 'var(--text-secondary)', fontSize: '0.82rem', lineHeight: '1.5' }}>
                                <strong>Estratégia Pós-Funding (Favor):</strong> Entra após a virada, mas mantendo a direção recomendada do funding.
                                Funding <strong>positivo</strong> mantém entrada <strong>SHORT</strong>; funding <strong>negativo</strong> mantém entrada <strong>LONG</strong>.
                                Nesse modo, <strong>entrySeconds</strong> é o delay após a virada e a posição segue sem timeout por tempo.
                            </div>
                        )}
                        {isCounterTrend && (
                            <div className="config-field" style={{ minWidth: '200px' }}>
                                <label>Critério de Seleção</label>
                                <div className="ct-sort-toggle">
                                    <button
                                        type="button"
                                        className={`ct-sort-btn${ctSortCriteria === 'score' ? ' active' : ''}`}
                                        onClick={() => setCtSortCriteria('score')}
                                    >
                                        <span className="ct-sort-icon"><FaTrophy /></span>
                                        <span>Score</span>
                                    </button>
                                    <button
                                        type="button"
                                        className={`ct-sort-btn${ctSortCriteria === 'funding_rate' ? ' active' : ''}`}
                                        onClick={() => setCtSortCriteria('funding_rate')}
                                    >
                                        <span className="ct-sort-icon"><FaChartLine /></span>
                                        <span>Funding Rate</span>
                                    </button>
                                </div>
                            </div>
                        )}
                        <div className="config-field">
                            <label>Direção</label>
                            <select
                                value={autoDirection}
                                onChange={e => setAutoDirection(e.target.value)}
                            >
                                <option value="both">Long + Short</option>
                                <option value="long">Apenas Long</option>
                                <option value="short">Apenas Short</option>
                            </select>
                        </div>
                        <div className="config-field">
                            <label>Quantidade de Moedas</label>
                            <input
                                type="number"
                                value={autoMaxSymbols}
                                onChange={e => setAutoMaxSymbols(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
                                min={1}
                                max={30}
                                disabled={operationMode === 'manual'}
                            />
                        </div>
                        {operationMode !== 'auto_highest_rate' && (
                            <div className="config-field">
                                <label>Pontuação Mínima</label>
                                <input
                                    type="number"
                                    value={autoMinScore}
                                    onChange={e => setAutoMinScore(Math.max(0, Math.min(100, Number(e.target.value) || 0)))}
                                    min={0}
                                    max={100}
                                    step={1}
                                    disabled={operationMode === 'manual'}
                                />
                            </div>
                        )}
                        <div className="config-field">
                            <label>Funding Minimo (%)</label>
                            <input
                                type="number"
                                value={minFundingRatePct}
                                onChange={e => setMinFundingRatePct(Math.max(0, Math.min(5, Number(e.target.value) || 0)))}
                                min={0}
                                max={5}
                                step={0.001}
                            />
                        </div>
                        {operationMode === 'auto_expiring' && (
                            <div className="config-field">
                                <label>Janela de Expiração (min)</label>
                                <input
                                    type="number"
                                    value={autoWindowMinutes}
                                    onChange={e => setAutoWindowMinutes(Math.max(5, Math.min(240, Number(e.target.value) || 60)))}
                                    min={5}
                                    max={240}
                                />
                            </div>
                        )}
                    </div>

                    {!isManualMode && (
                        <div className="strategy-preview-block">
                            <span className="suggestions-label">Pré-seleção para início rápido ({autoPreviewSymbols.length})</span>
                            <div className="symbol-tags">
                                {autoPreviewSymbols.map(sym => (
                                    <span key={sym} className="symbol-tag">
                                        {sym.replace('USDT', '')}
                                    </span>
                                ))}
                                {!autoPreviewSymbols.length && (
                                    <span className="symbol-tag-empty">
                                        Nenhuma moeda elegível agora com os filtros atuais. O bot seguirá monitorando automaticamente.
                                    </span>
                                )}
                            </div>
                            <span className="config-hint">
                                A lista é validada com a pré-programação e atualizada durante a execução para evitar atraso no start.
                            </span>
                        </div>
                    )}

                    {/* Symbol Picker (modo manual) */}
                    {isManualMode && (
                        <div className="symbol-picker">
                            <div className="symbol-picker-header">
                                <span className="config-label">Símbolos ({selectedSymbols.length})</span>
                                <button
                                    type="button"
                                    className="symbol-picker-toggle"
                                    onClick={() => setSymbolsCollapsed(prev => !prev)}
                                    aria-expanded={!symbolsCollapsed}
                                >
                                    {symbolsCollapsed ? 'Expandir' : 'Recolher'}
                                    <span className={`symbol-picker-caret ${symbolsCollapsed ? 'collapsed' : 'expanded'}`}>
                                        <FaChevronDown />
                                    </span>
                                </button>
                            </div>

                            {symbolsCollapsed ? (
                                <div className="symbol-picker-collapsed">
                                    {selectedSymbols.slice(0, 8).map(sym => (
                                        <span key={sym} className="symbol-tag">
                                            {sym.replace('USDT', '')}
                                        </span>
                                    ))}
                                    {selectedSymbols.length > 8 && (
                                        <span className="symbol-tag symbol-tag-more">+{selectedSymbols.length - 8}</span>
                                    )}
                                    {!selectedSymbols.length && (
                                        <span className="symbol-tag-empty">Seção recolhida. Clique em Expandir para adicionar símbolos.</span>
                                    )}
                                </div>
                            ) : (
                                <div className="symbol-picker-body">
                                    <div className="symbol-custom-row">
                                        <input
                                            type="text"
                                            value={customSymbolInput}
                                            onChange={e => setCustomSymbolInput(e.target.value)}
                                            onKeyDown={e => { if (e.key === 'Enter') handleAddCustomSymbol(); }}
                                            placeholder="Adicionar qualquer moeda (ex: BTC, SOL, 1000PEPE)"
                                            maxLength={20}
                                        />
                                        <button
                                            type="button"
                                            className="symbol-custom-add"
                                            onClick={handleAddCustomSymbol}
                                            disabled={!customSymbolInput.trim()}
                                        >
                                            + Adicionar
                                        </button>
                                    </div>
                                    <span className="symbol-custom-hint">
                                        Você pode inserir qualquer moeda manualmente. Se faltar sufixo, será adicionado USDT.
                                    </span>

                                    <div className="symbol-tags">
                                        {selectedSymbols.map(sym => (
                                            <span key={sym} className="symbol-tag">
                                                {sym.replace('USDT', '')}
                                                <button className="tag-remove" onClick={() => removeSymbol(sym)} aria-label={`Remover ${sym}`}>
                                                    <FaXmark />
                                                </button>
                                            </span>
                                        ))}
                                        {!selectedSymbols.length && (
                                            <span className="symbol-tag-empty">Clique nos símbolos abaixo para selecionar</span>
                                        )}
                                    </div>

                                    <div className="symbol-suggestions">
                                        <span className="suggestions-label">
                                            <FaTrophy />
                                            Top por Score (shouldOpen = true):
                                        </span>
                                        <div className="suggestion-list">
                                            {topSymbols.map(s => (
                                                <button
                                                    key={s.symbol}
                                                    className={`suggestion-btn ${selectedSymbols.includes(s.symbol) ? 'selected' : ''} ${s.confidence === 'FORTE' ? 'forte' : 'moderado'}`}
                                                    onClick={() => selectedSymbols.includes(s.symbol) ? removeSymbol(s.symbol) : addSymbol(s.symbol)}
                                                    title={`Score: ${s.score} | Funding: ${Number(s.fr || 0).toFixed(4)}% | ${s.interval}h`}
                                                >
                                                    <span className="sugg-name">{s.symbol.replace('USDT', '')}</span>
                                                    <span className="sugg-score">{s.score}</span>
                                                    <span className={`sugg-signal ${s.signal?.includes('SHORT') ? 'short' : 'long'}`}>
                                                        {s.signal?.includes('SHORT') ? <FaArrowTrendDown /> : <FaArrowTrendUp />}
                                                    </span>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {effectiveSymbols.length > 1 && (
                        <div className="capital-split-info">
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                <FaLightbulb />
                                Capital dividido: <strong>${capitalPerSymbol.toFixed(2)}</strong> por símbolo
                            </span>
                        </div>
                    )}

                    {/* Configurações principais */}
                    <div className="config-row paper-config-row">
                        <div className="config-field">
                            <label>Capital Total ($)</label>
                            <input type="number" value={capitalInput} onChange={e => setCapitalInput(Number(e.target.value))} min={10} />
                        </div>
                        <div className="config-field">
                            <label>Alavancagem</label>
                            <select value={leverageInput} onChange={e => setLeverageInput(Number(e.target.value))}>
                                {[1, 2, 3, 5, 10, 15, 20].map(l => <option key={l} value={l}>{l}x</option>)}
                            </select>
                        </div>
                        <div className="config-field">
                            <label>Fee</label>
                            <select value={feeInput} onChange={e => setFeeInput(e.target.value)}>
                                <option value="maker">Maker (0.02%)</option>
                                <option value="taker">Taker (0.05%)</option>
                            </select>
                        </div>
                    </div>

                    {/* Timings */}
                    <div className="config-row paper-timing-row">
                        <div className="config-field">
                            <label>{(isCounterTrend || isPostFundingFollow) ? 'Delay pós-virada (s)' : 'Entrada (seg antes)'}</label>
                            <input type="number" value={entrySeconds} onChange={e => setEntrySeconds(normalizeSeconds(e.target.value, 30))} min={1} max={300} />
                        </div>
                        {!isCounterTrend && !isPostFundingFollow && (
                            <div className="config-field">
                                <label>Saída (seg depois)</label>
                                <input type="number" value={exitSeconds} onChange={e => setExitSeconds(normalizeSeconds(e.target.value, 30))} min={1} max={300} />
                            </div>
                        )}
                        <div className="config-field">
                            <label title="Tempo máximo aguardando a ordem Maker (GTX) ser preenchida antes de usar Taker (mercado)">
                                Timeout Maker (s)
                            </label>
                            <input
                                type="number"
                                value={makerTimeout}
                                onChange={e => setMakerTimeout(normalizeMakerTimeout(e.target.value, 8))}
                                min={2}
                                max={900}
                            />
                            <span className="config-hint">Espera p/ ordem maker antes de usar taker</span>
                        </div>
                    </div>

                    {/* Stop Loss e Min Profit */}
                    <div className="config-section-title">
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <FaShieldHalved />
                            Proteção de Capital (opcional)
                        </span>
                    </div>
                    <div className="config-row paper-risk-row">
                        <div className="config-field">
                            <label title="Fecha a posição se o preço se mover X% contra. Ex: 2 = fechar se -2% no preço">
                                Stop Loss preço (%)
                            </label>
                            <input
                                type="number"
                                value={stopLossPct}
                                onChange={e => setStopLossPct(e.target.value)}
                                placeholder="Ex: 2.0"
                                min={0}
                                step={0.1}
                            />
                            <span className="config-hint">Fecha se preço mover X% contra</span>
                        </div>
                        <div className="config-field">
                            <label title="Fecha se a perda total ultrapassar este valor em USD">
                                Stop Loss em USD ($)
                            </label>
                            <input
                                type="number"
                                value={stopLossUsd}
                                onChange={e => setStopLossUsd(e.target.value)}
                                placeholder="Ex: 15.00"
                                min={0}
                                step={1}
                            />
                            <span className="config-hint">Fecha se perda total superar $X</span>
                        </div>
                        <div className="config-field">
                            <label title="Coloca uma ordem Limit alvo de ganho e encerra o trade assim que for atingida.">
                                Take Profit Alvo (%)
                            </label>
                            <input
                                type="number"
                                value={targetTakeProfitPct}
                                onChange={e => setTargetTakeProfitPct(e.target.value)}
                                placeholder="Ex: 0.50"
                                min={0}
                                step={0.01}
                            />
                            <span className="config-hint">Alvo de lucro com Limit Order</span>
                        </div>
                        <div className="config-field">
                            <label title="Fecha a posição se o preço recuar X% do pico (LONG) ou subir X% do vale (SHORT). Stop dinâmico que segue o preço favorável.">
                                Trailing Stop %
                            </label>
                            <input
                                type="number"
                                value={trailingStopPct}
                                onChange={e => setTrailingStopPct(e.target.value)}
                                placeholder="Ex: 1.5"
                                min={0.1}
                                step={0.1}
                            />
                            <span className="config-hint">Stop móvel: fecha se recuar X% do preço do pico</span>
                        </div>
                        <div className="config-field">
                            <label title="Só começa a rastrear o trailing quando o preço se mover X% a favor da posição. Ex: 1 = arma trailing após +1% de preço.">
                                Ativa Trailing %
                            </label>
                            <input
                                type="number"
                                value={trailingStartProfitPct}
                                onChange={e => setTrailingStartProfitPct(e.target.value)}
                                placeholder="Ex: 1.0"
                                min={0}
                                step={0.1}
                            />
                            <span className="config-hint">Opcional: trailing só arma após +X% de preço favorável</span>
                        </div>
                        <div className="config-field">
                            <label title="Quando o lucro de preço atingir X%, o stop loss é movido para o preço de entrada (break-even). Protege capital mesmo sem atingir o trailing.">
                                Break em lucro %
                            </label>
                            <input
                                type="number"
                                value={breakEvenAtPct}
                                onChange={e => setBreakEvenAtPct(e.target.value)}
                                placeholder="Ex: 0.4"
                                min={0.1}
                                step={0.1}
                            />
                            <span className="config-hint">Opcional: move SL para entrada quando lucro atingir X%</span>
                        </div>
                        <div className="config-field">
                            <label title="Quando o lucro de preço atingir X%, fecha parcialmente a posição e continua monitorando o restante com o trailing.">
                                TP Parcial % lucro
                            </label>
                            <input
                                type="number"
                                value={partialTpPct}
                                onChange={e => setPartialTpPct(e.target.value)}
                                placeholder="Ex: 0.8"
                                min={0.1}
                                step={0.1}
                            />
                            <span className="config-hint">Opcional: fecha X% da posição ao atingir o lucro alvo</span>
                        </div>
                        <div className="config-field">
                            <label title="Percentual da posição a fechar no TP Parcial (padrão 50%).">
                                TP Parcial %
                            </label>
                            {/* Comentário de controle: permitir ajuste antecipado do tamanho do TP parcial sem depender do alvo de lucro. */}
                            <input
                                type="number"
                                value={partialTpSize}
                                onChange={e => setPartialTpSize(e.target.value)}
                                placeholder="Ex: 50"
                                min={1}
                                max={99}
                                step={1}
                            />
                            <span className="config-hint">Percentual da posição a fechar no TP parcial</span>
                        </div>
                        <div className="config-field">
                            <label title="Só fecha a posição após o funding se o lucro total for >= X%. Evita sair no negativo.">
                                Min lucro %
                            </label>
                            <input
                                type="number"
                                value={minProfitPct}
                                onChange={e => setMinProfitPct(e.target.value)}
                                placeholder="Ex: 0.05"
                                min={0}
                                step={0.01}
                            />
                            <span className="config-hint">Aguarda atingir X% de lucro p/ fechar</span>
                        </div>
                    </div>

                    {/* Salvar Estratégia */}
                    <div className="save-strategy-section">
                        {!showSaveInput ? (
                            <button
                                type="button"
                                className="save-strategy-btn"
                                onClick={() => { setShowSaveInput(true); setSaveFeedback(null); }}
                                aria-label="Salvar configuração atual como estratégia"
                            >
                                <FaFloppyDisk />
                                Salvar Estratégia
                            </button>
                        ) : (
                            <div className="save-strategy-input-row">
                                <input
                                    type="text"
                                    placeholder="Nome da estratégia..."
                                    value={saveNameInput}
                                    onChange={e => setSaveNameInput(e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter') handleSaveStrategy(); if (e.key === 'Escape') setShowSaveInput(false); }}
                                    maxLength={60}
                                    autoFocus
                                    aria-label="Nome da estratégia a salvar"
                                />
                                <button
                                    type="button"
                                    className="save-strategy-confirm-btn"
                                    onClick={handleSaveStrategy}
                                    disabled={savingStrategy || !saveNameInput.trim()}
                                >
                                    {savingStrategy ? 'Salvando...' : 'Salvar'}
                                </button>
                                <button
                                    type="button"
                                    className="save-strategy-cancel-btn"
                                    onClick={() => { setShowSaveInput(false); setSaveNameInput(''); }}
                                >
                                    Cancelar
                                </button>
                            </div>
                        )}
                        {saveFeedback && (
                            <span className={`save-strategy-feedback ${saveFeedback.type}`}>
                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                    {saveFeedback.type === 'success' ? <FaCircleCheck /> : <FaTriangleExclamation />}
                                    {saveFeedback.msg}
                                </span>
                            </span>
                        )}
                    </div>

                    {error && (
                        <div className="paper-error" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <FaTriangleExclamation />
                            {error}
                        </div>
                    )}
                </>
            )}

            <div className="paper-actions">
                <button
                    className="paper-start-btn"
                    onClick={handlePrimaryAction}
                    disabled={loading || (!formCollapsed && !canStartWhenExpanded)}
                >
                    {loading ? (
                        <><span className="spinner-small" /> Iniciando...</>
                    ) : formCollapsed ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                            <FaPen />
                            Expandir para configurar estratégia
                        </span>
                    ) : (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                            <FaPlay />
                            {`Iniciar Bot com ${effectiveSymbols.length} símbolo${effectiveSymbols.length !== 1 ? 's' : ''}`}
                        </span>
                    )}
                </button>
            </div>
        </div>
    );
}
