import { useEffect, useState } from 'react';
import {
  LuBot,
  LuChartLine,
  LuCircleDot,
  LuClipboardList,
  LuLayoutDashboard,
  LuLogOut,
  LuSettings2,
  LuTarget,
  LuZap,
} from 'react-icons/lu';
import StatsCards from './components/StatsCards';
import FundingTable from './components/FundingTable';
import HistoryModal from './components/HistoryModal';
import StrategyPanel from './components/StrategyPanel';
import SmartReport from './components/SmartReport';
import BacktestPanel from './components/BacktestPanel';
import RealTradingPage from './components/RealTradingPage';
import ManualOperationPage from './components/ManualOperationPage';
import SettingsPage from './components/SettingsPage';
import ScoreDiagnosticsPage from './components/ScoreDiagnosticsPage';
import LogsPage from './components/LogsPage';
import LoginPage from './components/LoginPage';
import CoinalyzePage from './components/CoinalyzePage';
import binanceLogo from './assets/binance.svg';
import bybitLogo from './assets/bybit.png';
import './index.css';

const EXCHANGES = [
  { id: 'binance', label: 'Binance', logo: binanceLogo },
  { id: 'bybit', label: 'Bybit', logo: bybitLogo },
];

const PAGE_STORAGE_KEY = 'app.currentPage';
const AUTH_TOKEN_KEY = 'auth.token';
const AUTH_USER_KEY = 'auth.user';
// Comentário de controle: adiciona nova tela operacional Coinalyze no roteamento local do App.
const VALID_PAGES = new Set(['home', 'strategies', 'ai', 'backtest', 'coinalyze', 'real-trading', 'manual-operation', 'settings', 'logs', 'score-diagnostics']);

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem(AUTH_TOKEN_KEY) || null);
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem(AUTH_USER_KEY) || 'null'); } catch { return null; }
  });

  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [exchange, setExchange] = useState('binance');
  const [prefilledStrategy, setPrefilledStrategy] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [page, setPage] = useState(() => {
    if (typeof window === 'undefined') return 'home';
    const saved = window.localStorage.getItem(PAGE_STORAGE_KEY);
    return VALID_PAGES.has(saved) ? saved : 'home';
  });

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(PAGE_STORAGE_KEY, page);
    }
  }, [page]);

  const handleLogin = (newToken, newUser) => {
    localStorage.setItem(AUTH_TOKEN_KEY, newToken);
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(newUser));
    setToken(newToken);
    setUser(newUser);
  };

  const handleLogout = () => {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
    setToken(null);
    setUser(null);
    setPage('home');
  };

  const handleCopyStrategy = (config) => {
    setPrefilledStrategy(config);
    setPage('real-trading');
    setMenuOpen(false);
  };

  const navigateTo = (p) => {
    setPage(p);
    setMenuOpen(false);
  };

  if (!token) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="app">
      <header className="app-header">
        {/* Botão hamburguer — ao lado esquerdo no mobile */}
        <button
          className={`hamburger-btn ${menuOpen ? 'open' : ''}`}
          onClick={() => setMenuOpen(o => !o)}
          aria-label="Menu"
        >
          <span /><span /><span />
        </button>

        <div className="header-left">
          <div className="logo">
            <img src="/logo-full.svg" alt="Crypto Funding Rates" className="logo-image" />
          </div>
        </div>

        {/* Overlay para fechar o menu ao clicar fora */}
        {menuOpen && (
          <div
            className="menu-overlay"
            onClick={() => setMenuOpen(false)}
            onKeyDown={(e) => { if (e.key === 'Escape' || e.key === 'Enter') setMenuOpen(false); }}
            role="button"
            tabIndex={0}
            aria-label="Fechar menu"
          />
        )}

        <div className={`header-right ${menuOpen ? 'menu-open' : ''}`}>
          <button
            className={`nav-btn ${page === 'home' ? 'active' : ''}`}
            onClick={() => navigateTo('home')}
          >
            <LuLayoutDashboard className="nav-btn-icon" />
            Dashboard
          </button>
          <button className={`nav-btn ${page === 'strategies' ? 'active' : ''}`} onClick={() => navigateTo('strategies')}>
            <LuTarget className="nav-btn-icon" />
            Estratégias
          </button>
          <button className={`nav-btn ${page === 'ai' ? 'active' : ''}`} onClick={() => navigateTo('ai')}>
            <LuBot className="nav-btn-icon" />
            Análise IA
          </button>
          <button className={`nav-btn ${page === 'backtest' ? 'active' : ''}`} onClick={() => navigateTo('backtest')}>
            <LuChartLine className="nav-btn-icon" />
            Backtest
          </button>
          <button className={`nav-btn ${page === 'coinalyze' ? 'active' : ''}`} onClick={() => navigateTo('coinalyze')}>
            <LuChartLine className="nav-btn-icon" />
            Coinalyze
          </button>
          <button
            className={`nav-btn nav-btn--real ${page === 'real-trading' ? 'active' : ''}`}
            onClick={() => navigateTo('real-trading')}
          >
            <LuCircleDot className="nav-btn-icon" />
            Conta Real
          </button>
          <button
            className={`nav-btn ${page === 'manual-operation' ? 'active' : ''}`}
            onClick={() => navigateTo('manual-operation')}
          >
            <LuZap className="nav-btn-icon" />
            Operação Manual
          </button>
          <button
            className={`nav-btn ${page === 'logs' ? 'active' : ''}`}
            onClick={() => navigateTo('logs')}
          >
            <LuClipboardList className="nav-btn-icon" />
            Logs
          </button>
          <button
            className={`nav-btn ${page === 'settings' ? 'active' : ''}`}
            onClick={() => navigateTo('settings')}
          >
            <LuSettings2 className="nav-btn-icon" />
            Config.
          </button>

          <div className="header-right-bottom">
            <div className="exchange-selector">
              {EXCHANGES.map(ex => (
                <button
                  key={ex.id}
                  className={`exchange-btn ${exchange === ex.id ? 'active' : ''}`}
                  onClick={() => setExchange(ex.id)}
                >
                  <img src={ex.logo} alt={ex.label} className="exchange-logo" />
                  {ex.label}
                </button>
              ))}
            </div>
            <div className="live-badge">
              <span className="live-dot" />
              LIVE
            </div>
            <button className="logout-btn" onClick={handleLogout} title={`Sair (${user?.email})`}>
              <LuLogOut className="logout-btn-icon" />
              Sair
            </button>
          </div>
        </div>
      </header>

      {/* Telas ricas em dados (Dashboard, Manual, Score) ganham contêiner mais largo */}
      <main className={`app-main ${['manual-operation', 'score-diagnostics', 'coinalyze'].includes(page) ? 'app-main--wide' : ''}`}>
        {page === 'score-diagnostics' ? (
          <ScoreDiagnosticsPage exchange={exchange} user={user} onBack={() => navigateTo('settings')} />
        ) : page === 'settings' ? (
          <SettingsPage exchange={exchange} user={user} onNavigate={navigateTo} />
        ) : page === 'logs' ? (
          <LogsPage onCopyStrategy={handleCopyStrategy} />
        ) : page === 'coinalyze' ? (
          <CoinalyzePage exchange={exchange} />
        ) : page === 'real-trading' ? (
          <RealTradingPage
            exchange={exchange}
            prefilledConfig={prefilledStrategy}
            onClearPrefilled={() => setPrefilledStrategy(null)}
          />
        ) : page === 'manual-operation' ? (
          <ManualOperationPage exchange={exchange} />
        ) : page === 'strategies' ? (
          <StrategyPanel />
        ) : page === 'ai' ? (
          <SmartReport exchange={exchange} />
        ) : page === 'backtest' ? (
          <BacktestPanel exchange={exchange} />
        ) : (
          <>
            <StatsCards exchange={exchange} />
            <FundingTable exchange={exchange} onSelectSymbol={setSelectedSymbol} />
          </>
        )}
      </main>

      {selectedSymbol && (
        <HistoryModal
          symbol={selectedSymbol}
          exchange={exchange}
          onClose={() => setSelectedSymbol(null)}
        />
      )}

      <footer className="app-footer">
        <p>Dados obtidos da API pública da {exchange === 'binance' ? 'Binance' : 'Bybit'} · Atualização a cada 60s · Horários em GMT-3</p>
      </footer>
    </div>
  );
}
