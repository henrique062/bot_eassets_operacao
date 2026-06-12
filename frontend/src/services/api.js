const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const DEV_AUTH_ENABLED = import.meta.env.DEV && import.meta.env.VITE_DEV_TEST_USER === 'true';
const DEV_AUTH_TOKEN = 'dev-local-token';

// ──────────────────────────────────────────────────────────────
// Helper: fetch autenticado — injeta Bearer token e trata 401
// ──────────────────────────────────────────────────────────────

function authHeaders(extra = {}) {
  const token = localStorage.getItem('auth.token');
  const headers = { 'Content-Type': 'application/json', ...extra };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });

  if (res.status === 401) {
    // Motivo: no modo local de teste mantemos a sessão fake para validar UI sem ciclo de logout/reload.
    const token = localStorage.getItem('auth.token');
    const isDevSession = DEV_AUTH_ENABLED && token === DEV_AUTH_TOKEN;
    if (isDevSession) {
      throw new Error('Endpoint protegido no modo de usuario de teste local.');
    }

    localStorage.removeItem('auth.token');
    localStorage.removeItem('auth.user');
    window.location.reload();
    throw new Error('Sessão expirada. Faça login novamente.');
  }

  return res;
}

// ──────────────────────────────────────────────────────────────
// Autenticação
// ──────────────────────────────────────────────────────────────

export async function login(email, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data?.detail || 'Falha ao fazer login');
  }
  return res.json();
}

export async function fetchMe() {
  const res = await apiFetch(`${API_BASE}/auth/me`);
  if (!res.ok) throw new Error('Falha ao buscar dados do usuário');
  return res.json();
}

// ──────────────────────────────────────────────────────────────
// Funding Rates (públicas)
// ──────────────────────────────────────────────────────────────

export async function fetchFundingRates(exchange = 'binance', search = '', sortBy = 'fundingRate', sortOrder = 'desc', scoringMode = 'harvesting') {
  const params = new URLSearchParams();
  params.append('exchange', exchange);
  if (search) params.append('search', search);
  params.append('sort_by', sortBy);
  params.append('sort_order', sortOrder);
  params.append('scoring_mode', scoringMode);

  const res = await apiFetch(`${API_BASE}/funding-rates?${params}`);
  if (!res.ok) throw new Error('Falha ao buscar funding rates');
  return res.json();
}

export async function fetchHistory(symbol, exchange = 'binance', limit = 50) {
  const params = new URLSearchParams();
  params.append('exchange', exchange);
  params.append('limit', limit);

  const res = await apiFetch(`${API_BASE}/funding-rates/${symbol}/history?${params}`);
  if (!res.ok) throw new Error(`Falha ao buscar histórico de ${symbol}`);
  return res.json();
}

export async function fetchLSR(symbol, exchange = 'binance', period = '1h', limit = 30) {
  const params = new URLSearchParams();
  params.append('exchange', exchange);
  params.append('period', period);
  params.append('limit', limit);

  const res = await apiFetch(`${API_BASE}/funding-rates/${symbol}/lsr?${params}`);
  if (!res.ok) throw new Error(`Falha ao buscar LSR de ${symbol}`);
  return res.json();
}

export async function fetchBatchLSR(symbols, exchange = 'binance') {
  const params = new URLSearchParams();
  params.append('symbols', symbols.join(','));
  params.append('exchange', exchange);

  const res = await apiFetch(`${API_BASE}/batch-lsr?${params}`);
  if (!res.ok) throw new Error('Falha ao buscar LSR em lote');
  return res.json();
}

export async function fetchKlines(symbol, exchange = 'binance', interval = '1h', limit = 24) {
  const params = new URLSearchParams();
  params.append('exchange', exchange);
  params.append('interval', interval);
  params.append('limit', limit);

  const res = await apiFetch(`${API_BASE}/funding-rates/${symbol}/klines?${params}`);
  if (!res.ok) throw new Error(`Falha ao buscar klines de ${symbol}`);
  return res.json();
}

export async function fetchStats(exchange = 'binance') {
  const params = new URLSearchParams();
  params.append('exchange', exchange);

  const res = await apiFetch(`${API_BASE}/stats?${params}`);
  if (!res.ok) throw new Error('Falha ao buscar estatísticas');
  return res.json();
}

