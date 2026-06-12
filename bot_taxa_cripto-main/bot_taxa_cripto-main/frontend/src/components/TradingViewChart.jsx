import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    createChart,
    CandlestickSeries,
    LineSeries,
    LineStyle,
    createSeriesMarkers,
} from 'lightweight-charts';

// ── Formatação de preço adaptativa ────────────────────────────────────────────
function adaptivePrice(price) {
    const abs = Math.abs(price);
    if (abs >= 10000) return price.toFixed(1);
    if (abs >= 1000)  return price.toFixed(2);
    if (abs >= 1)     return price.toFixed(3);
    if (abs >= 0.1)   return price.toFixed(4);
    if (abs >= 0.01)  return price.toFixed(5);
    return price.toFixed(6);
}

// ── Normalização de dados ─────────────────────────────────────────────────────
function normalizeToChartTime(value) {
    const raw = Number(value);
    if (!Number.isFinite(raw) || raw <= 0) return null;
    return raw > 10_000_000_000 ? Math.floor(raw / 1000) : Math.floor(raw);
}

function normalizeCandles(rawData) {
    return (rawData || []).map(k => ({
        time: normalizeToChartTime(k.timestamp),
        open:  Number(k.open),
        high:  Number(k.high),
        low:   Number(k.low),
        close: Number(k.close),
    }))
        .filter(c => c.time !== null && isFinite(c.open) && isFinite(c.high) && isFinite(c.low) && isFinite(c.close))
        .sort((a, b) => a.time - b.time);
}

function timeToEpochSeconds(value) {
    if (typeof value === 'number') return Math.floor(value);
    if (typeof value === 'string') {
        const parsed = Date.parse(value);
        return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : null;
    }
    if (value && typeof value === 'object' && 'year' in value && 'month' in value && 'day' in value) {
        return Math.floor(Date.UTC(value.year, value.month - 1, value.day) / 1000);
    }
    return null;
}

function normalizeVerticalLine(line, idx) {
    if (!line || typeof line !== 'object') return null;
    const time = normalizeToChartTime(line.time);
    if (!time) return null;
    return {
        id: `${time}-${idx}`,
        time,
        color: line.color || 'rgba(59, 130, 246, 0.85)',
        label: line.label || '',
        labelColor: line.labelColor || '#3b82f6',
    };
}

function resolveLineStyle(style) {
    if (style === 'dashed') return LineStyle.Dashed;
    if (style === 'dotted') return LineStyle.Dotted;
    return LineStyle.Solid;
}

function normalizeHorizontalLine(line, idx) {
    if (!line || typeof line !== 'object') return null;
    const price = Number(line.price);
    if (!Number.isFinite(price) || price <= 0) return null;
    return {
        id: line.id || `hline-${idx}-${price}`,
        price,
        color: line.color || 'rgba(34, 197, 94, 0.9)',
        title: line.title || line.label || '',
        lineWidth: Number.isFinite(Number(line.lineWidth)) ? Number(line.lineWidth) : 2,
        lineStyle: resolveLineStyle(line.lineStyle),
    };
}

function normalizeClosedSegment(segment, idx) {
    if (!segment || typeof segment !== 'object') return null;
    const fromTime = normalizeToChartTime(segment.fromTime);
    const toTime = normalizeToChartTime(segment.toTime);
    const fromPrice = Number(segment.fromPrice);
    const toPrice = Number(segment.toPrice);
    if (!fromTime || !toTime) return null;
    if (!Number.isFinite(fromPrice) || !Number.isFinite(toPrice)) return null;
    return {
        id: segment.id || `closed-seg-${idx}-${fromTime}-${toTime}`,
        fromTime,
        toTime,
        fromPrice,
        toPrice,
        color: segment.color || 'rgba(56, 189, 248, 0.85)',
        lineWidth: Number.isFinite(Number(segment.lineWidth)) ? Number(segment.lineWidth) : 2,
        lineStyle: resolveLineStyle(segment.lineStyle),
    };
}

