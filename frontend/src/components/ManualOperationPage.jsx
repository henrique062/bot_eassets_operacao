import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    FaArrowRotateLeft,
    FaBolt,
    FaChartLine,
    FaCircleCheck,
    FaFloppyDisk,
    FaLayerGroup,
    FaPlay,
    FaShieldHalved,
    FaTriangleExclamation,
} from 'react-icons/fa6';
import {
    fetchFundingRates,
    fetchKlines,
    fetchRealChartOperations,
    fetchUserSettings,
    startManualOperation,
    updateUserSetting,
} from '../services/api';
import TradingViewChart from './TradingViewChart';
import AdvancedTradingViewWidget from './AdvancedTradingViewWidget';
import {
    CHART_INTERVAL_OPTIONS,
    getKlineLimitForInterval,
    getRefreshMsForInterval,
    resolveChartInterval,
} from '../utils/chartIntervals';

const MANUAL_CONFIG_KEY = 'manual_operation_last_config_v1';
const MANUAL_LOCAL_KEY = 'manual_operation_last_config_v1';

function toIsoNow() {
    return new Date().toISOString();
}

function toMs(iso) {
    const ms = Date.parse(iso || '');
    return Number.isFinite(ms) ? ms : 0;
}

function toNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
}

function normalizeSymbol(raw) {
    const clean = String(raw || '')
        .trim()
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, '');
    if (!clean) return '';
    return clean.endsWith('USDT') ? clean : `${clean}USDT`;
}

function parseNullableNumber(raw) {
    const text = String(raw ?? '').trim();
    if (!text) return null;
    const parsed = Number(text.replace(',', '.'));
    return Number.isFinite(parsed) ? parsed : null;
}

function stringifyNullable(value) {
    if (value === null || value === undefined || value === '') return '';
    return String(value);
}

function getDefaultConfig() {
    return {
        symbol: 'BTCUSDT',
        direction: 'LONG',
        feeType: 'maker',
        capital: '10',
        leverage: '1',
        makerTimeout: '8',
        entryLimitPrice: '',
        stopLossPct: '',
        stopLossUsd: '',
        trailingStopPct: '1.5',
        trailingStartProfitPct: '',
        breakEvenAtPct: '',
        partialTpPct: '',
        partialTpSize: '50',
        chartInterval: '1m',
        // Motivo: o modo clássico dá mais controle visual/funcional para nossa tela.
        chartEngine: 'classic',
        updatedAt: null,
    };
}

function parseEntry(raw) {
    if (!raw || typeof raw !== 'object') return null;
    const defaults = getDefaultConfig();
    return {
        symbol: normalizeSymbol(raw.symbol) || defaults.symbol,
        direction: raw.direction === 'SHORT' ? 'SHORT' : 'LONG',
        feeType: raw.feeType === 'taker' ? 'taker' : 'maker',
        capital: stringifyNullable(raw.capital ?? defaults.capital),
        leverage: stringifyNullable(raw.leverage ?? defaults.leverage),
        makerTimeout: stringifyNullable(raw.makerTimeout ?? defaults.makerTimeout),
        entryLimitPrice: stringifyNullable(raw.entryLimitPrice),
        stopLossPct: stringifyNullable(raw.stopLossPct),
        stopLossUsd: stringifyNullable(raw.stopLossUsd),
        trailingStopPct: stringifyNullable(raw.trailingStopPct),
        trailingStartProfitPct: stringifyNullable(raw.trailingStartProfitPct),
        breakEvenAtPct: stringifyNullable(raw.breakEvenAtPct),
        partialTpPct: stringifyNullable(raw.partialTpPct),
        partialTpSize: stringifyNullable(raw.partialTpSize ?? defaults.partialTpSize),
        chartInterval: CHART_INTERVAL_OPTIONS.some(i => i.value === raw.chartInterval) ? raw.chartInterval : defaults.chartInterval,
        chartEngine: raw.chartEngine === 'advanced' ? 'advanced' : 'classic',
        updatedAt: raw.updatedAt || null,
    };
}

function readLocalPayload() {
    try {
        const parsed = JSON.parse(localStorage.getItem(MANUAL_LOCAL_KEY) || '{}');
        return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
        return {};
    }
}

function buildPayload(basePayload, exchange, entry) {
    const payload = basePayload && typeof basePayload === 'object' ? basePayload : {};
    const byExchange = payload.byExchange && typeof payload.byExchange === 'object'
        ? payload.byExchange
        : {};

    return {
        ...payload,
        byExchange: {
            ...byExchange,
            [exchange]: {
                ...entry,
                updatedAt: entry.updatedAt || toIsoNow(),
            },
        },
    };
}

function pickLatestEntry(localPayload, remotePayload, exchange) {
    const localEntry = parseEntry(localPayload?.byExchange?.[exchange]);
    const remoteEntry = parseEntry(remotePayload?.byExchange?.[exchange]);
    if (!localEntry) return remoteEntry;
    if (!remoteEntry) return localEntry;
    return toMs(remoteEntry.updatedAt) > toMs(localEntry.updatedAt) ? remoteEntry : localEntry;
}

function formatRate(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `${n >= 0 ? '+' : ''}${n.toFixed(4)}%`;
}

function formatPrice(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return '—';
    if (n >= 10000) return n.toFixed(2);
    if (n >= 1000) return n.toFixed(3);
    if (n >= 1) return n.toFixed(4);
    return n.toFixed(6);
}

