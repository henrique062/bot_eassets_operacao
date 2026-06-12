import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  FaArrowRotateRight,
  FaChartColumn,
  FaCircleDot,
  FaFilter,
  FaGaugeHigh,
  FaMagnifyingGlass,
  FaRobot,
  FaUserGear,
} from 'react-icons/fa6';
import { fetchCoinalyzeOpportunities } from '../services/api';

const INTERVAL_OPTIONS = [
  { value: '15min', label: '15m' },
  { value: '30min', label: '30m' },
  { value: '1hour', label: '1h' },
  { value: '2hour', label: '2h' },
  { value: '4hour', label: '4h' },
];

function asNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function formatSignedPct(value, decimals = 2) {
  const n = asNumber(value, 0);
  return `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`;
}

function formatUsd(value) {
  const n = asNumber(value, 0);
  if (n <= 0) return '—';
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

function formatCountdown(nextFundingTime) {
  const raw = String(nextFundingTime || '').trim();
  if (!raw) return '—';

  const nextMs = asNumber(raw, 0);
  if (nextMs <= 0) return '—';

  const diff = nextMs - Date.now();
  if (diff <= 0) return 'Agora';

  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  return `${String(hours).padStart(2, '0')}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`;
}

function actionLabel(action) {
  const normalized = String(action || '').toLowerCase();
  if (normalized === 'entry') return 'Entrada';
  if (normalized === 'monitor') return 'Monitorar';
  return 'Evitar';
}

export default function CoinalyzePage({ exchange = 'binance' }) {
  const [interval, setIntervalValue] = useState('1hour');
  const [lookbackHours, setLookbackHours] = useState(24);
  const [symbolsLimit, setSymbolsLimit] = useState(6);
  const [search, setSearch] = useState('');

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [payload, setPayload] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState('');

  const loadData = useCallback(async ({ silent = false } = {}) => {
    if (silent) setRefreshing(true);
    else setLoading(true);

    setError('');

    try {
      const response = await fetchCoinalyzeOpportunities({
        exchange,
        interval,
        lookbackHours,
        symbolsLimit,
        maxRows: 30,
      });

      setPayload(response);
      const first = response?.data?.[0]?.symbol;
      setSelectedSymbol(prev => prev || first || '');
    } catch (e) {
      setError(e.message || 'Falha ao carregar dados Coinalyze.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [exchange, interval, lookbackHours, symbolsLimit]);

  useEffect(() => {
    loadData({ silent: false });
  }, [loadData]);

  useEffect(() => {
    // Comentário de controle: auto refresh curto para manter visão operacional atualizada.
    const timerId = window.setInterval(() => {
      loadData({ silent: true });
    }, 60000);

    return () => window.clearInterval(timerId);
  }, [loadData]);

  const rows = useMemo(() => payload?.data || [], [payload]);

  const filteredRows = useMemo(() => {
    const term = String(search || '').trim().toUpperCase();
    if (!term) return rows;
    return rows.filter(row => String(row.symbol || '').toUpperCase().includes(term));
  }, [rows, search]);

  useEffect(() => {
    if (!filteredRows.length) {
      setSelectedSymbol('');
      return;
    }
    if (!selectedSymbol || !filteredRows.some(row => row.symbol === selectedSymbol)) {
      setSelectedSymbol(filteredRows[0].symbol);
    }
  }, [filteredRows, selectedSymbol]);

  const selectedRow = useMemo(
    () => filteredRows.find(row => row.symbol === selectedSymbol) || filteredRows[0] || null,
    [filteredRows, selectedSymbol],
  );

  const summary = useMemo(() => {
    const total = rows.length;
    const entryCount = rows.filter(row => String(row?.plan?.systematicAction || '').toLowerCase() === 'entry').length;
    const monitorCount = rows.filter(row => String(row?.plan?.systematicAction || '').toLowerCase() === 'monitor').length;
    const avgScore = total > 0 ? rows.reduce((acc, row) => acc + asNumber(row.score, 0), 0) / total : 0;

    return {
      total,
      entryCount,
      monitorCount,
      avgScore,
      picked: payload?.selectedSymbolsFromFunding?.length || 0,
    };
  }, [rows, payload]);

  return (
    <section className="coinalyze-page">
      <div className="coinalyze-hero">
        <div>
          <h2>
            <FaChartColumn />
            Coinalyze Signals
          </h2>
          <p>
            Métricas derivadas para decisão manual e trade sistemático ({exchange.toUpperCase()}).
          </p>
        </div>

        <button
          type="button"
          className="coinalyze-refresh-btn"
          onClick={() => loadData({ silent: true })}
          disabled={loading || refreshing}
        >
          <FaArrowRotateRight />
          {refreshing ? 'Atualizando...' : 'Atualizar'}
        </button>
      </div>

      <div className="coinalyze-summary-grid">
        <article className="coinalyze-summary-card">
          <span>Ativos analisados</span>
          <strong>{summary.total}</strong>
          <small>Top {summary.picked} por funding atual</small>
        </article>
        <article className="coinalyze-summary-card">
          <span>Sinais de entrada</span>
          <strong>{summary.entryCount}</strong>
          <small>Ação sistemática: entrada</small>
        </article>
        <article className="coinalyze-summary-card">
          <span>Em monitoramento</span>
          <strong>{summary.monitorCount}</strong>
          <small>Aguardando confirmação</small>
        </article>
        <article className="coinalyze-summary-card">
          <span>Score médio</span>
          <strong>{summary.avgScore.toFixed(1)}</strong>
          <small>Escala composta 0-100</small>
        </article>
      </div>

      <div className="coinalyze-filters">
        <label className="coinalyze-filter-field">
          <FaFilter />
          Intervalo
          <select value={interval} onChange={e => setIntervalValue(e.target.value)}>
            {INTERVAL_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>

        <label className="coinalyze-filter-field">
          Janela
          <select value={lookbackHours} onChange={e => setLookbackHours(Number(e.target.value))}>
            <option value={12}>12h</option>
            <option value={24}>24h</option>
            <option value={48}>48h</option>
            <option value={72}>72h</option>
          </select>
        </label>

        <label className="coinalyze-filter-field">
          Símbolos
          <select value={symbolsLimit} onChange={e => setSymbolsLimit(Number(e.target.value))}>
            <option value={4}>4</option>
            <option value={5}>5</option>
            <option value={6}>6</option>
            <option value={7}>7</option>
            <option value={8}>8</option>
          </select>
        </label>

        <label className="coinalyze-filter-field coinalyze-search-field">
          <FaMagnifyingGlass />
          Buscar
          <input
            type="text"
            placeholder="BTC, ETH..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </label>
      </div>

      {error && <div className="coinalyze-error-banner">{error}</div>}

      <div className="coinalyze-layout">
        <article className="coinalyze-table-card">
          <header>
            <h3>
              <FaGaugeHigh />
              Ranking operacional
            </h3>
            <span>{loading ? 'Carregando...' : `${filteredRows.length} ativos`}</span>
          </header>

          <div className="coinalyze-table-wrap">
            <table className="coinalyze-table">
              <thead>
                <tr>
                  <th>Ativo</th>
                  <th>Score</th>
                  <th>Ação</th>
                  <th>Funding</th>
                  <th>Pred.</th>
                  <th>OI 1h</th>
                  <th>Liq 1h</th>
                  <th>Flow Buy</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map(row => {
                  const metrics = row.metrics || {};
                  const plan = row.plan || {};
                  const score = asNumber(row.score, 0);
                  const action = String(plan.systematicAction || '').toLowerCase();
                  const liqImb = asNumber(metrics.liquidationImbalance1h, 0) * 100;
                  const buyFlow = asNumber(metrics.buyVolumeRatio, 0.5) * 100;

                  return (
                    <tr
                      key={row.symbol}
                      className={selectedRow?.symbol === row.symbol ? 'selected' : ''}
                      onClick={() => setSelectedSymbol(row.symbol)}
                    >
                      <td>
                        <div className="symbol-cell">
                          <strong>{row.symbol}</strong>
                          <small>{row.baseAsset}/{row.quoteAsset}</small>
                        </div>
                      </td>
                      <td className={score >= 72 ? 'score-high' : score >= 55 ? 'score-mid' : 'score-low'}>
                        {score.toFixed(1)}
                      </td>
                      <td>
                        <span className={`coinalyze-action-badge ${action}`}>{actionLabel(action)}</span>
                      </td>
                      <td>{formatSignedPct(metrics.fundingRatePct, 4)}</td>
                      <td>{formatSignedPct(metrics.predictedFundingRatePct, 4)}</td>
                      <td className={asNumber(metrics.oiDelta1hPct, 0) >= 0 ? 'positive' : 'negative'}>
                        {formatSignedPct(metrics.oiDelta1hPct, 2)}
                      </td>
                      <td className={liqImb >= 0 ? 'positive' : 'negative'}>{formatSignedPct(liqImb, 1)}</td>
                      <td>{buyFlow.toFixed(1)}%</td>
                    </tr>
                  );
                })}

                {!loading && !filteredRows.length && (
                  <tr>
                    <td colSpan={8} className="coinalyze-empty-row">Nenhum ativo encontrado.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>

        <aside className="coinalyze-detail-card">
          <header>
            <h3>
              <FaCircleDot />
              Plano operacional
            </h3>
          </header>

          {!selectedRow ? (
            <div className="coinalyze-detail-empty">Selecione um ativo para ver os detalhes.</div>
          ) : (
            <>
              <div className="coinalyze-detail-head">
                <div>
                  <h4>{selectedRow.symbol}</h4>
                  <p>
                    Próximo funding em {formatCountdown(selectedRow?.localSnapshot?.nextFundingTime)}
                  </p>
                </div>
                <span className="coinalyze-score-pill">{asNumber(selectedRow.score, 0).toFixed(1)}</span>
              </div>

              <div className="coinalyze-detail-grid">
                <div>
                  <span>Direção sugerida</span>
                  <strong>{selectedRow?.plan?.recommendedDirection || '—'}</strong>
                </div>
                <div>
                  <span>Ação</span>
                  <strong>{actionLabel(selectedRow?.plan?.systematicAction)}</strong>
                </div>
                <div>
                  <span>Funding dislocation</span>
                  <strong className={asNumber(selectedRow?.metrics?.fundingDislocationPct, 0) >= 0 ? 'positive' : 'negative'}>
                    {formatSignedPct(selectedRow?.metrics?.fundingDislocationPct, 4)}
                  </strong>
                </div>
                <div>
                  <span>Open Interest</span>
                  <strong>{formatUsd(selectedRow?.metrics?.openInterest)}</strong>
                </div>
              </div>

              <section className="coinalyze-plan-section">
                <h5>
                  <FaRobot />
                  Leitura Sistemática
                </h5>
                <p>{selectedRow?.plan?.executionHint || '—'}</p>
                <ul>
                  {(selectedRow?.plan?.reasons || []).map(reason => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </section>

              <section className="coinalyze-plan-section">
                <h5>
                  <FaUserGear />
                  Checklist Manual
                </h5>
                <ul>
                  {(selectedRow?.plan?.manualChecklist || []).map(item => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <p className="coinalyze-invalidation">{selectedRow?.plan?.manualInvalidation || '—'}</p>
              </section>
            </>
          )}
        </aside>
      </div>
    </section>
  );
}