// ── Indicadores ───────────────────────────────────────────────────────────────
function computeEma(candles, period) {
    if (!candles.length || period <= 0) return [];
    const alpha = 2 / (period + 1);
    let ema = candles[0].close;
    const result = [{ time: candles[0].time, value: ema }];
    for (let i = 1; i < candles.length; i++) {
        ema = candles[i].close * alpha + ema * (1 - alpha);
        result.push({ time: candles[i].time, value: ema });
    }
    return result;
}

function computeRsi(candles, period = 14) {
    if (candles.length <= period) return [];
    let gains = 0, losses = 0;
    for (let i = 1; i <= period; i++) {
        const diff = candles[i].close - candles[i - 1].close;
        if (diff >= 0) gains += diff; else losses += Math.abs(diff);
    }
    let avgGain = gains / period;
    let avgLoss = losses / period;
    const rsiData = [];
    const firstRs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
    rsiData.push({ time: candles[period].time, value: avgLoss === 0 ? 100 : 100 - 100 / (1 + firstRs) });
    for (let i = period + 1; i < candles.length; i++) {
        const diff = candles[i].close - candles[i - 1].close;
        avgGain = ((avgGain * (period - 1)) + (diff > 0 ? diff : 0)) / period;
        avgLoss = ((avgLoss * (period - 1)) + (diff < 0 ? Math.abs(diff) : 0)) / period;
        const rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
        rsiData.push({ time: candles[i].time, value: avgLoss === 0 ? 100 : 100 - 100 / (1 + rs) });
    }
    return rsiData;
}

// ── Formatação de tempo BRT ───────────────────────────────────────────────────
function toDateFromChartTime(time) {
    if (typeof time === 'number') return new Date(time * 1000);
    if (typeof time === 'string') {
        const p = Date.parse(time);
        return Number.isFinite(p) ? new Date(p) : null;
    }
    if (time && typeof time === 'object' && 'year' in time) {
        return new Date(Date.UTC(time.year, time.month - 1, time.day));
    }
    return null;
}

const brtFull  = new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
const brtShort = new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });

function fmtBrt(time, full = true) {
    const d = toDateFromChartTime(time);
    if (!d) return '';
    return (full ? brtFull : brtShort).format(d).replace(',', '');
}

function getFullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
}