function formatCountdown(targetMs, nowMs = Date.now()) {
    if (!targetMs) return '—';
    const diff = Number(targetMs) - Number(nowMs);
    if (diff <= 0) return 'Agora';
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    return `${String(h).padStart(2, '0')}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
}

function formatCompactDateTime(raw) {
    const text = String(raw || '').trim();
    if (!text) return '—';

    // Motivo: padronizar horário no painel para formato compacto DD/MM HH:MM:SS.
    const brMatch = text.match(/^(\d{2})\/(\d{2})\/(\d{2,4})\s+(\d{2}:\d{2}:\d{2})$/);
    if (brMatch) {
        const [, dd, mm, , hhmmss] = brMatch;
        return `${dd}/${mm} ${hhmmss}`;
    }

    const parsed = Date.parse(text);
    if (!Number.isFinite(parsed)) return text;
    const d = new Date(parsed);
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${dd}/${mm} ${hh}:${min}:${ss}`;
}

function formatSignedUsd(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `${n >= 0 ? '+' : '-'}$${Math.abs(n).toFixed(2)}`;
}


function formatUsd(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return '—';
    return `$${n.toFixed(n >= 100 ? 2 : 4)}`;
}


function pnlToneClass(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 'muted';
    return n >= 0 ? 'positive' : 'negative';
}

function toChartTimestamp(raw) {
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return null;
    return n > 10_000_000_000 ? Math.floor(n) : Math.floor(n * 1000);
}

