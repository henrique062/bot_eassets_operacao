# Frontend Agent — Memoria do Projeto

## Estrutura de Pastas
- `frontend/src/components/` — componentes React (FundingTable.jsx, etc.)
- `frontend/src/services/api.js` — todas as chamadas HTTP (apiFetch + funcoes exportadas)
- `frontend/src/App.jsx` — roteamento de paginas e gerenciamento de auth

## Convencoes de Codigo
- Componentes: JSX (nao TSX) — projeto usa JavaScript puro, sem TypeScript
- Icones: `react-icons/fa6` (FontAwesome 6)
- Sem emojis em texto de componentes (regra do projeto)
- `COLUMNS` em FundingTable.jsx e definido no escopo do modulo (fora do componente) — nao pode usar estado nele diretamente; adaptar labels dinamicos no render do `<thead>`

## Padroes de Fetch
- `apiFetch()` em `api.js` injeta Bearer token e redireciona em 401
- Todos os parametros de query via `URLSearchParams`
- `loadData` e um `useCallback` com dependencias explicitas — adicionar novos params de estado como dependencia ao modificar

## Scoring Mode (FundingTable)
- Estado `scoringMode`: `'harvesting'` | `'counter_trend'`
- Enviado ao backend como `scoring_mode` via query param em `/api/funding-rates`
- Breakdown harvesting: `{apy, volume, interval, consistency}`
- Breakdown counter_trend: `{extremity, persistence, volume, volatility_bonus}`
- Toggle visual: dois botoes estilo tab (verde para harvesting, roxo #8b5cf6 para counter_trend)
- Badge de modo ativo no header da coluna Score (renderizado no `<thead>` dentro do componente)

## Dependencias Principais
- React 19 + Vite
- react-icons/fa6
- Sem bibliotecas de UI (estilos proprios via CSS vars: --accent-green, --border-color, --bg-secondary, --text-secondary)
