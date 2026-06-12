import { useState, useEffect, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import { LuRefreshCw, LuSearch, LuArrowLeft, LuActivity, LuShieldAlert, LuSettings, LuSparkles, LuX, LuCheck } from 'react-icons/lu';
import { fetchFundingRates, fetchSettings, updateSetting, requestScoreAIAnalysis, applyScoreAISuggestions } from '../services/api';

function fmtVol(v) {
  if (!v || v === 0) return '—';
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtHours(nextFundingTime) {
  if (!nextFundingTime) return '—';
  const msLeft = nextFundingTime - Date.now();
  if (msLeft <= 0) return 'Agora';
  const h = Math.floor(msLeft / 3600000);
  const m = Math.floor((msLeft % 3600000) / 60000);
  if (h >= 6) return `${h}h+`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function ScoreBar({ value, max, color }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <div style={{ width: '52px', height: '5px', background: 'var(--bg-secondary)', borderRadius: '3px', overflow: 'hidden', flexShrink: 0 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '3px' }} />
      </div>
      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', minWidth: '26px', tabularNums: true }}>
        {value.toFixed(1)}
      </span>
    </div>
  );
}

/* Barra bidirecional para o momentum (−15 a +15).
   Centro = zero; preenchimento verde à direita (positivo) ou vermelho à esquerda (negativo). */
function MomentumBar({ value }) {
  const MAX = 15;
  const pct = Math.min(100, (Math.abs(value) / MAX) * 50); // metade da barra por lado
  const isPos = value >= 0;
  const color = value > 1 ? 'var(--accent-green)' : value < -1 ? 'var(--accent-red)' : '#f59e0b';
  const textColor = value > 1 ? 'var(--accent-green)' : value < -1 ? 'var(--accent-red)' : 'var(--text-secondary)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <div style={{ width: '52px', height: '5px', background: 'var(--bg-secondary)', borderRadius: '3px', overflow: 'hidden', position: 'relative', flexShrink: 0 }}>
        {/* Marcador central */}
        <div style={{ position: 'absolute', left: '50%', top: 0, width: '1px', height: '100%', background: 'var(--text-muted)', opacity: 0.5, zIndex: 1 }} />
        {/* Preenchimento */}
        <div style={{
          position: 'absolute',
          height: '100%',
          background: color,
          borderRadius: '3px',
          width: `${pct}%`,
          left: isPos ? '50%' : `${50 - pct}%`,
        }} />
      </div>
      <span style={{ fontSize: '0.73rem', color: textColor, minWidth: '30px' }}>
        {value > 0 ? '+' : ''}{value.toFixed(1)}
      </span>
    </div>
  );
}

const CONFIDENCE_CFG = {
  FORTE:    { color: 'var(--accent-green)', bg: 'rgba(0,230,138,0.05)' },
  MODERADO: { color: 'var(--accent-blue)',  bg: 'rgba(59,130,246,0.05)' },
  FRACO:    { color: '#f59e0b',             bg: 'rgba(245,158,11,0.05)' },
  EVITAR:   { color: 'var(--accent-red)',   bg: 'rgba(239,68,68,0.04)' },
  'VETO R/R': { color: 'var(--text-muted)', bg: 'rgba(255,255,255,0.01)' },
  VETO: { color: 'var(--text-muted)', bg: 'rgba(255,255,255,0.01)' },
};

const MODE_OPTIONS = [
  { key: 'harvesting', label: 'Coleta de Taxa', description: 'Diagnóstico para captura de funding' },
  { key: 'counter_trend', label: 'Counter-Tendência', description: 'Diagnóstico para reversão pós-virada' },
];

const DEFAULT_HARVESTING_THRESHOLDS = { forte: 75, moderado: 50, fraco: 30 };
const DEFAULT_HARVESTING_LIMITS = { max_volatility: 35, min_volume: 2000000, max_funding_rate_pct: 1.0 };
const DEFAULT_HARVESTING_WEIGHTS = { apy: 40, vol: 20, int: 10, consistency: 15, momentum: 15 };

const DEFAULT_COUNTER_THRESHOLDS = { forte: 75, moderado: 50, fraco: 30 };
const DEFAULT_COUNTER_LIMITS = { min_volume: 2000000, min_funding_rate_pct: 0.01 };
const DEFAULT_COUNTER_WEIGHTS = { extremity: 40, persistence: 30, volume: 20, volatility_bonus: 10 };

const HARVESTING_COMPONENTS = [
  { key: 'APY',         desc: 'APY líquido ajustado por fee (0–40)',             color: '#8b5cf6',             field: 'apy',         max: 40 },
  { key: 'Vol',         desc: 'Liquidez — volume 24h (0–20)',                    color: 'var(--accent-green)', field: 'volume',      max: 20 },
  { key: 'Int',         desc: 'Intervalo de pagamento (0–10)',                   color: '#f59e0b',             field: 'interval',    max: 10 },
  { key: 'Consist.',    desc: 'Consistência histórica da direção (0–15)',         color: 'var(--accent-blue)',  field: 'consistency', max: 15 },
  { key: 'Moment.',     desc: 'Momentum da taxa nas últimas 4h (−15 a +15)',     color: '#ec4899',             field: 'momentum',    max: 15 },
];

const COUNTER_COMPONENTS = [
  { key: 'Extrem.',  desc: 'Extremidade da taxa (0–40)',                 color: '#8b5cf6',             field: 'extremity',        max: 40 },
  { key: 'Persist.', desc: 'Persistência da direção (0–30)',             color: 'var(--accent-blue)',  field: 'persistence',      max: 30 },
  { key: 'Vol',      desc: 'Liquidez para reversão (0–20)',              color: 'var(--accent-green)', field: 'volume',           max: 20 },
  { key: 'Volat.+',  desc: 'Bônus de volatilidade para reversão (0–10)', color: '#f59e0b',             field: 'volatility_bonus', max: 10 },
];

const FILTERS_HARVESTING = [
  { key: 'all',     label: 'Todos',   color: 'var(--text-secondary)' },
  { key: 'FORTE',   label: '✅ FORTE', color: 'var(--accent-green)' },
  { key: 'MODERADO',label: '⚠️ MODERADO', color: 'var(--accent-blue)' },
  { key: 'FRACO',   label: '⚡ FRACO', color: '#f59e0b' },
  { key: 'EVITAR',  label: '❌ EVITAR', color: 'var(--accent-red)' },
  { key: 'VETO R/R',label: '⛔ VETADO', color: 'var(--text-muted)' },
];

const FILTERS_COUNTER = [
  { key: 'all',     label: 'Todos',   color: 'var(--text-secondary)' },
  { key: 'FORTE',   label: '✅ FORTE', color: 'var(--accent-green)' },
  { key: 'MODERADO',label: '⚠️ MODERADO', color: 'var(--accent-blue)' },
  { key: 'FRACO',   label: '⚡ FRACO', color: '#f59e0b' },
  { key: 'EVITAR',  label: '❌ EVITAR', color: 'var(--accent-red)' },
  { key: 'VETO',    label: '⛔ VETADO', color: 'var(--text-muted)' },
];

const AI_FIELD_CONFIG = {
  harvesting: [
    { path: 'thresholds.forte', label: 'Threshold FORTE' },
    { path: 'thresholds.moderado', label: 'Threshold MODERADO' },
    { path: 'thresholds.fraco', label: 'Threshold FRACO' },
    { path: 'limits.max_volatility', label: 'Volatilidade Máxima (%)' },
    { path: 'limits.min_volume', label: 'Volume Mínimo ($)' },
    { path: 'weights.apy', label: 'Peso APY' },
    { path: 'weights.vol', label: 'Peso Volume' },
    { path: 'weights.int', label: 'Peso Intervalo' },
    { path: 'weights.consistency', label: 'Peso Consistência' },
    { path: 'weights.momentum', label: 'Peso Momentum (±)' },
  ],
  counter_trend: [
    { path: 'thresholds.forte', label: 'Threshold FORTE' },
    { path: 'thresholds.moderado', label: 'Threshold MODERADO' },
    { path: 'thresholds.fraco', label: 'Threshold FRACO' },
    { path: 'limits.min_volume', label: 'Volume Mínimo ($)' },
    { path: 'limits.min_funding_rate_pct', label: 'Funding Mínimo (%)' },
    { path: 'weights.extremity', label: 'Peso Extremidade' },
    { path: 'weights.persistence', label: 'Peso Persistência' },
    { path: 'weights.volume', label: 'Peso Volume' },
    { path: 'weights.volatility_bonus', label: 'Peso Volatilidade+' },
  ],
};

function getByPath(obj, path, fallback = null) {
  return String(path || '')
    .split('.')
    .reduce((acc, key) => (acc && Object.prototype.hasOwnProperty.call(acc, key) ? acc[key] : undefined), obj) ?? fallback;
}

function toNumeric(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function formatAiValue(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  return Number.isInteger(num) ? String(num) : num.toFixed(4);
}

export default function ScoreDiagnosticsPage({ exchange, user, onBack }) {
  const [activeTab, setActiveTab] = useState('diagnostico');
  // Estratégia exibida no diagnóstico: coleta de taxa x counter-trend.
  const [scoringMode, setScoringMode] = useState('harvesting');
  // Modo de configuração selecionado na aba de parâmetros.
  const [settingsMode, setSettingsMode] = useState('harvesting');

  // --- Aba Diagnóstico ---
  const [rates, setRates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [filterConf, setFilterConf] = useState('all');
  const [lastUpdate, setLastUpdate] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // --- Aba Configurações ---
  const [settings, setSettings] = useState({});
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [settingsSuccess, setSettingsSuccess] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiApplying, setAiApplying] = useState(false);
  const [aiError, setAiError] = useState('');
  const [aiResult, setAiResult] = useState(null);
  const [showAiModal, setShowAiModal] = useState(false);

  const load = useCallback(async (showRefresh = false) => {
    try {
      if (showRefresh) setRefreshing(true);
      setError('');
      const res = await fetchFundingRates(exchange, '', 'score', 'desc', scoringMode);
      setRates(res.data || []);
      setLastUpdate(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [exchange, scoringMode]);

  const loadSettings = useCallback(async () => {
    try {
      setSettingsLoading(true);
      setSettingsError('');
      const res = await fetchSettings();
      setSettings(res.settings || {});
    } catch (e) {
      setSettingsError(e.message);
    } finally {
      setSettingsLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    load();
    const iv = setInterval(() => load(), 30000);
    return () => clearInterval(iv);
  }, [load]);

  useEffect(() => {
    if (activeTab === 'configuracoes' && Object.keys(settings).length === 0) {
      loadSettings();
    }
  }, [activeTab, loadSettings, settings]);

  const handleSettingChange = (category, key, value) => {
    setSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        value: {
          ...(prev[category]?.value || {}),
          [key]: parseFloat(value) || 0,
        },
      },
    }));
  };

  const handleSave = async (settingKey) => {
    try {
      setSettingsSaving(true);
      setSettingsError('');
      setSettingsSuccess('');
      await updateSetting(settingKey, settings[settingKey]?.value);
      setSettingsSuccess('Configurações salvas com sucesso!');
      setTimeout(() => setSettingsSuccess(''), 3000);
    } catch (e) {
      setSettingsError(e.message);
    } finally {
      setSettingsSaving(false);
    }
  };

  const buildDraftSettings = useCallback(() => {
    // Comentário de controle: sempre envia draft do modo atual em edição na aba Configurações.
    if (settingsMode === 'counter_trend') {
      return {
        thresholds: settings.score_thresholds_counter?.value || DEFAULT_COUNTER_THRESHOLDS,
        limits: settings.score_limits_counter?.value || DEFAULT_COUNTER_LIMITS,
        weights: settings.score_weights_counter?.value || DEFAULT_COUNTER_WEIGHTS,
      };
    }
    return {
      thresholds: settings.score_thresholds?.value || DEFAULT_HARVESTING_THRESHOLDS,
      limits: settings.score_limits?.value || DEFAULT_HARVESTING_LIMITS,
      weights: settings.score_weights?.value || DEFAULT_HARVESTING_WEIGHTS,
    };
  }, [settings, settingsMode]);

  const renderAiMarkdown = useCallback((text) => {
    const html = marked.parse(text || '');
    return DOMPurify.sanitize(typeof html === 'string' ? html : '');
  }, []);

  const handleAnalyzeWithAI = async () => {
    try {
      setAiLoading(true);
      setAiError('');
      const res = await requestScoreAIAnalysis({
        exchange,
        mode: settingsMode,
        windowDays: 7,
        draftSettings: buildDraftSettings(),
      });
      setAiResult(res || null);
      setShowAiModal(true);
    } catch (e) {
      setAiError(e.message || 'Falha ao analisar com IA');
    } finally {
      setAiLoading(false);
    }
  };

  const handleApplyAISuggestions = async () => {
    try {
      if (!aiResult?.analysisId) return;
      setAiApplying(true);
      setAiError('');
      const res = await applyScoreAISuggestions(aiResult.analysisId);

      // Comentário de controle: aplica no estado local apenas as 3 chaves retornadas pelo backend.
      setSettings((prev) => {
        const next = { ...prev };
        const appliedSettings = res?.settings || {};
        Object.entries(appliedSettings).forEach(([key, value]) => {
          next[key] = {
            ...(next[key] || {}),
            value,
          };
        });
        return next;
      });

      setSettingsSuccess('Configurações recomendadas aplicadas com sucesso.');
      setAiResult((prev) => ({
        ...(prev || {}),
        applied: true,
      }));
      setShowAiModal(false);
      setTimeout(() => setSettingsSuccess(''), 3500);
    } catch (e) {
      setAiError(e.message || 'Falha ao aplicar sugestões da IA');
    } finally {
      setAiApplying(false);
    }
  };

  if (user?.role !== 'admin') {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <LuShieldAlert size={48} style={{ color: 'var(--accent-red)', marginBottom: '16px' }} />
        <h2 style={{ color: 'var(--accent-red)' }}>Acesso Restrito</h2>
        <p style={{ color: 'var(--text-muted)' }}>Esta área é reservada para administradores.</p>
        <button onClick={onBack} style={{ marginTop: '16px', padding: '8px 20px', borderRadius: '8px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', cursor: 'pointer' }}>
          Voltar
        </button>
      </div>
    );
  }

  const counts = rates.reduce((acc, r) => {
    const c = r.scoreData?.confidence || 'EVITAR';
    acc[c] = (acc[c] || 0) + 1;
    return acc;
  }, {});

  const isCounterMode = scoringMode === 'counter_trend';
  const components = isCounterMode ? COUNTER_COMPONENTS : HARVESTING_COMPONENTS;
  const filters = isCounterMode ? FILTERS_COUNTER : FILTERS_HARVESTING;

  const filtered = rates.filter(r => {
    const sym = (r.symbol || '').toLowerCase();
    const conf = r.scoreData?.confidence || '';
    return sym.includes(search.toLowerCase()) && (filterConf === 'all' || conf === filterConf);
  });

  const thresholds = settings.score_thresholds?.value || DEFAULT_HARVESTING_THRESHOLDS;
  const limits = settings.score_limits?.value || DEFAULT_HARVESTING_LIMITS;
  const weights = settings.score_weights?.value || DEFAULT_HARVESTING_WEIGHTS;
  const thresholdsCounter = settings.score_thresholds_counter?.value || DEFAULT_COUNTER_THRESHOLDS;
  const limitsCounter = settings.score_limits_counter?.value || DEFAULT_COUNTER_LIMITS;
  const weightsCounter = settings.score_weights_counter?.value || DEFAULT_COUNTER_WEIGHTS;

  const currentDraftForMode = buildDraftSettings();
  const aiProjection = aiResult?.projection || {};
  const aiBaseline = aiProjection?.baseline || {};
  const aiRecommended = aiProjection?.recommended || {};
  const aiDelta = aiProjection?.delta || {};
  const aiReasons = aiResult?.recommendationReasons || {};
  const aiRows = (AI_FIELD_CONFIG[settingsMode] || []).map((field) => {
    const currentVal = toNumeric(getByPath(currentDraftForMode, field.path, 0));
    const recommendedVal = toNumeric(getByPath(aiResult?.recommendedSettings || {}, field.path, currentVal));
    return {
      ...field,
      currentVal,
      recommendedVal,
      changed: currentVal !== recommendedVal,
      reason: aiReasons[field.path] || '',
    };
  });

  return (
    <div style={{ padding: '24px 32px' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px', marginBottom: '20px', flexWrap: 'wrap' }}>
        <button
          onClick={onBack}
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', padding: '8px 14px', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.88rem', flexShrink: 0 }}
        >
          <LuArrowLeft size={15} /> Voltar
        </button>

        <div style={{ flex: 1 }}>
          <h1 style={{ margin: 0, fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <LuActivity style={{ color: 'var(--accent-blue)' }} />
            Diagnóstico de Score
          </h1>
          <p style={{ margin: '4px 0 0', color: 'var(--text-muted)', fontSize: '0.83rem' }}>
            Algoritmo em tempo real · Configurações do scoring · Área exclusiva admin
          </p>
        </div>

        {activeTab === 'diagnostico' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
            {lastUpdate && (
              <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                Atualizado às {lastUpdate.toLocaleTimeString('pt-BR')}
              </span>
            )}
            <button
              onClick={() => load(true)}
              disabled={refreshing}
              style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)', padding: '6px 10px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.8rem' }}
            >
              <LuRefreshCw size={13} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
              Atualizar
            </button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '24px', borderBottom: '1px solid var(--border-color)', paddingBottom: '0' }}>
        {[
          { key: 'diagnostico',   label: 'Diagnóstico',   icon: <LuActivity size={14} /> },
          { key: 'configuracoes', label: 'Configurações', icon: <LuSettings size={14} /> },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              padding: '9px 18px',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === tab.key ? '2px solid var(--accent-blue)' : '2px solid transparent',
              color: activeTab === tab.key ? 'var(--accent-blue)' : 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: '0.88rem',
              fontWeight: activeTab === tab.key ? '700' : '400',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginBottom: '-1px',
              transition: 'color 0.15s',
            }}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* ===== ABA: DIAGNÓSTICO ===== */}
      {activeTab === 'diagnostico' && (
        <>
          {error && <div className="error-message" style={{ marginBottom: '16px' }}>{error}</div>}

          {loading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Carregando dados...</div>
          ) : (
            <>
              {/* Seletor de estratégia para separar diagnósticos de operações diferentes */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                {MODE_OPTIONS.map(mode => (
                  <button
                    key={mode.key}
                    onClick={() => {
                      setScoringMode(mode.key);
                      setFilterConf('all');
                    }}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '7px 12px',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      fontSize: '0.8rem',
                      border: `1px solid ${scoringMode === mode.key ? 'var(--accent-blue)' : 'var(--border-color)'}`,
                      background: scoringMode === mode.key ? 'rgba(59,130,246,0.10)' : 'var(--bg-secondary)',
                      color: scoringMode === mode.key ? 'var(--accent-blue)' : 'var(--text-secondary)',
                      fontWeight: scoringMode === mode.key ? '700' : '500',
                    }}
                    title={mode.description}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>

              {/* Filtros e resumo */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '16px' }}>
                {filters.map(f => (
                  <button
                    key={f.key}
                    onClick={() => setFilterConf(f.key)}
                    style={{
                      padding: '5px 12px', borderRadius: '16px', cursor: 'pointer', fontSize: '0.79rem',
                      fontWeight: filterConf === f.key ? '700' : '400',
                      background: filterConf === f.key ? 'var(--bg-secondary)' : 'transparent',
                      border: `1px solid ${filterConf === f.key ? f.color : 'var(--border-color)'}`,
                      color: f.color,
                    }}
                  >
                    {f.label} ({f.key === 'all' ? rates.length : (counts[f.key] || 0)})
                  </button>
                ))}

                <div style={{ marginLeft: 'auto', position: 'relative' }}>
                  <LuSearch size={13} style={{ position: 'absolute', left: '9px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                  <input
                    placeholder="Filtrar símbolo..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    style={{ padding: '5px 12px 5px 28px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '16px', fontSize: '0.79rem', width: '170px' }}
                  />
                </div>
              </div>

              {/* Legenda do algoritmo */}
              <div className="stat-card" style={{ padding: '14px 20px', marginBottom: '20px' }}>
                <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: '700', letterSpacing: '0.05em' }}>
                    FÓRMULA:
                  </span>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontFamily: 'monospace', background: 'var(--bg-secondary)', padding: '3px 10px', borderRadius: '4px' }}>
                    {isCounterMode
                      ? 'Score = Extremidade + Persistência + Vol + Bônus Volat. (0–100)'
                      : 'Score = APY(liq.) + Vol + Int + Consistência ± Momentum (0–100)'}
                  </span>
                  {components.map(c => (
                    <div key={c.key} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <div style={{ width: '8px', height: '8px', borderRadius: '2px', background: c.color, flexShrink: 0 }} />
                      <span style={{ fontSize: '0.76rem' }}>
                        <strong style={{ color: c.color }}>{c.key}</strong>
                        <span style={{ color: 'var(--text-muted)' }}> — {c.desc}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Tabela principal */}
              <div style={{ overflowX: 'auto', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.81rem' }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-card)', borderBottom: '2px solid var(--border-color)' }}>
                      {(isCounterMode
                        ? [
                            'Símbolo', 'Funding%', 'Volat.%', 'Volume 24h', 'Próx. Pag.',
                            'Score', 'Extrem. (40)', 'Persist. (30)', 'Vol (20)', 'Volat.+ (10)',
                            'Direção', 'Confiança', 'Motivos',
                          ]
                        : [
                            'Símbolo', 'Funding%', 'APY Bruto', 'Volat.%', 'Volume 24h', 'Próx. Pag.',
                            'Score', 'APY (40)', 'Vol (20)', 'Int (10)', 'Consist. (15)', 'Moment. (±15)',
                            'Direção', 'Confiança', 'Motivos',
                          ]).map(h => (
                        <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: '600', fontSize: '0.7rem', whiteSpace: 'nowrap', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {filtered.map(r => {
                      const sd = r.scoreData || {};
                      const bd = sd.breakdown || {};
                      const conf = sd.confidence || 'EVITAR';
                      const cc = CONFIDENCE_CFG[conf] || CONFIDENCE_CFG['EVITAR'];
                      const fundingPct = parseFloat(r.fundingRatePercent || 0);
                      const volat = parseFloat(r.price24hPcnt || 0);
                      const isVeto = conf === 'VETO R/R' || conf === 'VETO';

                      return (
                        <tr key={r.symbol} style={{ borderBottom: '1px solid var(--border-color)', background: cc.bg }}>
                          {/* Símbolo */}
                          <td style={{ padding: '9px 12px', fontWeight: '700', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
                            {r.symbol}
                          </td>

                          {/* Funding% */}
                          <td style={{ padding: '9px 12px', color: fundingPct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: '700', whiteSpace: 'nowrap' }}>
                            {fundingPct >= 0 ? '+' : ''}{fundingPct.toFixed(4)}%
                          </td>

                          {!isCounterMode && (
                            <td style={{ padding: '9px 12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                              {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : `${(bd.gross_apy ?? 0).toFixed(1)}%`}
                            </td>
                          )}

                          {/* Volatilidade muda de interpretação conforme a estratégia */}
                          <td style={{ padding: '9px 12px', color: isCounterMode ? (volat >= 10 ? 'var(--accent-green)' : 'var(--text-secondary)') : (volat > 15 ? '#f59e0b' : 'var(--text-secondary)'), whiteSpace: 'nowrap' }}>
                            {!isCounterMode && volat > 15 && <span title="Volatilidade preocupante para coleta de taxa" style={{ marginRight: '3px' }}>⚠</span>}
                            {isCounterMode && volat >= 10 && <span title="Volatilidade favorável para reversão" style={{ marginRight: '3px' }}>⚡</span>}
                            {volat.toFixed(2)}%
                          </td>

                          {/* Volume */}
                          <td style={{ padding: '9px 12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                            {fmtVol(parseFloat(r.volume24h || r.turnover24h || 0))}
                          </td>

                          {/* Próx. pagamento */}
                          <td style={{ padding: '9px 12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                            {fmtHours(r.nextFundingTime)}
                          </td>

                          {/* Score — círculo */}
                          <td style={{ padding: '9px 12px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <div style={{
                                width: '34px', height: '34px', borderRadius: '50%',
                                border: `2.5px solid ${cc.color}`,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: '0.7rem', fontWeight: '800', color: cc.color, flexShrink: 0,
                              }}>
                                {sd.score ?? 0}
                              </div>
                            </div>
                          </td>

                          {isCounterMode ? (
                            <>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <ScoreBar value={bd.extremity ?? 0} max={40} color="#8b5cf6" />}
                              </td>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <ScoreBar value={bd.persistence ?? 0} max={30} color="var(--accent-blue)" />}
                              </td>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <ScoreBar value={bd.volume ?? 0} max={20} color="var(--accent-green)" />}
                              </td>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <ScoreBar value={bd.volatility_bonus ?? 0} max={10} color="#f59e0b" />}
                              </td>
                            </>
                          ) : (
                            <>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <ScoreBar value={bd.apy ?? 0} max={40} color="#8b5cf6" />}
                              </td>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <ScoreBar value={bd.volume ?? 0} max={20} color="var(--accent-green)" />}
                              </td>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <ScoreBar value={bd.interval ?? 0} max={10} color="#f59e0b" />}
                              </td>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <ScoreBar value={bd.consistency ?? 0} max={15} color="var(--accent-blue)" />}
                              </td>
                              <td style={{ padding: '9px 12px' }}>
                                {isVeto ? <span style={{ color: 'var(--text-muted)' }}>—</span> : <MomentumBar value={bd.momentum ?? 0} />}
                              </td>
                            </>
                          )}

                          {/* Direção */}
                          <td style={{ padding: '9px 12px', fontWeight: '700', whiteSpace: 'nowrap', fontSize: '0.78rem',
                            color: sd.direction === 'SHORT' ? 'var(--accent-red)' : sd.direction === 'LONG' ? 'var(--accent-green)' : 'var(--text-muted)'
                          }}>
                            {sd.direction || '—'}
                          </td>

                          {/* Confiança */}
                          <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                            <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '0.71rem', fontWeight: '700', background: `${cc.color}20`, color: cc.color }}>
                              {conf}
                            </span>
                          </td>

                          {/* Motivo — coluna com quebra de linha */}
                          <td style={{ padding: '9px 12px', minWidth: '260px', maxWidth: '350px' }}>
                            {(sd.reasons || []).length === 0
                              ? <span style={{ color: 'var(--text-muted)', fontSize: '0.71rem' }}>—</span>
                              : (sd.reasons || []).map((reason, i) => (
                                  <div key={i} style={{ fontSize: '0.71rem', color: 'var(--text-muted)', lineHeight: '1.6', whiteSpace: 'normal', wordBreak: 'break-word' }}>
                                    {reason}
                                  </div>
                                ))
                            }
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {filtered.length === 0 && (
                  <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    Nenhum ativo encontrado com os filtros selecionados.
                  </div>
                )}
              </div>

              <p style={{ marginTop: '12px', color: 'var(--text-muted)', fontSize: '0.74rem' }}>
                {filtered.length} de {rates.length} ativos exibidos · Exchange: {exchange} · Estratégia: {isCounterMode ? 'Counter-Tendência' : 'Coleta de Taxa'} · Dados ordenados por Score
              </p>
            </>
          )}
        </>
      )}

      {/* ===== ABA: CONFIGURAÇÕES ===== */}
      {activeTab === 'configuracoes' && (
        <div className="scorediag-config-shell">
          {settingsError && <div className="error-message" style={{ marginBottom: '16px' }}>{settingsError}</div>}
          {settingsSuccess && (
            <div className="scorediag-success">
              {settingsSuccess}
            </div>
          )}

          {settingsLoading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Carregando configurações...</div>
          ) : (
            <>
              {/* Alterna entre os parâmetros de coleta e counter sem misturar contextos */}
              <div className="scorediag-mode-switch">
                {MODE_OPTIONS.map(mode => (
                  <button
                    key={mode.key}
                    className={`scorediag-mode-btn${settingsMode === mode.key ? ' active' : ''}`}
                    onClick={() => setSettingsMode(mode.key)}
                    title={mode.description}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>

              <div className="scorediag-ai-toolbar">
                <div className="scorediag-ai-copy">
                  <strong>Análise IA do modo atual</strong>
                  <span>
                    Valida trades dos últimos 7 dias, projeta baseline vs recomendado e gera ajustes de thresholds, filtros e pesos.
                  </span>
                </div>
                <button
                  className="scorediag-ai-btn"
                  onClick={handleAnalyzeWithAI}
                  disabled={settingsLoading || settingsSaving || aiLoading || aiApplying}
                >
                  <LuSparkles size={14} />
                  {aiLoading ? 'Analisando...' : 'Analisar com IA'}
                </button>
              </div>

              {aiError && (
                <div className="error-message" style={{ marginBottom: '16px' }}>
                  {aiError}
                </div>
              )}

              {settingsMode === 'harvesting' ? (
                <>
                  {/* Configurações dedicadas ao modo coleta de funding */}
                  <div className="section-block scorediag-config-section">
                    <h3 className="scorediag-config-title">Regras de Classificação (Coleta de Taxa)</h3>
                    <p className="scorediag-config-subtitle">
                      Pontuação mínima (0–100) para cada nível de confiança no modo de coleta de funding.
                    </p>
                    <div className="config-row">
                      <div className="config-field">
                        <label>FORTE (Min)</label>
                        <input
                          type="number" min="0" max="100"
                          value={thresholds.forte}
                          onChange={e => handleSettingChange('score_thresholds', 'forte', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>MODERADO (Min)</label>
                        <input
                          type="number" min="0" max="100"
                          value={thresholds.moderado}
                          onChange={e => handleSettingChange('score_thresholds', 'moderado', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>FRACO (Min)</label>
                        <input
                          type="number" min="0" max="100"
                          value={thresholds.fraco}
                          onChange={e => handleSettingChange('score_thresholds', 'fraco', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="scorediag-actions">
                      <button className="scorediag-save-btn" onClick={() => handleSave('score_thresholds')} disabled={settingsSaving}>
                        {settingsSaving ? 'Salvando...' : 'Salvar Regras'}
                      </button>
                    </div>
                  </div>

                  <div className="section-block scorediag-config-section">
                    <h3 className="scorediag-config-title">Filtros de Segurança (Coleta de Taxa)</h3>
                    <p className="scorediag-config-subtitle">
                      Vetos para ativos com risco excessivo no modo de coleta.
                    </p>
                    <div className="config-row">
                      <div className="config-field">
                        <label>Volatilidade Máxima (%)</label>
                        <input
                          type="number" min="0" max="100"
                          value={limits.max_volatility}
                          onChange={e => handleSettingChange('score_limits', 'max_volatility', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>Volume Diário Mínimo ($)</label>
                        <input
                          type="number" min="0"
                          value={limits.min_volume}
                          onChange={e => handleSettingChange('score_limits', 'min_volume', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="config-row">
                      <div className="config-field">
                        <label title="Taxa de funding máxima permitida por ciclo (%). Acima disso o ativo é vetado. Dados históricos: win rate cai para 41% acima de 1%/ciclo. Deixe vazio para desativar.">
                          Taxa Máxima por Ciclo (%)
                        </label>
                        <input
                          type="number" min="0" step="0.1"
                          placeholder="Ex: 1.0 (desativar = vazio)"
                          value={limits.max_funding_rate_pct ?? ''}
                          onChange={e => handleSettingChange(
                            'score_limits',
                            'max_funding_rate_pct',
                            e.target.value === '' ? null : e.target.value
                          )}
                        />
                      </div>
                    </div>
                    <div className="scorediag-actions">
                      <button className="scorediag-save-btn" onClick={() => handleSave('score_limits')} disabled={settingsSaving}>
                        {settingsSaving ? 'Salvando...' : 'Salvar Filtros'}
                      </button>
                    </div>
                  </div>

                  <div className="section-block scorediag-config-section">
                    <h3 className="scorediag-config-title">Pesos do Algoritmo (Coleta de Taxa)</h3>
                    <p className="scorediag-config-subtitle">
                      Score = APY({weights.apy}) + Vol({weights.vol}) + Int({weights.int}) + Consist.({weights.consistency}) ± Moment.({weights.momentum ?? 15})
                      {' '}— base {weights.apy + weights.vol + weights.int + weights.consistency} pts; momentum pode adicionar ou subtrair até {weights.momentum ?? 15} pts
                    </p>
                    <div className="config-row">
                      <div className="config-field">
                        <label>APY Líquido</label>
                        <input
                          type="number" min="0"
                          value={weights.apy}
                          onChange={e => handleSettingChange('score_weights', 'apy', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>Volume / Liquidez</label>
                        <input
                          type="number" min="0"
                          value={weights.vol}
                          onChange={e => handleSettingChange('score_weights', 'vol', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="config-row">
                      <div className="config-field">
                        <label>Frequência / Intervalo</label>
                        <input
                          type="number" min="0"
                          value={weights.int}
                          onChange={e => handleSettingChange('score_weights', 'int', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>Consistência Histórica</label>
                        <input
                          type="number" min="0"
                          value={weights.consistency}
                          onChange={e => handleSettingChange('score_weights', 'consistency', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="config-row">
                      <div className="config-field">
                        <label>Momentum da Taxa (±)</label>
                        <input
                          type="number" min="0"
                          value={weights.momentum ?? 15}
                          onChange={e => handleSettingChange('score_weights', 'momentum', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="scorediag-actions">
                      <button className="scorediag-save-btn" onClick={() => handleSave('score_weights')} disabled={settingsSaving}>
                        {settingsSaving ? 'Salvando...' : 'Salvar Pesos'}
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  {/* Configurações dedicadas ao modo counter-trend */}
                  <div className="section-block scorediag-config-section">
                    <h3 className="scorediag-config-title">Regras de Classificação (Counter-Tendência)</h3>
                    <p className="scorediag-config-subtitle">
                      Thresholds de confiança para decisões de reversão após funding.
                    </p>
                    <div className="config-row">
                      <div className="config-field">
                        <label>FORTE (Min)</label>
                        <input
                          type="number" min="0" max="100"
                          value={thresholdsCounter.forte}
                          onChange={e => handleSettingChange('score_thresholds_counter', 'forte', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>MODERADO (Min)</label>
                        <input
                          type="number" min="0" max="100"
                          value={thresholdsCounter.moderado}
                          onChange={e => handleSettingChange('score_thresholds_counter', 'moderado', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>FRACO (Min)</label>
                        <input
                          type="number" min="0" max="100"
                          value={thresholdsCounter.fraco}
                          onChange={e => handleSettingChange('score_thresholds_counter', 'fraco', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="scorediag-actions">
                      <button className="scorediag-save-btn" onClick={() => handleSave('score_thresholds_counter')} disabled={settingsSaving}>
                        {settingsSaving ? 'Salvando...' : 'Salvar Regras Counter'}
                      </button>
                    </div>
                  </div>

                  <div className="section-block scorediag-config-section">
                    <h3 className="scorediag-config-title">Filtros de Segurança (Counter-Tendência)</h3>
                    <p className="scorediag-config-subtitle">
                      Define o mínimo de liquidez e de taxa para considerar sinal de contra-tendência.
                    </p>
                    <div className="config-row">
                      <div className="config-field">
                        <label>Volume Diário Mínimo ($)</label>
                        <input
                          type="number" min="0"
                          value={limitsCounter.min_volume}
                          onChange={e => handleSettingChange('score_limits_counter', 'min_volume', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>Funding Mínimo (%)</label>
                        <input
                          type="number" min="0" step="0.0001"
                          value={limitsCounter.min_funding_rate_pct}
                          onChange={e => handleSettingChange('score_limits_counter', 'min_funding_rate_pct', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="scorediag-actions">
                      <button className="scorediag-save-btn" onClick={() => handleSave('score_limits_counter')} disabled={settingsSaving}>
                        {settingsSaving ? 'Salvando...' : 'Salvar Filtros Counter'}
                      </button>
                    </div>
                  </div>

                  <div className="section-block scorediag-config-section">
                    <h3 className="scorediag-config-title">Pesos do Algoritmo (Counter-Tendência)</h3>
                    <p className="scorediag-config-subtitle">
                      Score = Extremidade({weightsCounter.extremity}) + Persistência({weightsCounter.persistence}) +
                      {' '}Volume({weightsCounter.volume}) + Volat.+({weightsCounter.volatility_bonus}) =
                      {' '}{weightsCounter.extremity + weightsCounter.persistence + weightsCounter.volume + weightsCounter.volatility_bonus} pts máx
                    </p>
                    <div className="config-row">
                      <div className="config-field">
                        <label>Extremidade da Taxa</label>
                        <input
                          type="number" min="0"
                          value={weightsCounter.extremity}
                          onChange={e => handleSettingChange('score_weights_counter', 'extremity', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>Persistência</label>
                        <input
                          type="number" min="0"
                          value={weightsCounter.persistence}
                          onChange={e => handleSettingChange('score_weights_counter', 'persistence', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="config-row">
                      <div className="config-field">
                        <label>Volume / Liquidez</label>
                        <input
                          type="number" min="0"
                          value={weightsCounter.volume}
                          onChange={e => handleSettingChange('score_weights_counter', 'volume', e.target.value)}
                        />
                      </div>
                      <div className="config-field">
                        <label>Bônus de Volatilidade</label>
                        <input
                          type="number" min="0"
                          value={weightsCounter.volatility_bonus}
                          onChange={e => handleSettingChange('score_weights_counter', 'volatility_bonus', e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="scorediag-actions">
                      <button className="scorediag-save-btn" onClick={() => handleSave('score_weights_counter')} disabled={settingsSaving}>
                        {settingsSaving ? 'Salvando...' : 'Salvar Pesos Counter'}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}

      {showAiModal && aiResult && (
        <div className="scorediag-ai-modal-overlay" onClick={() => !aiApplying && setShowAiModal(false)}>
          <div className="scorediag-ai-modal" onClick={(e) => e.stopPropagation()}>
            <div className="scorediag-ai-modal-head">
              <div>
                <h3>Recomendação IA de Score</h3>
                <p>
                  Exchange: {exchange} · Modo: {settingsMode === 'counter_trend' ? 'Counter-Tendência' : 'Coleta de Taxa'} ·
                  Janela: {aiProjection?.windowDays || 7} dias
                </p>
              </div>
              <button
                className="scorediag-ai-modal-close"
                onClick={() => setShowAiModal(false)}
                disabled={aiApplying}
                aria-label="Fechar"
              >
                <LuX size={16} />
              </button>
            </div>

            <div className="scorediag-ai-metrics-grid">
              <div className="scorediag-ai-metric-card">
                <span>Trades avaliados</span>
                <strong>{aiProjection?.tradesEvaluated ?? aiResult?.metrics?.tradesEvaluated ?? 0}</strong>
              </div>
              <div className="scorediag-ai-metric-card">
                <span>PnL baseline</span>
                <strong>{formatAiValue(aiBaseline.totalPnl)}</strong>
              </div>
              <div className="scorediag-ai-metric-card">
                <span>PnL recomendado</span>
                <strong>{formatAiValue(aiRecommended.totalPnl)}</strong>
              </div>
              <div className="scorediag-ai-metric-card">
                <span>Delta PnL</span>
                <strong className={Number(aiDelta.totalPnl || 0) >= 0 ? 'is-positive' : 'is-negative'}>
                  {Number(aiDelta.totalPnl || 0) > 0 ? '+' : ''}{formatAiValue(aiDelta.totalPnl)}
                </strong>
              </div>
              <div className="scorediag-ai-metric-card">
                <span>Win rate baseline</span>
                <strong>{formatAiValue(aiBaseline.winRate)}%</strong>
              </div>
              <div className="scorediag-ai-metric-card">
                <span>Win rate recomendado</span>
                <strong>{formatAiValue(aiRecommended.winRate)}%</strong>
              </div>
            </div>

            <div className="scorediag-ai-markdown ai-markdown-content" dangerouslySetInnerHTML={{ __html: renderAiMarkdown(aiResult.analysisMarkdown || '') }} />

            <div className="scorediag-ai-compare-wrap">
              <h4>Atual vs Recomendado</h4>
              <div className="scorediag-ai-compare-table">
                <table>
                  <thead>
                    <tr>
                      <th>Parâmetro</th>
                      <th>Atual</th>
                      <th>Recomendado</th>
                      <th>Status</th>
                      <th>Motivo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {aiRows.map((row) => (
                      <tr key={row.path}>
                        <td>{row.label}</td>
                        <td>{formatAiValue(row.currentVal)}</td>
                        <td>{formatAiValue(row.recommendedVal)}</td>
                        <td>
                          <span className={`scorediag-ai-status${row.changed ? ' changed' : ''}`}>
                            {row.changed ? 'Alterar' : 'Manter'}
                          </span>
                        </td>
                        <td>{row.reason || 'Sem justificativa específica.'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="scorediag-ai-modal-actions">
              <button
                className="scorediag-ai-cancel-btn"
                onClick={() => setShowAiModal(false)}
                disabled={aiApplying}
              >
                Cancelar
              </button>
              <button
                className="scorediag-ai-confirm-btn"
                onClick={handleApplyAISuggestions}
                disabled={aiApplying || !aiResult?.analysisId}
              >
                <LuCheck size={14} />
                {aiApplying ? 'Aplicando...' : 'Confirmar e aplicar'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