export default function ManualOperationPage({ exchange = 'binance' }) {
    const [fundingRows, setFundingRows] = useState([]);
    const [ratesLoading, setRatesLoading] = useState(true);
    const [search, setSearch] = useState('');

    const [symbol, setSymbol] = useState('BTCUSDT');
    const [direction, setDirection] = useState('LONG');
    const [feeType, setFeeType] = useState('maker');
    const [capital, setCapital] = useState('10');
    const [leverage, setLeverage] = useState('1');
    const [makerTimeout, setMakerTimeout] = useState('8');
    const [entryLimitPrice, setEntryLimitPrice] = useState('');
    const [stopLossPct, setStopLossPct] = useState('');
    const [stopLossUsd, setStopLossUsd] = useState('');
    const [trailingStopPct, setTrailingStopPct] = useState('1.5');
    const [trailingStartProfitPct, setTrailingStartProfitPct] = useState('');
    const [breakEvenAtPct, setBreakEvenAtPct] = useState('');
    const [partialTpPct, setPartialTpPct] = useState('');
    const [partialTpSize, setPartialTpSize] = useState('50');

    const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT');
    const [chartInterval, setChartInterval] = useState('1m');
    const [chartEngine, setChartEngine] = useState('classic');
    const [klines, setKlines] = useState([]);
    const [klinesLoading, setKlinesLoading] = useState(false);

    const [symbolOpenPositions, setSymbolOpenPositions] = useState([]);
    const [symbolPendingEntries, setSymbolPendingEntries] = useState([]);
    const [symbolClosedOperations, setSymbolClosedOperations] = useState([]);
    const [globalOpenPositions, setGlobalOpenPositions] = useState([]);
    const [globalPendingEntries, setGlobalPendingEntries] = useState([]);
    const [globalClosedOperations, setGlobalClosedOperations] = useState([]);
    const [opsLoading, setOpsLoading] = useState(true);

    const [saveInfo, setSaveInfo] = useState('');
    const [saveError, setSaveError] = useState('');
    const [submitError, setSubmitError] = useState('');
    const [submitSuccess, setSubmitSuccess] = useState('');
    const [starting, setStarting] = useState(false);

    const [countdownNow, setCountdownNow] = useState(Date.now());

    const hydratedRef = useRef(false);
    const debounceRef = useRef(null);

    const selectedRate = useMemo(
        () => fundingRows.find(r => String(r.symbol || '').toUpperCase() === String(selectedSymbol || '').toUpperCase()) || null,
        [fundingRows, selectedSymbol],
    );

    const { apiInterval, hint: intervalHint } = resolveChartInterval(exchange, chartInterval);

    const verticalFundingLines = useMemo(() => {
        if (!selectedRate) return [];
        const nextFundingMs = Number(selectedRate.nextFundingTime || 0);
        const intervalHours = Number(selectedRate.fundingInterval || 8);
        if (!Number.isFinite(nextFundingMs) || nextFundingMs <= 0) return [];
        const prevFundingMs = nextFundingMs - Math.max(1, intervalHours) * 3600 * 1000;
        return [
            {
                time: prevFundingMs,
                color: 'rgba(245, 158, 11, 0.85)',
                label: 'Funding anterior',
                labelColor: '#f59e0b',
            },
            {
                time: nextFundingMs,
                color: 'rgba(59, 130, 246, 0.9)',
                label: 'Próximo funding',
                labelColor: '#3b82f6',
            },
        ];
    }, [selectedRate]);

    const readCurrentEntry = useCallback(() => ({
        symbol: normalizeSymbol(symbol) || 'BTCUSDT',
        direction,
        feeType,
        capital: String(capital || '10'),
        leverage: String(leverage || '1'),
        makerTimeout: String(makerTimeout || '8'),
        entryLimitPrice: String(entryLimitPrice || ''),
        stopLossPct: String(stopLossPct || ''),
        stopLossUsd: String(stopLossUsd || ''),
        trailingStopPct: String(trailingStopPct || ''),
        trailingStartProfitPct: String(trailingStartProfitPct || ''),
        breakEvenAtPct: String(breakEvenAtPct || ''),
        partialTpPct: String(partialTpPct || ''),
        partialTpSize: String(partialTpSize || '50'),
        chartInterval,
        chartEngine,
        updatedAt: toIsoNow(),
    }), [
        symbol,
        direction,
        feeType,
        capital,
        leverage,
        makerTimeout,
        entryLimitPrice,
        stopLossPct,
        stopLossUsd,
        trailingStopPct,
        trailingStartProfitPct,
        breakEvenAtPct,
        partialTpPct,
        partialTpSize,
        chartInterval,
        chartEngine,
    ]);

    const persistConfig = useCallback(async (entry, { quiet = true } = {}) => {
        const localPayload = readLocalPayload();
        const nextPayload = buildPayload(localPayload, exchange, entry);
        localStorage.setItem(MANUAL_LOCAL_KEY, JSON.stringify(nextPayload));

        try {
            await updateUserSetting(MANUAL_CONFIG_KEY, nextPayload);
            if (!quiet) {
                setSaveInfo('Configuração manual salva.');
                setSaveError('');
            }
        } catch (e) {
            if (!quiet) {
                setSaveError(e.message || 'Falha ao salvar configuração manual.');
            }
        }
    }, [exchange]);

    useEffect(() => {
        let cancelled = false;
        hydratedRef.current = false;

        const loadPersisted = async () => {
            const defaults = getDefaultConfig();
            const localPayload = readLocalPayload();

            let remotePayload = {};
            try {
                const user = await fetchUserSettings();
                remotePayload = user?.settings?.[MANUAL_CONFIG_KEY]?.value || {};
            } catch {
                remotePayload = {};
            }

            const chosen = pickLatestEntry(localPayload, remotePayload, exchange) || defaults;
            if (cancelled) return;

            setSymbol(chosen.symbol);
            setDirection(chosen.direction);
            setFeeType(chosen.feeType);
            setCapital(chosen.capital);
            setLeverage(chosen.leverage);
            setMakerTimeout(chosen.makerTimeout);
            setEntryLimitPrice(chosen.entryLimitPrice || '');
            setStopLossPct(chosen.stopLossPct);
            setStopLossUsd(chosen.stopLossUsd);
            setTrailingStopPct(chosen.trailingStopPct);
            setTrailingStartProfitPct(chosen.trailingStartProfitPct);
            setBreakEvenAtPct(chosen.breakEvenAtPct || '');
            setPartialTpPct(chosen.partialTpPct || '');
            setPartialTpSize(chosen.partialTpSize || '50');
            setChartInterval(chosen.chartInterval || '1m');
            setChartEngine(chosen.chartEngine || 'classic');
            setSelectedSymbol(chosen.symbol);
            hydratedRef.current = true;
        };

        loadPersisted();
        return () => {
            cancelled = true;
            hydratedRef.current = false;
        };
    }, [exchange]);

    useEffect(() => {
        if (!hydratedRef.current) return;
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            persistConfig(readCurrentEntry(), { quiet: true });
        }, 700);

        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, [readCurrentEntry, persistConfig]);

    useEffect(() => {
        const id = setInterval(() => setCountdownNow(Date.now()), 1000);
        return () => clearInterval(id);
    }, []);

    const loadRates = useCallback(async () => {
        setRatesLoading(true);
        try {
            const res = await fetchFundingRates(exchange, search, 'score', 'desc');
            const rows = (res.data || []).slice(0, 120);
            setFundingRows(rows);
            if (!selectedSymbol && rows.length > 0) {
                setSelectedSymbol(rows[0].symbol);
            }
        } catch {
            // Mantém último snapshot no estado.
        } finally {
            setRatesLoading(false);
        }
    }, [exchange, search, selectedSymbol]);

    useEffect(() => {
        loadRates();
        const id = setInterval(loadRates, 6000);
        return () => clearInterval(id);
    }, [loadRates]);

    const loadKlines = useCallback(async () => {
        const symbolToLoad = normalizeSymbol(selectedSymbol || symbol);
        if (!symbolToLoad) {
            setKlines([]);
            return;
        }
        setKlinesLoading(true);
        try {
            const res = await fetchKlines(
                symbolToLoad,
                exchange,
                apiInterval,
                getKlineLimitForInterval(chartInterval),
            );
            setKlines(res.data || []);
        } catch {
            setKlines([]);
        } finally {
            setKlinesLoading(false);
        }
    }, [selectedSymbol, symbol, exchange, apiInterval, chartInterval]);

    useEffect(() => {
        if (chartEngine !== 'classic') return;
        loadKlines();
        const refreshMs = getRefreshMsForInterval(chartInterval);
        const id = setInterval(loadKlines, refreshMs);
        return () => clearInterval(id);
    }, [loadKlines, chartInterval, chartEngine]);

    const loadChartOps = useCallback(async ({ initial = false } = {}) => {
        const symbolToLoad = normalizeSymbol(selectedSymbol || symbol);

        if (initial) setOpsLoading(true);
        try {
            // Motivo: o card de operações agora é global (todos os pares),
            // mas os overlays do gráfico continuam por símbolo selecionado.
            const [globalRes, symbolRes] = await Promise.all([
                fetchRealChartOperations({
                    exchange,
                    limitClosed: 20,
                }),
                symbolToLoad
                    ? fetchRealChartOperations({
                        exchange,
                        symbol: symbolToLoad,
                        limitClosed: 20,
                    })
                    : Promise.resolve({ openPositions: [], pendingEntries: [], closedOperations: [] }),
            ]);

            setGlobalOpenPositions(Array.isArray(globalRes?.openPositions) ? globalRes.openPositions : []);
            setGlobalPendingEntries(Array.isArray(globalRes?.pendingEntries) ? globalRes.pendingEntries : []);
            setGlobalClosedOperations(Array.isArray(globalRes?.closedOperations) ? globalRes.closedOperations : []);
            setSymbolOpenPositions(Array.isArray(symbolRes?.openPositions) ? symbolRes.openPositions : []);
            setSymbolPendingEntries(Array.isArray(symbolRes?.pendingEntries) ? symbolRes.pendingEntries : []);
            setSymbolClosedOperations(Array.isArray(symbolRes?.closedOperations) ? symbolRes.closedOperations : []);
        } catch {
            // Silencioso: mantém último snapshot válido de operações.
        } finally {
            if (initial) setOpsLoading(false);
        }
    }, [exchange, selectedSymbol, symbol]);

    useEffect(() => {
        loadChartOps({ initial: true });
        const id = setInterval(() => {
            loadChartOps({ initial: false });
        }, 6000);
        return () => clearInterval(id);
    }, [loadChartOps]);

    const handleSelectSymbol = (nextSymbol) => {
        const normalized = normalizeSymbol(nextSymbol);
        if (!normalized) return;
        setSelectedSymbol(normalized);
        setSymbol(normalized);
    };

    const handleStartManual = async () => {
        setSubmitError('');
        setSubmitSuccess('');
        setSaveInfo('');

        const normalized = normalizeSymbol(symbol);
        if (!normalized) {
            setSubmitError('Informe uma moeda válida. Ex: BTCUSDT.');
            return;
        }

        const payload = {
            symbol: normalized,
            direction,
            feeType,
            capital: Number(capital),
            leverage: Number(leverage),
            makerTimeout: Number(makerTimeout),
            entryLimitPrice: parseNullableNumber(entryLimitPrice),
            stopLossPct: parseNullableNumber(stopLossPct),
            stopLossUsd: parseNullableNumber(stopLossUsd),
            trailingStopPct: parseNullableNumber(trailingStopPct),
            trailingStartProfitPct: parseNullableNumber(trailingStartProfitPct),
            breakEvenAtPct: parseNullableNumber(breakEvenAtPct),
            partialTpPct: parseNullableNumber(partialTpPct),
            partialTpSize: parseNullableNumber(partialTpSize) ?? 50,
        };

        if (
            payload.stopLossPct == null &&
            payload.stopLossUsd == null &&
            payload.trailingStopPct == null
        ) {
            setSubmitError('Defina ao menos uma proteção: Stop Loss (%) / Stop Loss (USDT) / Trailing Stop (%).');
            return;
        }

        setStarting(true);
        try {
            const entryToSave = {
                ...readCurrentEntry(),
                symbol: normalized,
                updatedAt: toIsoNow(),
            };
            await persistConfig(entryToSave, { quiet: false });
            await startManualOperation(exchange, payload);
            setSelectedSymbol(normalized);
            setSubmitSuccess(`Operação manual enviada para ${normalized}.`);
            loadChartOps({ initial: false });
        } catch (e) {
            setSubmitError(e.message || 'Falha ao iniciar operação manual.');
        } finally {
            setStarting(false);
        }
    };

    const candleRange = useMemo(() => {
        if (!Array.isArray(klines) || klines.length === 0) return null;
        const timestamps = klines
            .map(k => toChartTimestamp(k.timestamp))
            .filter(Boolean)
            .sort((a, b) => a - b);
        if (timestamps.length === 0) return null;
        return {
            from: timestamps[0],
            to: timestamps[timestamps.length - 1],
        };
    }, [klines]);

    const isWithinCandleRange = useCallback((ts) => {
        if (!candleRange) return true;
        const normalizedTs = toChartTimestamp(ts);
        if (!normalizedTs) return false;
        const margin = 3 * 60 * 60 * 1000;
        return normalizedTs >= (candleRange.from - margin) && normalizedTs <= (candleRange.to + margin);
    }, [candleRange]);

    const openHorizontalLines = useMemo(() => {
        return symbolOpenPositions.flatMap((op) => {
            const entryPrice = toNumber(op.entryPrice);
            const tpPrice = toNumber(op.tpLimitPrice);
            const isLong = op.direction === 'LONG';
            const rows = [];

            if (entryPrice && entryPrice > 0) {
                rows.push({
                    id: `open-entry-${op.positionId}`,
                    price: entryPrice,
                    color: isLong ? 'rgba(0, 230, 138, 0.95)' : 'rgba(255, 77, 106, 0.95)',
                    lineStyle: 'solid',
                    title: `Entrada ${op.direction}`,
                    lineWidth: 2,
                });
            }

            if (tpPrice && tpPrice > 0) {
                rows.push({
                    id: `open-limit-${op.positionId}`,
                    price: tpPrice,
                    color: 'rgba(245, 158, 11, 0.92)',
                    lineStyle: 'dashed',
                    title: 'Limit TP',
                    lineWidth: 2,
                });
            }

            return rows;
        });
    }, [symbolOpenPositions]);

    const lastPriceBySymbol = useMemo(() => {
        const map = new Map();
        for (const row of fundingRows) {
            const sym = String(row?.symbol || '').toUpperCase();
            if (!sym) continue;
            const last = toNumber(row?.lastPrice);
            if (last && last > 0) map.set(sym, last);
        }
        return map;
    }, [fundingRows]);

    const openPositionsUi = useMemo(() => {
        // Motivo: enriquecer posições abertas com Mark/PnL/horário para o grid global.
        return globalOpenPositions.map((op) => {
            const sym = String(op?.symbol || '').toUpperCase();
            const entry = toNumber(op?.entryPrice);
            const size = toNumber(op?.size);
            const entryMargin = toNumber(op?.entryMargin);
            // Motivo: priorizar mark vindo da API de operações e cair para funding snapshot quando necessário.
            const mark = toNumber(op?.markPrice ?? lastPriceBySymbol.get(sym));
            let pnlUsd = null;
            let pnlPct = null;

            if (entry && size && mark) {
                const isLong = op.direction === 'LONG';
                pnlUsd = isLong ? (mark - entry) * size : (entry - mark) * size;
                const notional = entry * size;
                if (notional > 0) pnlPct = (pnlUsd / notional) * 100;
            }

            return {
                ...op,
                symbol: sym || '—',
                markPrice: mark,
                entryMargin,
                pnlUsd,
                pnlPct,
                openTimeCompact: formatCompactDateTime(op?.openTime),
            };
        });
    }, [globalOpenPositions, lastPriceBySymbol]);

    const pendingEntriesUi = useMemo(() => {
        // Motivo: padroniza dados das entradas limit pendentes para o grid global da operação manual.
        return globalPendingEntries.map((entry) => ({
            ...entry,
            symbol: String(entry?.symbol || '').toUpperCase() || '—',
            limitPrice: toNumber(entry?.limitPrice),
            size: toNumber(entry?.size),
            status: String(entry?.status || 'pending').toLowerCase(),
            createdTimeCompact: formatCompactDateTime(entry?.createdAt || entry?.updatedAt),
        }));
    }, [globalPendingEntries]);

    const closedOperationsUi = useMemo(() => {
        // Motivo: normalizar horário e direção para manter consistência visual do grid.
        return globalClosedOperations.map((op) => ({
            ...op,
            symbol: String(op?.symbol || '').toUpperCase() || '—',
            entryMargin: toNumber(op?.entryMargin),
            closeTimeCompact: formatCompactDateTime(op?.closeTime || op?.openTime),
        }));
    }, [globalClosedOperations]);

    const closedTradeSegments = useMemo(() => {
        return symbolClosedOperations
            .map((op) => {
                const fromTime = toChartTimestamp(op.openTimestamp);
                const toTime = toChartTimestamp(op.closeTimestamp || op.tradeTimestamp);
                const fromPrice = toNumber(op.entryPrice);
                const toPrice = toNumber(op.exitPrice);
                if (!fromTime || !toTime || !fromPrice || !toPrice) return null;
                if (!isWithinCandleRange(fromTime) && !isWithinCandleRange(toTime)) return null;

                const pnl = Number(op.totalPnl || 0);
                return {
                    id: `closed-${op.tradeId}`,
                    fromTime,
                    toTime,
                    fromPrice,
                    toPrice,
                    color: pnl >= 0 ? 'rgba(34, 197, 94, 0.85)' : 'rgba(239, 68, 68, 0.85)',
                    lineStyle: 'solid',
                    lineWidth: 2,
                };
            })
            .filter(Boolean);
    }, [symbolClosedOperations, isWithinCandleRange]);

    const closedTradeMarkers = useMemo(() => {
        const markers = [];
        for (const op of symbolClosedOperations) {
            const openTs = toChartTimestamp(op.openTimestamp);
            const closeTs = toChartTimestamp(op.closeTimestamp || op.tradeTimestamp);
            const isLong = op.direction === 'LONG';
            const pnl = Number(op.totalPnl || 0);
            const pnlColor = pnl >= 0 ? '#22c55e' : '#ef4444';

            if (openTs && isWithinCandleRange(openTs)) {
                markers.push({
                    time: openTs,
                    position: isLong ? 'belowBar' : 'aboveBar',
                    color: '#38bdf8',
                    shape: 'circle',
                    text: 'E',
                });
            }

            if (closeTs && isWithinCandleRange(closeTs)) {
                markers.push({
                    time: closeTs,
                    position: isLong ? 'aboveBar' : 'belowBar',
                    color: pnlColor,
                    shape: 'square',
                    text: 'S',
                });
            }
        }
        return markers;
    }, [symbolClosedOperations, isWithinCandleRange]);

    return (
        <div className="manual-op-page">
            <div className="manual-op-layout">
                <div className="manual-op-main">
                    <div className="manual-op-chart-card">
                        <div className="manual-op-chart-header">
                            <h3>{normalizeSymbol(selectedSymbol) || '—'}</h3>
                            <div className="manual-op-chart-meta">
                                <span>
                                    Funding atual: <strong className={(Number(selectedRate?.fundingRatePercent || 0) >= 0) ? 'positive' : 'negative'}>
                                        {formatRate(selectedRate?.fundingRatePercent)}
                                    </strong>
                                </span>
                                <span>
                                    Próximo funding: <strong>{selectedRate?.nextFundingTime ? formatCountdown(selectedRate.nextFundingTime, countdownNow) : '—'}</strong>
                                </span>
                                <span>
                                    Abertas: <strong>{globalOpenPositions.length}</strong>
                                </span>
                                <span>
                                    Pendentes: <strong>{globalPendingEntries.length}</strong>
                                </span>
                                <span>
                                    Pendentes do par: <strong>{symbolPendingEntries.length}</strong>
                                </span>
                                <span>
                                    Fechadas: <strong>{globalClosedOperations.length}</strong>
                                </span>
                            </div>
                        </div>

                        <div className="manual-op-chart-engine-toggle">
                            <button
                                type="button"
                                className={chartEngine === 'advanced' ? 'active' : ''}
                                onClick={() => setChartEngine('advanced')}
                            >
                                <FaLayerGroup /> Advanced
                            </button>
                            <button
                                type="button"
                                className={chartEngine === 'classic' ? 'active' : ''}
                                onClick={() => setChartEngine('classic')}
                            >
                                Ver Clássico
                            </button>
                        </div>

                        <div className="manual-op-chart-funding-hint">
                            {chartEngine === 'advanced'
                                ? 'Widget Advanced ativo. Linhas detalhadas de funding e operações ficam no modo Clássico.'
                                : verticalFundingLines.length === 2
                                    ? 'Linhas de funding: anterior (amarela) e próxima (azul). Overlays: entrada, limit e trades fechados.'
                                    : 'Sem referência de funding suficiente para desenhar as linhas deste ativo.'}
                        </div>

                        <div className={`manual-op-chart-wrap ${chartEngine === 'advanced' ? 'is-advanced' : 'is-classic'}`}>
                            {chartEngine === 'advanced' ? (
                                <AdvancedTradingViewWidget
                                    symbol={normalizeSymbol(selectedSymbol)}
                                    exchange={exchange}
                                    interval={chartInterval}
                                />
                            ) : klinesLoading && klines.length === 0 ? (
                                <div className="manual-op-empty">Carregando gráfico...</div>
                            ) : klines.length === 0 ? (
                                <div className="manual-op-empty">Sem dados de gráfico para este ativo.</div>
                            ) : (
                                <TradingViewChart
                                    data={klines}
                                    interval={chartInterval}
                                    onIntervalChange={setChartInterval}
                                    intervalOptions={CHART_INTERVAL_OPTIONS}
                                    intervalHint={`Padrão: 1m. ${intervalHint}`.trim()}
                                    fitKey={normalizeSymbol(selectedSymbol)}
                                    symbol={normalizeSymbol(selectedSymbol)}
                                    verticalLines={verticalFundingLines}
                                    ensureVisibleTimes={verticalFundingLines.map(v => v.time)}
                                    openHorizontalLines={openHorizontalLines}
                                    closedTradeSegments={closedTradeSegments}
                                    closedTradeMarkers={closedTradeMarkers}
                                />
                            )}
                        </div>
                    </div>

                    <div className="manual-op-ops-card">
                        <div className="manual-op-ops-header">
                            <h3>
                                <FaLayerGroup /> Operações Gerais
                            </h3>
                            <span>{String(exchange || 'binance').toUpperCase()}</span>
                        </div>
                        <div className="manual-op-ops-panel">
                            <div className="manual-op-ops-col">
                                <h4>Todas as posições em aberto ({globalOpenPositions.length})</h4>
                                {opsLoading ? (
                                    <div className="manual-op-ops-empty">Carregando...</div>
                                ) : globalOpenPositions.length === 0 ? (
                                    <div className="manual-op-ops-empty">Sem posições abertas na exchange.</div>
                                ) : (
                                    <div className="manual-op-ops-grid-wrap">
                                        {/* Motivo: render em grid deixa o bloco visualmente igual ao padrão de cards/tabelas compactas do terminal. */}
                                        <div className="manual-op-ops-grid-head manual-op-ops-grid-open">
                                            <span>Par</span>
                                            <span>Lado</span>
                                            <span>Margem</span>
                                            <span>Entrada</span>
                                            <span>Mark</span>
                                            <span>PnL</span>
                                            <span>Hora</span>
                                        </div>
                                        <div className="manual-op-ops-grid-body">
                                            {openPositionsUi.map((op) => (
                                                <div key={`open-${op.positionId}`} className="manual-op-ops-grid-row manual-op-ops-grid-open">
                                                    {/* Motivo: clique no par sincroniza imediatamente gráfico e formulário com a moeda escolhida. */}
                                                    <button
                                                        type="button"
                                                        className="manual-op-symbol-link"
                                                        onClick={() => handleSelectSymbol(op.symbol)}
                                                        title={`Ir para ${op.symbol} no gráfico`}
                                                    >
                                                        {op.symbol || '—'}
                                                    </button>
                                                    <span className={`manual-op-side-badge ${op.direction === 'LONG' ? 'long' : 'short'}`}>{op.direction}</span>
                                                    <span>{formatUsd(op.entryMargin)}</span>
                                                    <span>{formatPrice(op.entryPrice)}</span>
                                                    <span>{formatPrice(op.markPrice)}</span>
                                                    <span className={pnlToneClass(op.pnlUsd)}>
                                                        {op.pnlUsd == null ? '—' : `${formatSignedUsd(op.pnlUsd)}${op.pnlPct == null ? '' : ` (${op.pnlPct >= 0 ? '+' : ''}${op.pnlPct.toFixed(2)}%)`}`}
                                                    </span>
                                                    <span>{op.openTimeCompact}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="manual-op-ops-col">
                                <h4>Entradas limit pendentes ({globalPendingEntries.length})</h4>
                                {opsLoading ? (
                                    <div className="manual-op-ops-empty">Carregando...</div>
                                ) : globalPendingEntries.length === 0 ? (
                                    <div className="manual-op-ops-empty">Sem entradas limit pendentes.</div>
                                ) : (
                                    <div className="manual-op-ops-grid-wrap">
                                        {/* Motivo: exibir claramente pendências de limit sem quebrar o padrão visual de grade do módulo. */}
                                        <div className="manual-op-ops-grid-head manual-op-ops-grid-pending">
                                            <span>Par</span>
                                            <span>Lado</span>
                                            <span>Limit</span>
                                            <span>Tamanho</span>
                                            <span>Status</span>
                                            <span>Hora</span>
                                        </div>
                                        <div className="manual-op-ops-grid-body">
                                            {pendingEntriesUi.map((op) => (
                                                <div key={`pending-${op.pendingId}`} className="manual-op-ops-grid-row manual-op-ops-grid-pending">
                                                    <button
                                                        type="button"
                                                        className="manual-op-symbol-link"
                                                        onClick={() => handleSelectSymbol(op.symbol)}
                                                        title={`Ir para ${op.symbol} no gráfico`}
                                                    >
                                                        {op.symbol || '—'}
                                                    </button>
                                                    <span className={`manual-op-side-badge ${op.direction === 'LONG' ? 'long' : 'short'}`}>{op.direction}</span>
                                                    <span>{formatPrice(op.limitPrice)}</span>
                                                    <span>{op.size == null ? '—' : op.size}</span>
                                                    <span className="manual-op-pending-status">{(op.status || 'pending').toUpperCase()}</span>
                                                    <span>{op.createdTimeCompact}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="manual-op-ops-col">
                                <h4>Fechadas recentes (20) de qualquer par</h4>
                                {opsLoading ? (
                                    <div className="manual-op-ops-empty">Carregando...</div>
                                ) : globalClosedOperations.length === 0 ? (
                                    <div className="manual-op-ops-empty">Sem operações fechadas recentes na exchange.</div>
                                ) : (
                                    <div className="manual-op-ops-grid-wrap">
                                        {/* Motivo: linhas em grid facilitam leitura rápida sem “peso” visual de tabela tradicional. */}
                                        <div className="manual-op-ops-grid-head manual-op-ops-grid-closed">
                                            <span>Par</span>
                                            <span>Lado</span>
                                            <span>Margem</span>
                                            <span>Entrada</span>
                                            <span>Saída</span>
                                            <span>PnL</span>
                                            <span>Hora</span>
                                        </div>
                                        <div className="manual-op-ops-grid-body">
                                            {closedOperationsUi.map((op) => (
                                                <div key={`closed-${op.tradeId}`} className="manual-op-ops-grid-row manual-op-ops-grid-closed">
                                                    {/* Motivo: mesma UX de navegação por clique no par, também para operações fechadas. */}
                                                    <button
                                                        type="button"
                                                        className="manual-op-symbol-link"
                                                        onClick={() => handleSelectSymbol(op.symbol)}
                                                        title={`Ir para ${op.symbol} no gráfico`}
                                                    >
                                                        {op.symbol || '—'}
                                                    </button>
                                                    <span className={`manual-op-side-badge ${op.direction === 'LONG' ? 'long' : 'short'}`}>{op.direction}</span>
                                                    <span>{formatUsd(op.entryMargin)}</span>
                                                    <span>{formatPrice(op.entryPrice)}</span>
                                                    <span>{formatPrice(op.exitPrice)}</span>
                                                    <span className={pnlToneClass(op.totalPnl)}>
                                                        {Number(op.totalPnl || 0) >= 0 ? '+' : ''}${Number(op.totalPnl || 0).toFixed(2)}
                                                    </span>
                                                    <span>{op.closeTimeCompact}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="manual-op-symbol-card">
                        <div className="manual-op-symbol-header">
                            <h3>
                                <FaChartLine /> Radar de Moedas
                            </h3>
                            <input
                                type="text"
                                placeholder="Buscar moeda"
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                            />
                        </div>

                        <div className="manual-op-symbol-table-wrap">
                            <table className="manual-op-symbol-table">
                                <thead>
                                    <tr>
                                        <th>Moeda</th>
                                        <th>Funding</th>
                                        <th>Intervalo</th>
                                        <th>Próx. Funding</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {ratesLoading ? (
                                        <tr>
                                            <td colSpan={4} className="muted">Carregando...</td>
                                        </tr>
                                    ) : fundingRows.length === 0 ? (
                                        <tr>
                                            <td colSpan={4} className="muted">Sem moedas no momento.</td>
                                        </tr>
                                    ) : fundingRows.map(row => {
                                        const sym = String(row.symbol || '').toUpperCase();
                                        const active = sym === String(selectedSymbol || '').toUpperCase();
                                        const rate = Number(row.fundingRatePercent || 0);
                                        return (
                                            <tr
                                                key={sym}
                                                className={active ? 'active' : ''}
                                                onClick={() => handleSelectSymbol(sym)}
                                            >
                                                <td>{sym}</td>
                                                <td className={rate >= 0 ? 'positive' : 'negative'}>{formatRate(rate)}</td>
                                                <td>{Number(row.fundingInterval || 8)}h</td>
                                                <td>{formatCountdown(row.nextFundingTime, countdownNow)}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <aside className="manual-op-sidebar">
                    <div className="manual-op-form-card">
                        <div className="manual-op-form-header">
                            <div>
                                <h2>
                                    <FaBolt />
                                    Manual
                                </h2>
                                <p>Abre ordem imediatamente</p>
                            </div>
                            <button
                                className="manual-op-save-btn"
                                type="button"
                                onClick={() => persistConfig(readCurrentEntry(), { quiet: false })}
                                disabled={starting}
                            >
                                <FaFloppyDisk /> Salvar
                            </button>
                        </div>

                        <div className="manual-op-grid">
                            <div className="manual-op-field">
                                <label>Moeda</label>
                                <input
                                    type="text"
                                    value={symbol}
                                    onChange={e => {
                                        const v = e.target.value.toUpperCase();
                                        setSymbol(v);
                                        setSelectedSymbol(normalizeSymbol(v) || v);
                                    }}
                                    placeholder="Ex: BTCUSDT"
                                    disabled={starting}
                                />
                            </div>

                            <div className="manual-op-field">
                                <label>Direção</label>
                                <div className="manual-op-toggle">
                                    <button
                                        type="button"
                                        className={direction === 'LONG' ? 'active-long' : ''}
                                        onClick={() => setDirection('LONG')}
                                        disabled={starting}
                                    >
                                        ▲ LONG
                                    </button>
                                    <button
                                        type="button"
                                        className={direction === 'SHORT' ? 'active-short' : ''}
                                        onClick={() => setDirection('SHORT')}
                                        disabled={starting}
                                    >
                                        ▼ SHORT
                                    </button>
                                </div>
                            </div>

                            <div className="manual-op-field">
                                <label>Preço de Entrada Limit (opcional)</label>
                                <input
                                    type="number"
                                    min="0"
                                    step="any"
                                    value={entryLimitPrice}
                                    onChange={e => setEntryLimitPrice(e.target.value)}
                                    placeholder="Ex: 0.1234"
                                    disabled={starting}
                                />
                            </div>

                            <div className="manual-op-field">
                                <label>Fee</label>
                                <div className="manual-op-toggle">
                                    <button
                                        type="button"
                                        className={feeType === 'maker' ? 'active-default' : ''}
                                        onClick={() => setFeeType('maker')}
                                        disabled={starting}
                                    >
                                        Maker
                                    </button>
                                    <button
                                        type="button"
                                        className={feeType === 'taker' ? 'active-default' : ''}
                                        onClick={() => setFeeType('taker')}
                                        disabled={starting}
                                    >
                                        Taker
                                    </button>
                                </div>
                            </div>

                            <div className="manual-op-field">
                                <label>Capital (USDT)</label>
                                <input type="number" min="1" value={capital} onChange={e => setCapital(e.target.value)} disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label>Alavancagem</label>
                                <input type="number" min="1" max="20" value={leverage} onChange={e => setLeverage(e.target.value)} disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label>Timeout Maker (s)</label>
                                <input type="number" min="2" max="900" value={makerTimeout} onChange={e => setMakerTimeout(e.target.value)} disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label>
                                    <FaShieldHalved /> Stop Loss (%)
                                </label>
                                <input type="number" min="0" step="0.1" value={stopLossPct} onChange={e => setStopLossPct(e.target.value)} placeholder="Ex: 1.5" disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label>
                                    <FaShieldHalved /> Stop Loss (USDT)
                                </label>
                                <input type="number" min="0" step="0.1" value={stopLossUsd} onChange={e => setStopLossUsd(e.target.value)} placeholder="Ex: 5" disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label>
                                    <FaArrowRotateLeft /> Trailing Stop (%)
                                </label>
                                <input type="number" min="0.1" step="0.1" value={trailingStopPct} onChange={e => setTrailingStopPct(e.target.value)} placeholder="Ex: 1.2" disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label>Ativar trailing após (%)</label>
                                <input type="number" min="0" step="0.1" value={trailingStartProfitPct} onChange={e => setTrailingStartProfitPct(e.target.value)} placeholder="Ex: 1.0" disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label title="Quando o lucro de preço atingir X%, o stop loss é movido automaticamente para o preço de entrada (break-even). Protege o capital mesmo sem atingir o trailing.">
                                    Break-Even em lucro (%)
                                </label>
                                <input type="number" min="0.1" step="0.1" value={breakEvenAtPct} onChange={e => setBreakEvenAtPct(e.target.value)} placeholder="Ex: 0.4" disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label title="Quando o lucro de preço atingir X%, fecha parcialmente a posição e continua monitorando o restante.">
                                    TP Parcial em lucro (%)
                                </label>
                                <input type="number" min="0.1" step="0.1" value={partialTpPct} onChange={e => setPartialTpPct(e.target.value)} placeholder="Ex: 0.8" disabled={starting} />
                            </div>

                            <div className="manual-op-field">
                                <label title="Percentual da posição a fechar no TP Parcial (padrão 50%).">
                                    Tamanho do TP Parcial (%)
                                </label>
                                {/* Comentário de controle: mantém o campo editável para pré-configuração, bloqueando apenas durante envio. */}
                                <input type="number" min="1" max="99" step="1" value={partialTpSize} onChange={e => setPartialTpSize(e.target.value)} placeholder="Ex: 50" disabled={starting} />
                            </div>

                            <div className="manual-op-action-wrap">
                                <button className="manual-op-start-btn" onClick={handleStartManual} disabled={starting}>
                                    {starting ? 'Iniciando...' : <><FaPlay /> Iniciar Operação Manual</>}
                                </button>
                            </div>
                        </div>

                        {saveInfo && (
                            <div className="manual-op-msg success">
                                <FaCircleCheck /> {saveInfo}
                            </div>
                        )}
                        {saveError && (
                            <div className="manual-op-msg error">
                                <FaTriangleExclamation /> {saveError}
                            </div>
                        )}
                        {submitSuccess && (
                            <div className="manual-op-msg success">
                                <FaCircleCheck /> {submitSuccess}
                            </div>
                        )}
                        {submitError && (
                            <div className="manual-op-msg error">
                                <FaTriangleExclamation /> {submitError}
                            </div>
                        )}
                    </div>
                </aside>
            </div>
        </div>
    );
}
