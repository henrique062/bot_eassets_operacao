# 🚀 Bot de Taxa de Criptomoedas (Funding Rates Bot & Dashboard)

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB)](https://reactjs.org/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

**Dashboard de Funding Rates** interativo para contratos perpétuos de criptomoedas das principais exchanges (Binance e Bybit). O projeto inclui análise de oportunidades potencializada por Inteligência Artificial (Google Gemini), sistema de Paper trading, engine completo de Backtesting, algoritmos de scoring avançados para risco e alertas via Telegram.

---

## 📋 Sumário

- [Recursos Principais](#-recursos-principais)
- [Arquitetura do Projeto](#-arquitetura-do-projeto)
- [Tecnologias Utilizadas](#-tecnologias-utilizadas)
- [Como Executar o Projeto](#-como-executar-o-projeto)
  - [Pré-requisitos](#pré-requisitos)
  - [Usando Docker (Recomendado)](#usando-docker-recomendado)
  - [Execução Local (Desenvolvimento)](#execução-local-desenvolvimento)
- [Variáveis de Ambiente](#-variáveis-de-ambiente)
- [Rotas Principais da API](#-rotas-principais-da-api)
- [Contribuindo](#-contribuindo)

---

## ✨ Recursos Principais

- **📊 Dashboard em Tempo Real:** Acompanhamento dinâmico e em tempo real das taxas de fundings de todos os pares nas exchanges integradas.
- **🤖 Integração com IA (Geimini):** Assistente integrado inteligente que analisa oportunidades de trade com base nos dados de mercado, fornecendo relatórios detalhados na tela do analista.
- **🥇 Scoring Inteligente:** Algoritmo que classifica ativos (0 a 100) com base no risco/retorno, magnitude de pagamento de fundos, volatilidade (com veto automático >35%), volume de liquidez (veto automático <$2M) e urgência da janela de settlement.
- **💼 Paper Trading:** Simulador interativo que roda assincronamente e mantem o histórico vivo no Postgres persistido contra restarts da aplicação.
- **🔄 Backtester Nativo:** Engine histórico completo contendo modo `normal` (com variação real dos candlesticks) e modo de alta agilidade `sniping`, considerando devidamente custos de transação taker e maker.
- **📱 Alertas no Telegram:** Alertas e rotinas periódicas de oportunidades, integrado em microsserviço separado.

---

## 🏗 Arquitetura do Projeto

O sistema é construído sobre uma base sólida, desenhado em múltiplos diretores de domínio:

- **Backend (`/backend`)**: API em FastAPI com alta concorrência assíncrona baseada na biblioteca `asyncpg` e pooling connection. É o coração do algoritmo (verificação de scoring, chamadas ao Gemini para NLP, sync de banco de dados do simulador e exchanges externas).
- **Frontend (`/frontend`)**: Interface Web rápida em React + Vite. Fica responsável pela comunicação de rotas API e desenha gráficos elegantes via _Lightweight Charts_ para o usuário final. Modulo SPA.
- **Telegram Bot (`/telegram_alert_bot`)**: Um serviço passivo que escuta gatilhos em banco ou triggers de tempos em tempos e envia broadcasts no grupo informando insights relevantes e taxas altas para settlement.

---

## 💻 Tecnologias Utilizadas

**Frontend:**

- [React 19](https://react.dev/) / ReactDOM
- [Vite](https://vitejs.dev/) (Build pipeline leve e ágil)
- [Lightweight Charts](https://tradingview.github.io/lightweight-charts/) (Visualização financeira)
- [TailwindCSS](https://tailwindcss.com/) / Componentes Flex/Grid Modernos

**Backend / Ops:**

- [Python 3.9+](https://www.python.org/)
- [FastAPI](https://fastapi.tiangolo.com/) & Uvicorn (Runtime ASGI)
- [PostgreSQL](https://www.postgresql.org/) + `asyncpg`
- Serviços: Cloud AI via [Google Gemini API]
- [Docker](https://www.docker.com/) e Docker Compose

---

## 🚀 Como Executar o Projeto

### Pré-requisitos

- [Node.js](https://nodejs.org/) (Para testar o frontend manualmente)
- [Python 3.9+](https://www.python.org/) (Para rodar o core backend)
- [Docker](https://www.docker.com/) e [Docker Compose](https://docs.docker.com/compose/)

### 🐳 Usando Docker (Recomendado)

Em ambiente de desenvolvimento unificado e produção, utilize Docker para rodar API backend e o alerta bot de fora da caixa.

1. Clone The Repositório

```bash
git clone https://github.com/seu-user/bot_taxa_cripto.git
cd bot_taxa_cripto
```

2. Crie na raiz o arquivo `.env` preenchido com suas chaves (use o exemplo de vars abaixo).

3. Rode os contêineres:

```bash
docker-compose up -d --build
```

> Obs: A API estará disponível no seu localhost na porta `8000`.

### 💻 Execução Local (Desenvolvimento Separado)

Para estender a aplicação mais rapidamente sem precisar rebuildar o Docker.

**1. Rodando o Backend (API REST + Socket)**

```bash
cd backend
pip install -r requirements.txt
python main.py
# ou alternativamente: uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

_- O Swagger/Docs ficará na URL: `http://localhost:8000/docs`_

**2. Rodando o Frontend (Painel React)**

```bash
cd frontend
npm install
npm run dev
```

_- Acesso local em `http://localhost:5173/` (porta padrão do Vite)._

---

## 🔐 Variáveis de Ambiente

Para o perfeito funcionamento do sistema, defina no arquivo `backend/.env` (ou na raiz caso utilize docker) as seguintes configurações:

```ini
# Chave Google AI (Google Gemini - Essencial para /api/ai-analysis)
GEMINI_API_KEY=sua_chave_aqui
GEMINI_MODEL=gemini-3-flash-preview

# Banco PostgreSQL (Requisito obrigatório de pool assíncrono)
DATABASE_URL=postgres://user:pass@host:5432/vorxia?sslmode=disable

# Alertas via Telegram
TELEGRAM_BOT_TOKEN=token_do_canal_ou_bot
TELEGRAM_CHAT_ID=id_do_grupo_ou_user_destinatario
```

---

## 📡 Rotas Principais da API

Todas as rotas consumíveis estão no prefixo `/api` no servidor Backend:

| Endpoint                              |  Metódos   | Descrição                                                |
| ------------------------------------- | :--------: | -------------------------------------------------------- |
| `/api/funding-rates`                  |   `GET`    | Lista as taxas, avalia scoring em tempo real             |
| `/api/ai-analysis`                    |   `GET`    | Análise do painel pelas redes neurais Gemini             |
| `/api/funding-rates/{symbol}/history` |   `GET`    | Histórico linear do valor de uma moeda                   |
| `/api/funding-rates/{symbol}/klines`  |   `GET`    | Trilha de candle e variação de mercado da moeda          |
| `/api/backtest`                       |   `GET`    | Endpoints de backtest assíncronos das estratégias        |
| `/api/paper-trading`                  | `GET/POST` | Cria, inicializa ou encerra sessões de simulação virtual |

---

## 🤝 Contribuindo

Pull requests são sempre bem-vindos! Para mudanças importantes, abra primeiramente uma issue para discutir sobre o que você gostaria de mudar.

1. Faça um _fork_ deste repositório
2. Crie uma branch com a sua nova feature: `git checkout -b minha-feature`
3. Commite as suas alterações respeitando padrão convencional: `git commit -m 'feat: minha nova rotina'` (**Apenas em Português-BR**)
4. Faça _push_ na branch: `git push origin minha-feature`
5. Envie seu _Pull Request_.

<br/>
<p align="center">Desenvolvido pensando em performance, agilidade no trading e interface amigável 🚀</p>