// ── Componente principal ──────────────────────────────────────────────────────
export default function TradingViewChart({
    data,
    containerStyle,
    markers    = [],
    closedTradeMarkers = [],
    interval   = '1h',
    onIntervalChange,
    intervalOptions = [],
    intervalHint    = '',
    fitKey          = '',
    symbol          = '',
    verticalLines   = [],
    openHorizontalLines = [],
    closedTradeSegments = [],
    ensureVisibleTimes = [],
}) {
    const chartWrapperRef   = useRef();
    const chartContainerRef = useRef();
    const chartRef          = useRef();
    const seriesRef         = useRef();
    const markersPluginRef  = useRef();
    const priceLinesRef     = useRef([]);
    const closedSegmentsRef = useRef(new Map());
    const ema9Ref           = useRef(null);
    const ema25Ref          = useRef(null);
    const ema200Ref         = useRef(null);
    const rsiPaneRef        = useRef(null);
    const rsiSeriesRef      = useRef(null);
    const didInitialFitRef  = useRef(false);
    const ensureAppliedKeyRef = useRef('');

    const [showRsi,  setShowRsi]  = useState(false);
    const [showEmas, setShowEmas] = useState(false);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [projectedVerticalLines, setProjectedVerticalLines] = useState([]);

    const normalizedData = useMemo(() => normalizeCandles(data), [data]);
    const normalizedVerticalLines = useMemo(
        () => (verticalLines || []).map(normalizeVerticalLine).filter(Boolean).sort((a, b) => a.time - b.time),
        [verticalLines],
    );
    const normalizedHorizontalLines = useMemo(
        () => (openHorizontalLines || []).map(normalizeHorizontalLine).filter(Boolean),
        [openHorizontalLines],
    );
    const normalizedClosedSegments = useMemo(
        () => (closedTradeSegments || [])
            .map(normalizeClosedSegment)
            .filter(Boolean)
            .sort((a, b) => a.fromTime - b.fromTime),
        [closedTradeSegments],
    );
    const normalizedEnsureTimes = useMemo(() => {
        const seen = new Set();
        const merged = [...(ensureVisibleTimes || []), ...normalizedVerticalLines.map(v => v.time)];
        return merged
            .map(normalizeToChartTime)
            .filter((t) => {
                if (!t || seen.has(t)) return false;
                seen.add(t);
                return true;
            })
            .sort((a, b) => a - b);
    }, [ensureVisibleTimes, normalizedVerticalLines]);

    const updateProjectedVerticalLines = useCallback(() => {
        const chart = chartRef.current;
        const container = chartContainerRef.current;
        if (!chart || !container || normalizedVerticalLines.length === 0) {
            setProjectedVerticalLines([]);
            return;
        }

        const width = container.clientWidth || 0;
        if (width <= 0) {
            setProjectedVerticalLines([]);
            return;
        }
        const timeScale = chart.timeScale();
        const visibleRange = timeScale.getVisibleRange?.();
        const visFrom = timeToEpochSeconds(visibleRange?.from);
        const visTo = timeToEpochSeconds(visibleRange?.to);
        const projected = normalizedVerticalLines
            .map((line) => {
                let coord = timeScale.timeToCoordinate(line.time);

                // Fallback para tempos futuros/passados sem candle correspondente:
                // projeta com base no range visível atual.
                if ((coord === null || coord === undefined || !Number.isFinite(coord)) && visFrom != null && visTo != null && visTo > visFrom) {
                    const ratio = (line.time - visFrom) / (visTo - visFrom);
                    coord = ratio * width;
                }

                if (coord === null || coord === undefined || !Number.isFinite(coord)) return null;
                const left = Math.min(Math.max(coord, 0), width);
                return { ...line, left, alignRight: left > (width - 130) };
            })
            .filter(Boolean);

        setProjectedVerticalLines(projected);
    }, [normalizedVerticalLines]);

    // ── Criação do gráfico (uma vez) ─────────────────────────────────────────
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            width: chartContainerRef.current.clientWidth,
            height: Math.max(300, chartContainerRef.current.clientHeight || 300),
            layout: {
                background: { type: 'solid', color: 'transparent' },
                textColor: 'rgba(255, 255, 255, 0.6)',
                fontFamily: 'Inter, sans-serif',
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
                borderColor: 'rgba(255, 255, 255, 0.1)',
                tickMarkFormatter: (time) => fmtBrt(time, false),
            },
            rightPriceScale: {
                borderColor: 'rgba(255, 255, 255, 0.1)',
            },
            localization: {
                locale: 'pt-BR',
                timeFormatter: (time) => fmtBrt(time, true),
                priceFormatter: adaptivePrice,
            },
            crosshair: {
                vertLine: { color: 'rgba(255,255,255,0.2)', labelBackgroundColor: 'var(--bg-card)' },
                horzLine: { color: 'rgba(255,255,255,0.2)', labelBackgroundColor: 'var(--bg-card)' },
            },
        });
        chartRef.current = chart;

        const seriesOpts = {
            upColor: '#00e68a',
            downColor: '#ff4d6a',
            borderVisible: false,
            wickUpColor: '#00e68a',
            wickDownColor: '#ff4d6a',
            priceFormat: { type: 'custom', formatter: adaptivePrice, minMove: 0.000001 },
        };

        const cs = typeof chart.addCandlestickSeries === 'function'
            ? chart.addCandlestickSeries(seriesOpts)
            : chart.addSeries(CandlestickSeries, seriesOpts);
        seriesRef.current = cs;

        const onResize = () => {
            if (!chartContainerRef.current) return;
            chart.applyOptions({
                width: chartContainerRef.current.clientWidth,
                height: Math.max(300, chartContainerRef.current.clientHeight || 300),
            });
            updateProjectedVerticalLines();
        };
        window.addEventListener('resize', onResize);
        const ro = new ResizeObserver(onResize);
        ro.observe(chartContainerRef.current);

        return () => {
            window.removeEventListener('resize', onResize);
            ro.disconnect();
            chart.remove();
            chartRef.current = null;
            seriesRef.current = null;
            markersPluginRef.current = null;
            priceLinesRef.current = [];
            closedSegmentsRef.current = new Map();
            ema9Ref.current = ema25Ref.current = ema200Ref.current = null;
            rsiPaneRef.current = rsiSeriesRef.current = null;
            didInitialFitRef.current = false;
            ensureAppliedKeyRef.current = '';
            setProjectedVerticalLines([]);
        };
    }, []);

    // ── Atualização de dados ──────────────────────────────────────────────────
    useEffect(() => {
        const series = seriesRef.current;
        const chart  = chartRef.current;
        if (!series || !chart) return;

        series.setData(normalizedData);

        if (normalizedData.length > 0 && !didInitialFitRef.current) {
            chart.timeScale().fitContent();
            didInitialFitRef.current = true;
        }
        requestAnimationFrame(updateProjectedVerticalLines);
    }, [normalizedData, updateProjectedVerticalLines]);

    // Só reseta o fit quando muda o símbolo (fitKey = symbol), NÃO no intervalo
    useEffect(() => {
        didInitialFitRef.current = false;
        ensureAppliedKeyRef.current = '';
    }, [fitKey]);

    // ── Garantia de visibilidade para linhas de referência (funding) ────────
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart || normalizedData.length === 0) return;

        const ensureKey = `${fitKey || symbol || ''}|${interval}|${normalizedEnsureTimes.join(',')}`;
        if (ensureAppliedKeyRef.current === ensureKey) {
            requestAnimationFrame(updateProjectedVerticalLines);
            return;
        }

        if (normalizedEnsureTimes.length === 0) {
            requestAnimationFrame(updateProjectedVerticalLines);
            ensureAppliedKeyRef.current = ensureKey;
            return;
        }

        const first = normalizedData[0].time;
        const last = normalizedData[normalizedData.length - 1].time;
        const step = normalizedData.length > 1
            ? Math.max(1, normalizedData[normalizedData.length - 1].time - normalizedData[normalizedData.length - 2].time)
            : 60;

        const minNeed = Math.min(first, ...normalizedEnsureTimes);
        const maxNeed = Math.max(last, ...normalizedEnsureTimes);
        const from = Math.floor(minNeed - (step * 6));
        const to = Math.ceil(maxNeed + (step * 2));

        chart.timeScale().setVisibleRange({ from, to });
        if (maxNeed > last) {
            const barsAhead = Math.ceil((maxNeed - last) / step) + 2;
            chart.timeScale().applyOptions({ rightOffset: Math.max(2, barsAhead) });
        }

        requestAnimationFrame(updateProjectedVerticalLines);
        ensureAppliedKeyRef.current = ensureKey;
    }, [
        fitKey,
        symbol,
        interval,
        normalizedData,
        normalizedEnsureTimes,
        updateProjectedVerticalLines,
    ]);

    // ── Linhas horizontais (entrada / limit) ─────────────────────────────────
    useEffect(() => {
        const series = seriesRef.current;
        if (!series) return;

        for (const line of priceLinesRef.current) {
            try {
                series.removePriceLine(line);
            } catch {
                // ignora line refs já removidas
            }
        }
        priceLinesRef.current = [];

        if (normalizedHorizontalLines.length === 0) return;

        const created = normalizedHorizontalLines
            .map((line) => {
                try {
                    return series.createPriceLine({
                        price: line.price,
                        color: line.color,
                        lineWidth: line.lineWidth,
                        lineStyle: line.lineStyle,
                        axisLabelVisible: true,
                        title: line.title,
                    });
                } catch {
                    return null;
                }
            })
            .filter(Boolean);
        priceLinesRef.current = created;
    }, [normalizedHorizontalLines, fitKey]);

    // ── Segmentos de operações fechadas ───────────────────────────────────────
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        const refs = closedSegmentsRef.current;
        const keepIds = new Set(normalizedClosedSegments.map(s => s.id));

        for (const [id, lineSeries] of refs.entries()) {
            if (keepIds.has(id)) continue;
            try {
                chart.removeSeries(lineSeries);
            } catch {
                // noop
            }
            refs.delete(id);
        }

        for (const segment of normalizedClosedSegments) {
            let lineSeries = refs.get(segment.id);
            if (!lineSeries) {
                lineSeries = chart.addSeries(LineSeries, {
                    color: segment.color,
                    lineWidth: segment.lineWidth,
                    lineStyle: segment.lineStyle,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    crosshairMarkerVisible: false,
                });
                refs.set(segment.id, lineSeries);
            } else {
                lineSeries.applyOptions({
                    color: segment.color,
                    lineWidth: segment.lineWidth,
                    lineStyle: segment.lineStyle,
                });
            }
            lineSeries.setData([
                { time: segment.fromTime, value: segment.fromPrice },
                { time: segment.toTime, value: segment.toPrice },
            ]);
        }
    }, [normalizedClosedSegments]);

    // ── Recalcula projeção das linhas ao navegar no gráfico ──────────────────
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;
        const ts = chart.timeScale();
        const handler = () => updateProjectedVerticalLines();
        if (typeof ts.subscribeVisibleTimeRangeChange === 'function') {
            ts.subscribeVisibleTimeRangeChange(handler);
        }
        if (typeof ts.subscribeVisibleLogicalRangeChange === 'function') {
            ts.subscribeVisibleLogicalRangeChange(handler);
        }
        requestAnimationFrame(handler);
        return () => {
            if (typeof ts.unsubscribeVisibleTimeRangeChange === 'function') {
                ts.unsubscribeVisibleTimeRangeChange(handler);
            }
            if (typeof ts.unsubscribeVisibleLogicalRangeChange === 'function') {
                ts.unsubscribeVisibleLogicalRangeChange(handler);
            }
        };
    }, [updateProjectedVerticalLines]);

    // ── Tela cheia ───────────────────────────────────────────────────────────
    useEffect(() => {
        const onChange = () => {
            const el = getFullscreenElement();
            setIsFullscreen(el === chartWrapperRef.current);
            if (chartRef.current && chartContainerRef.current) {
                chartRef.current.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                    height: Math.max(300, chartContainerRef.current.clientHeight || 300),
                });
                updateProjectedVerticalLines();
            }
        };
        document.addEventListener('fullscreenchange', onChange);
        document.addEventListener('webkitfullscreenchange', onChange);
        return () => {
            document.removeEventListener('fullscreenchange', onChange);
            document.removeEventListener('webkitfullscreenchange', onChange);
        };
    }, []);

    // ── Marcadores ───────────────────────────────────────────────────────────
    useEffect(() => {
        const series = seriesRef.current;
        if (!series) return;

        const mergedMarkers = [...(markers || []), ...(closedTradeMarkers || [])];
        const norm = mergedMarkers.map(m => {
            const t = normalizeToChartTime(m.time);
            if (!t) return null;
            return { time: t, position: m.position || 'aboveBar', color: m.color || '#3b82f6', shape: m.shape || 'circle', text: m.text || '' };
        }).filter(Boolean);

        if (typeof series.setMarkers === 'function') {
            series.setMarkers(norm);
            return;
        }
        if (!markersPluginRef.current) {
            markersPluginRef.current = createSeriesMarkers(series, norm);
        } else {
            markersPluginRef.current.setMarkers(norm);
        }
    }, [markers, closedTradeMarkers]);

    // ── EMAs ─────────────────────────────────────────────────────────────────
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        const removeEmas = () => {
            [ema9Ref, ema25Ref, ema200Ref].forEach(ref => {
                if (ref.current) { chart.removeSeries(ref.current); ref.current = null; }
            });
        };

        if (!showEmas) { removeEmas(); return; }

        if (!ema9Ref.current)   ema9Ref.current   = chart.addSeries(LineSeries, { color: '#facc15', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
        if (!ema25Ref.current)  ema25Ref.current  = chart.addSeries(LineSeries, { color: '#8b5cf6', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
        if (!ema200Ref.current) ema200Ref.current = chart.addSeries(LineSeries, { color: '#22c55e', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });

        if (normalizedData.length > 0) {
            ema9Ref.current.setData(computeEma(normalizedData, 9));
            ema25Ref.current.setData(computeEma(normalizedData, 25));
            ema200Ref.current.setData(computeEma(normalizedData, 200));
        }
    }, [showEmas, normalizedData]);

    // ── RSI ──────────────────────────────────────────────────────────────────
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        const removeRsi = () => {
            if (rsiPaneRef.current) {
                try { chart.removePane(rsiPaneRef.current.paneIndex()); } catch { /* já removido */ }
            }
            rsiPaneRef.current = rsiSeriesRef.current = null;
        };

        if (!showRsi) { removeRsi(); return; }

        if (!rsiPaneRef.current) {
            const pane = chart.addPane();
            pane.setStretchFactor(0.22);
            rsiPaneRef.current  = pane;
            rsiSeriesRef.current = pane.addSeries(LineSeries, { color: '#60a5fa', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
        }

        if (rsiSeriesRef.current && normalizedData.length > 0) {
            rsiSeriesRef.current.setData(computeRsi(normalizedData, 14));
        }
    }, [showRsi, normalizedData]);

    // ── Toggle tela cheia ────────────────────────────────────────────────────
    const toggleFullscreen = async () => {
        const wrapper = chartWrapperRef.current;
        if (!wrapper) return;
        if (getFullscreenElement() === wrapper) {
            if (document.exitFullscreen) await document.exitFullscreen();
            else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
        } else {
            if (wrapper.requestFullscreen) await wrapper.requestFullscreen();
            else if (wrapper.webkitRequestFullscreen) wrapper.webkitRequestFullscreen();
        }
    };

    const showToolbar = typeof onIntervalChange === 'function' && intervalOptions.length > 0;

    return (
        <div className="tv-chart-wrapper" ref={chartWrapperRef}>
            {showToolbar && (
                <div className="tv-chart-toolbar">
                    <div className="tv-chart-intervals">
                        {intervalOptions.map(opt => (
                            <button key={opt.value} className={interval === opt.value ? 'active' : ''} onClick={() => onIntervalChange(opt.value)} type="button">
                                {opt.label}
                            </button>
                        ))}
                    </div>
                    <div className="tv-chart-indicators">
                        <button type="button" className={`tv-chart-indicator-btn tv-chart-fullscreen-btn ${isFullscreen ? 'active' : ''}`} onClick={toggleFullscreen}>
                            {isFullscreen ? 'Sair Tela Cheia' : 'Tela Cheia'}
                        </button>
                        <button type="button" className={`tv-chart-indicator-btn ${showRsi ? 'active' : ''}`} onClick={() => setShowRsi(p => !p)}>RSI</button>
                        <button type="button" className={`tv-chart-indicator-btn ${showEmas ? 'active' : ''}`} onClick={() => setShowEmas(p => !p)}>EMAs</button>
                        {intervalHint && <span className="tv-chart-hint">{intervalHint}</span>}
                    </div>
                </div>
            )}
            <div className="tv-chart-canvas-wrap">
                <div ref={chartContainerRef} style={{ width: '100%', flex: 1, height: '100%', minHeight: 0, ...containerStyle }} />
                {projectedVerticalLines.length > 0 && (
                    <div className="tv-chart-vlines-layer">
                        {projectedVerticalLines.map((line) => (
                            <div key={line.id} className="tv-chart-vline-wrap" style={{ left: `${line.left}px` }}>
                                <div className="tv-chart-vline" style={{ background: line.color }} />
                                {line.label && (
                                    <div className={`tv-chart-vline-label${line.alignRight ? ' right' : ''}`} style={{ color: line.labelColor }}>
                                        {line.label}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