// Comentário de controle: consulta ranking Coinalyze já enriquecido com snapshot local do backend.
export async function fetchCoinalyzeOpportunities({
  exchange = 'binance',
  quoteAsset = 'USDT',
  interval = '1hour',
  lookbackHours = 24,
  symbolsLimit = 6,
  maxRows = 20,
  minVolume24h = 0,
} = {}) {
  const params = new URLSearchParams();
  params.append('exchange', exchange);
  params.append('quote_asset', quoteAsset);
  params.append('interval', interval);
  params.append('lookback_hours', String(lookbackHours));
  params.append('symbols_limit', String(symbolsLimit));
  params.append('max_rows', String(maxRows));
  params.append('min_volume_24h', String(minVolume24h));

  const res = await apiFetch(`${API_BASE}/coinalyze/opportunities?${params.toString()}`);
  if (!res.ok) {
    let detail = 'Falha ao buscar oportunidades Coinalyze';
    try {
      const data = await res.json();
      detail = data?.detail || data?.message || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// Comentário de controle: catálogo de mercados suportados pelo microserviço Coinalyze.
export async function fetchCoinalyzeMarkets(exchange = 'binance', quoteAsset = 'USDT') {
  const params = new URLSearchParams();
  params.append('exchange', exchange);
  params.append('quote_asset', quoteAsset);

  const res = await apiFetch(`${API_BASE}/coinalyze/markets?${params.toString()}`);
  if (!res.ok) throw new Error('Falha ao buscar mercados Coinalyze');
  return res.json();
}

export async function fetchAIAnalysis(exchange = 'binance') {
  const params = new URLSearchParams();
  params.append('exchange', exchange);

  const res = await apiFetch(`${API_BASE}/ai-analysis?${params}`);
  if (!res.ok) throw new Error('Falha ao buscar análise IA');
  return res.json();
}

export async function fetchSmartReports(limit = 20, offset = 0) {
  const params = new URLSearchParams();
  params.append('limit', limit);
  params.append('offset', offset);

  const res = await apiFetch(`${API_BASE}/smart-reports?${params}`);
  if (!res.ok) throw new Error('Falha ao buscar histórico de relatórios');
  return res.json();
}

export async function fetchSmartReportById(id) {
  const res = await apiFetch(`${API_BASE}/smart-reports/${id}`);
  if (!res.ok) throw new Error(`Falha ao buscar detalhes do relatório ${id}`);
  return res.json();
}

export async function fetchBacktest(symbol, exchange = 'binance', capital = 1000, days = 7, leverage = 1, feeType = 'maker', mode = 'normal', targetTakeProfitPct = null) {
  const params = new URLSearchParams();
  params.append('symbol', symbol);
  params.append('exchange', exchange);
  params.append('capital', capital);
  params.append('days', days);
  params.append('leverage', leverage);
  params.append('fee_type', feeType);
  params.append('mode', mode);
  if (targetTakeProfitPct) params.append('target_take_profit_pct', targetTakeProfitPct);

  const res = await apiFetch(`${API_BASE}/backtest?${params}`);
  if (!res.ok) throw new Error('Falha ao rodar backtest');
  return res.json();
}

// ──────────────────────────────────────────────────────────────
// SSE helper — retorna URL com token no query param (EventSource não suporta headers)
// ──────────────────────────────────────────────────────────────

export function sseUrl(path) {
  const base = import.meta.env.VITE_API_BASE || '/api';
  const token = localStorage.getItem('auth.token') || '';
  return `${base}${path}?token=${encodeURIComponent(token)}`;
}

// ──────────────────────────────────────────────────────────────
// Real Trading
// ──────────────────────────────────────────────────────────────

export async function fetchRealStatus() {
  const res = await apiFetch(`${API_BASE}/real-trading`);
  if (!res.ok) throw new Error('Falha ao buscar status real');
  return res.json();
}

export async function fetchRealSessionStatus(sessionId) {
  const res = await apiFetch(`${API_BASE}/real-trading/${sessionId}`);
  if (!res.ok) throw new Error('Falha ao buscar sessão real');
  return res.json();
}

export async function startReal(exchange = 'binance', config = {}) {
  const res = await apiFetch(`${API_BASE}/real-trading/start?exchange=${exchange}`, {
    method: 'POST',
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    let detail = 'Falha ao iniciar real trading';
    try {
      const data = await res.json();
      detail = data?.detail || data?.message || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function startManualOperation(exchange = 'binance', config = {}) {
  const res = await apiFetch(`${API_BASE}/real-trading/manual/start?exchange=${exchange}`, {
    method: 'POST',
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    let detail = 'Falha ao iniciar operação manual';
    try {
      const data = await res.json();
      detail = data?.detail || data?.message || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function startRealTest(exchange = 'binance', config = {}) {
  return startManualOperation(exchange, config);
}

export async function stopReal(sessionId) {
  const res = await apiFetch(`${API_BASE}/real-trading/stop?session_id=${sessionId}`, { method: 'POST' });
  let data = null;
  try {
    data = await res.json();
  } catch (_) {}

  if (!res.ok) {
    const detail = data?.detail || data?.message || 'Falha ao parar real trading';
    throw new Error(detail);
  }
  return data || {};
}

export async function editRealSession(sessionId, config) {
  const res = await apiFetch(`${API_BASE}/real-trading/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    let detail = 'Falha ao editar sessão real';
    try {
      const data = await res.json();
      detail = data?.detail || data?.message || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchRealSessions() {
  const res = await apiFetch(`${API_BASE}/real-trading/sessions`);
  if (!res.ok) throw new Error('Falha ao buscar sessões reais');
  return res.json();
}

export async function deleteRealSession(sessionId) {
  const res = await apiFetch(`${API_BASE}/real-trading/sessions/${sessionId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Falha ao deletar sessão real');
  return res.json();
}

export async function closeAllRealPositions(sessionId) {
  const res = await apiFetch(`${API_BASE}/real-trading/${sessionId}/close-all`, { method: 'POST' });
  if (!res.ok) throw new Error('Falha ao fechar posições reais');
  return res.json();
}

export async function triggerRealManual(sessionId, { symbol } = {}) {
  const body = {};
  if (symbol) body.symbol = symbol;
  const res = await apiFetch(`${API_BASE}/real-trading/${sessionId}/manual-trigger`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = 'Falha ao disparar operação manual';
    try {
      const data = await res.json();
      detail = data?.detail || data?.message || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function pauseRealSession(sessionId) {
  return editRealSession(sessionId, { paused: true });
}

export async function resumeRealSession(sessionId) {
  return editRealSession(sessionId, { paused: false });
}

export async function validateRealApiKeys(exchange = 'binance') {
  const res = await apiFetch(`${API_BASE}/real-trading/validate-keys?exchange=${exchange}`);
  if (!res.ok) throw new Error('Falha ao validar chaves de API');
  return res.json();
}

export async function fetchRealLogs(params = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await apiFetch(`${API_BASE}/real-trading/logs?${query}`);
  if (!res.ok) throw new Error('Falha ao buscar logs da conta real');
  return res.json();
}

export async function fetchRealChartOperations({ exchange = 'binance', symbol, limitClosed = 20 } = {}) {
  // Motivo: o painel de operações da tela manual agora suporta visão global (todos os pares),
  // então o símbolo passa a ser opcional.
  const params = new URLSearchParams();
  params.append('exchange', exchange);
  if (symbol) params.append('symbol', symbol);
  params.append('limit_closed', String(limitClosed));
  const res = await apiFetch(`${API_BASE}/real-trading/chart-operations?${params.toString()}`);
  if (!res.ok) throw new Error('Falha ao buscar operações para o gráfico');
  return res.json();
}

export async function requestBotAIAnalysis(sessionId) {
  const res = await apiFetch(`${API_BASE}/real-trading/${sessionId}/ai-analyze`, {
    method: 'POST',
  });
  if (!res.ok) {
    let detail = 'Falha ao gerar análise IA';
    try { const d = await res.json(); detail = d?.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function applyBotAISuggestions(sessionId, suggestedConfig, analysisId) {
  const res = await apiFetch(`${API_BASE}/real-trading/${sessionId}/ai-apply`, {
    method: 'POST',
    body: JSON.stringify({ suggestedConfig, analysisId }),
  });
  if (!res.ok) {
    let detail = 'Falha ao aplicar sugestões';
    try { const d = await res.json(); detail = d?.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchBotAIAnalyses(sessionId, limit = 10) {
  const res = await apiFetch(`${API_BASE}/real-trading/${sessionId}/ai-analyses?limit=${limit}`);
  if (!res.ok) throw new Error('Falha ao buscar análises IA');
  return res.json();
}

export async function fetchRealOrderLogs(sessionId, { limit = 100, level = '', event = '' } = {}) {
  const params = new URLSearchParams({ limit });
  if (level) params.set('level', level);
  if (event) params.set('event', event);
  const res = await apiFetch(`${API_BASE}/real-trading/${sessionId}/order-logs?${params}`);
  if (!res.ok) throw new Error('Falha ao buscar logs de ordens');
  return res.json();
}

// ──────────────────────────────────────────────────────────────
// Estratégias Salvas
// ──────────────────────────────────────────────────────────────

export async function fetchStrategies() {
  const res = await apiFetch(`${API_BASE}/strategies`);
  if (!res.ok) throw new Error('Falha ao buscar estratégias');
  return res.json();
}

export async function saveStrategy(name, config) {
  const res = await apiFetch(`${API_BASE}/strategies`, {
    method: 'POST',
    body: JSON.stringify({ name, config }),
  });
  if (!res.ok) {
    let detail = 'Falha ao salvar estratégia';
    try { const d = await res.json(); detail = d?.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function deleteStrategy(id) {
  const res = await apiFetch(`${API_BASE}/strategies/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Falha ao deletar estratégia');
  return res.json();
}

// ──────────────────────────────────────────────────────────────
// Logs do Servidor
// ──────────────────────────────────────────────────────────────

export async function fetchServerLogs({ limit = 100, offset = 0, level = '', dateFrom = null, dateTo = null, search = '', module = '' } = {}) {
  const params = new URLSearchParams({ limit, offset });
  if (level) params.append('level', level);
  if (dateFrom) params.append('date_from', dateFrom);
  if (dateTo) params.append('date_to', dateTo);
  if (search) params.append('search', search);
  if (module) params.append('module', module);
  const res = await apiFetch(`${API_BASE}/server-logs?${params}`);
  if (!res.ok) throw new Error('Falha ao buscar logs do servidor');
  return res.json();
}

// ──────────────────────────────────────────────────────────────
// Configurações do Sistema (score thresholds etc.)
// ──────────────────────────────────────────────────────────────

export async function fetchSettings() {
  const res = await apiFetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error('Falha ao buscar configurações');
  return res.json();
}

export async function updateSetting(key, value) {
  const res = await apiFetch(`${API_BASE}/settings/${key}`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error(`Falha ao atualizar configuração ${key}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────────
// Configurações do Usuário (chaves de API por usuário)
// ──────────────────────────────────────────────────────────────

export async function requestScoreAIAnalysis(payload) {
  // Comentário de controle: dispara análise IA para o modo ativo do diagnóstico.
  const res = await apiFetch(`${API_BASE}/settings/score-ai/analyze`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = 'Falha ao analisar configurações com IA';
    try {
      const data = await res.json();
      detail = data?.detail || data?.message || detail;
    } catch (error) {
      void error;
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function applyScoreAISuggestions(analysisId) {
  // Comentário de controle: aplica recomendações persistidas pela análise selecionada.
  const res = await apiFetch(`${API_BASE}/settings/score-ai/apply`, {
    method: 'POST',
    body: JSON.stringify({ analysisId }),
  });
  if (!res.ok) {
    let detail = 'Falha ao aplicar sugestões de score';
    try {
      const data = await res.json();
      detail = data?.detail || data?.message || detail;
    } catch (error) {
      void error;
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchUserSettings() {
  const res = await apiFetch(`${API_BASE}/auth/settings`);
  if (!res.ok) throw new Error('Falha ao buscar configurações do usuário');
  return res.json();
}

export async function updateUserSetting(key, value) {
  const res = await apiFetch(`${API_BASE}/auth/settings/${key}`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error(`Falha ao atualizar configuração ${key}`);
  return res.json();
}

// ──────────────────────────────────────────────────────────────
// Blacklist Inteligente de Símbolos
// ──────────────────────────────────────────────────────────────

export async function fetchSymbolBlacklist() {
  const res = await apiFetch(`${API_BASE}/symbols/blacklist`);
  if (!res.ok) throw new Error('Falha ao buscar blacklist de símbolos');
  return res.json();
}

export async function clearSymbolBlacklist(symbol) {
  const res = await apiFetch(`${API_BASE}/symbols/blacklist/${encodeURIComponent(symbol)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    let detail = 'Falha ao remover blacklist';
    try { const d = await res.json(); detail = d?.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// ──────────────────────────────────────────────────────────────
// Geração de Bot via IA
// ──────────────────────────────────────────────────────────────

export async function generateBotConfigFromAI(reportId, { capital, leverage, exchange, operationMode } = {}) {
  const res = await apiFetch(`${API_BASE}/ai/generate-bot-config`, {
    method: 'POST',
    body: JSON.stringify({ reportId, capital, leverage, exchange, operationMode }),
  });
  if (!res.ok) {
    let detail = 'Falha ao gerar configuração de bot via IA';
    try { const d = await res.json(); detail = d?.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function analyzeMarketForBot(capital, leverage, exchange) {
  const res = await apiFetch(`${API_BASE}/ai/analyze-market-for-bot`, {
    method: 'POST',
    body: JSON.stringify({ capital, leverage, exchange }),
  });
  if (!res.ok) {
    let detail = 'Falha ao analisar mercado via IA';
    try { const d = await res.json(); detail = d?.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchBotAIConfigHistory(sessionId) {
  const res = await apiFetch(`${API_BASE}/real-trading/${sessionId}/ai-config-history`);
  if (!res.ok) {
    let detail = 'Falha ao carregar histórico de config IA';
    try { const d = await res.json(); detail = d?.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}
