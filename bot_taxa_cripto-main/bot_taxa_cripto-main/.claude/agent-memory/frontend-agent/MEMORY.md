# Frontend Agent Memory — bot_taxa_cripto

## Estrutura do Projeto

- Framework: React (JSX, sem TypeScript) + Vite
- Pasta principal: `d:\3 - Projetos investimentos\bot_taxa_cripto\frontend\src\`
- Componentes: `frontend/src/components/`
- Serviços de API: `frontend/src/services/api.js`
- Estilos globais: `frontend/src/index.css`

## Componentes Principais

- `PaperTradingPage.jsx` — página principal de paper trading com cards de sessões ativas/inativas e modal de histórico
  - Sub-componentes: `ActiveSessionCard`, `SessionCard`, `SessionHistoryModal`
  - Usa SSE (`EventSource`) para atualizar sessões ativas em tempo real
  - Usa `setInterval(loadData, 30000)` para sessões históricas (inativas)
  - `loadData` é chamado manualmente após ações do usuário (stop, delete, edit, closeAll)

## Padrões de Dados

- SSE endpoint: `/api/paper-trading/events` — payload JSON com campo `sessions`
- REST: `/api/paper-trading` — retorna `{ sessions, active, config, balance, positions, totalTrades, trades, pnl, pnlPct }`
- Proxy Vite lida com rotas `/api/*` — usar paths relativos no frontend

## Padrão SSE Adotado

```js
useEffect(() => {
    loadData(); // mount inicial
    const interval = setInterval(loadData, 30000); // histórico

    let es = null;
    let retryTimer = null;
    const connect = () => {
        es = new EventSource('/api/paper-trading/events');
        es.onmessage = (event) => { /* atualiza activeSessions */ };
        es.onerror = () => { es.close(); retryTimer = setTimeout(connect, 3000); };
    };
    connect();
    return () => { clearInterval(interval); es?.close(); if (retryTimer) clearTimeout(retryTimer); };
}, []); // sem dependências
```

## Componentes Adicionados/Modificados

- `RealTrading.jsx` — formulário de conta real
  - Contém `PRESET_STRATEGIES` (4 cards de estratégias pré-definidas) no topo do arquivo
  - Cards de preset renderizados em `.preset-strategies-grid` (2x2 desktop, 1 coluna mobile)
  - Estado `selectedPreset` rastreia qual preset está selecionado (borda azul)
  - Botão "💾 Salvar Estratégia" usa `saveStrategy(name, config)` da api.js
  - Após salvar, recarrega `savedStrategies` automaticamente

## Design System — Classes CSS Relevantes

- Menu mobile: `.hamburger-btn` (display:none desktop, flex mobile), `.header-right.menu-open` (drawer lateral)
- Overlay menu: `.menu-overlay` (display:none desktop, block mobile via media query)
- Preset cards: `.preset-strategies-grid`, `.preset-card`, `.preset-card.selected`, `.preset-badge--recommended/popular/danger/expert`
- Salvar estratégia: `.save-strategy-section`, `.save-strategy-btn`, `.save-strategy-input-row`, `.save-strategy-feedback.success/error`
- Media queries: bloco principal em `@media (max-width: 768px)` com `config-row` empilhado, `modal-content` full-screen, `stats-grid` 2 colunas
- `index.css` tem ~4700 linhas — vários blocos `@media (max-width: 768px)` separados por seção, isso é intencional

## Padrão de Overlay do Menu Mobile

- O overlay (`.menu-overlay`) é renderizado condicionalmente no React: `{menuOpen && <div className="menu-overlay" onClick={() => setMenuOpen(false)} />}`
- No CSS: `display: none` por padrão, `display: block` apenas dentro de `@media (max-width: 768px)`
- Isso garante que o overlay não apareça em desktop mesmo se `menuOpen` for `true`

## Preferências do Usuário

- Comunicação sempre em português brasileiro
- Não alterar nada além do que foi explicitamente solicitado
- Revisar e remover arquivos antigos/redundantes quando pertinente
- Fazer resumo de alterações críticas ou grandes
