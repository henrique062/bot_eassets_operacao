# Auditoria Técnica Completa — 2026-02-25

## Escopo e cobertura
- Escopo auditado integralmente: `backend/`, `frontend/`, `migrations/`, `docs/`, `skills/` e scripts de raiz (`*.py`/`*.sh`).
- Exclusões aplicadas conforme plano: `backend/.venv/`, `backend/**/__pycache__/`, `frontend/node_modules/`, `frontend/dist/`.
- Manifesto final auditado: **127 arquivos**.
- Cobertura: **100%** (`pending=0`).

## Metodologia executada
- Auditoria estática por linguagem (Python/JSX/SQL/CSS/JSON/MD/TXT/YAML).
- Validação de integridade no PostgreSQL em modo leitura (`SET default_transaction_read_only = on`).
- Validação de conectividade e relógio com APIs públicas Binance/Bybit (sem side effects).
- Checagens de padronização (line endings, trailing whitespace, artefatos versionados).

## Limitações de ambiente
- `node`/`npm` indisponíveis neste ambiente (`node: command not found`), portanto lint/build frontend não pôde ser executado.
- `pytest` não está instalado no venv backend (`No module named pytest`).

## Resumo executivo
- Foi confirmada uma combinação de riscos de **segurança**, **integridade operacional** e **manutenibilidade**.
- Há um bug de JSX que pode quebrar compilação em `RealTradingPage.jsx`.
- Banco está operacional e com snapshots recentes (coleta ativa), porém há inconsistência de lifecycle (`real_positions` em bots inativos).
- Há scripts legados de logs consultando tabelas inexistentes (`bot_logs`, `system_logs`) enquanto o padrão atual é `server_logs`.

## Achados por severidade

### Critical
1. **Credenciais hardcoded no código e fallback de conexão sensível**
- Evidência:
  - `backend/analyze_trades.py:14`
  - `backend/get_schema.py:9`
  - `backend/run_settings_migration.py:6`
  - `run_migration.py:9`
- Impacto: exposição de segredo, risco de comprometimento de banco.
- Recomendação: remover literals, centralizar leitura em variáveis de ambiente e rotacionar credenciais.

2. **Arquivo `.env` versionado no repositório**
- Evidência: `backend/.env:1`
- Impacto: vazamento direto de configuração sensível.
- Recomendação: remover do versionamento, adicionar ao `.gitignore`, rotacionar segredos.

3. **Falha de sintaxe JSX potencialmente bloqueante**
- Evidência: `frontend/src/components/RealTradingPage.jsx:1828`
- Trecho: fechamento incorreto `</ span>`.
- Impacto: risco de quebra de build/runtime no frontend.
- Recomendação: corrigir para `</span>` e validar com build/lint assim que Node estiver disponível.

### High
1. **Inconsistência de schema de logs em scripts legados**
- Evidência:
  - Migração cria `server_logs`: `migrations/20260224_add_server_logs.sql:4`
  - Scripts ainda leem `system_logs` e `bot_logs`:
    - `backend/query_logs.py:9`
    - `backend/query_logs.py:17`
    - `backend/query_psycopg.py:21`
    - `backend/query_psycopg.py:22`
- Evidência de banco: tabelas `bot_logs` e `system_logs` inexistentes.
- Impacto: erros em troubleshooting e scripts de suporte.
- Recomendação: alinhar scripts legados para `server_logs` ou descontinuar scripts obsoletos.

2. **Integridade operacional: posições em bots inativos**
- Evidência (query read-only): `positions_on_inactive_configs = 3`.
- Amostra:
  - `real_config.id=47` (`AWEUSDT TESTE`) com posição aberta.
  - `real_config.id=49` (`DUSDT TESTE`) com posição aberta.
  - `real_config.id=52` (`AWEUSDT TESTE`) com posição aberta.
- Impacto: estado de operação inconsistente (lifecycle vs posição real).
- Recomendação: rotina de reconciliação obrigatória ao parar bot; bloqueio de transição para `active=false` quando houver posições abertas não reconciliadas.

3. **`except: pass` / `except Exception: pass` em fluxo crítico de trading**
- Evidência:
  - `backend/real_trader.py:1610`
  - `backend/real_trader.py:1755`
  - `backend/real_trader.py:1831`
  - `backend/real_trader.py:1973`
- Impacto: falhas silenciosas em fechamento de conexão/ordem, reduzindo rastreabilidade.
- Recomendação: log estruturado + contexto do erro; evitar swallow total.

4. **SQL dinâmico em script utilitário com interpolação de identificadores/filtros**
- Evidência: `backend/query_psycopg.py:13`
- Impacto: risco de injeção se reutilizado fora de contexto controlado.
- Recomendação: restringir whitelists de tabela/coluna e evitar interpolar `query_filters` livres.

### Medium
1. **Arquitetura monolítica em módulos críticos**
- Evidência de tamanho/complexidade:
  - `backend/real_trader.py` (~2696 LOC)
  - `backend/routes.py` (~1307 LOC)
  - `frontend/src/components/RealTradingPage.jsx` (~2809 LOC)
- Impacto: alto custo de manutenção, maior risco de regressão.
- Recomendação: extrair serviços/handlers por domínio (execução, reconciliação, logs, UI submódulos).

2. **Múltiplos `except Exception` amplos e uso de `print()` em runtime**
- Evidência recorrente em `backend/main.py`, `backend/routes.py`, `backend/real_trader.py`, `backend/paper_trader.py`.
- Impacto: observabilidade e tratamento de falhas inconsistentes.
- Recomendação: padronizar logger estruturado, níveis e correlação por sessão/símbolo.

3. **Divergência de line endings e whitespace**
- Achados:
  - 6 arquivos com line ending misto (CRLF+LF), incluindo `backend/real_trader.py`, `backend/routes.py`, `frontend/src/components/RealTrading.jsx`.
  - 33 arquivos com trailing whitespace.
- Impacto: diffs ruidosos, revisão difícil, conflitos em merge.
- Recomendação: aplicar formatter/editorconfig e normalização em lote.

### Low
1. **Arquivos de saída/diagnóstico versionados**
- Exemplos: `backend/output*.txt`, `backend/db_diagnostic_report.txt`.
- Impacto: ruído de repositório.
- Recomendação: mover para artefatos locais e ignorar via `.gitignore`.

## Validação de dados (PostgreSQL read-only)

### Estado atual
- Tabelas centrais existentes: `funding_rate_snapshots`, `real_config`, `real_trades`, `real_positions`, `paper_config`, `paper_trades`, `paper_positions`, `server_logs`.
- Tabelas ausentes relevantes para scripts legados: `bot_logs`, `system_logs`.

### Métricas-chave coletadas
- Contagens:
  - `funding_rate_snapshots`: 111976
  - `real_config`: 25
  - `real_trades`: 89
  - `real_positions`: 4
  - `paper_trades`: 2329
  - `server_logs`: 207
- Integridade:
  - `orphan_real_trades`: 0
  - `orphan_real_positions`: 0
  - `positions_on_inactive_configs`: 3
  - `trailing_stop_negative_trades`: 4
- Recência:
  - último snapshot local observado: `2026-02-25T02:20:33.614831+00:00`
  - idade no momento da checagem: ~70s

## Validação APIs externas
- Endpoints testados com sucesso (`HTTP 200`):
  - Binance: `/fapi/v1/time`, `/fapi/v1/premiumIndex?symbol=BTCUSDT`
  - Bybit: `/v5/market/time`, `/v5/market/tickers?category=linear&symbol=BTCUSDT`
- Latência observada: ~354–430 ms.
- Clock skew observado: ~-605 ms (Binance), ~-584 ms (Bybit), dentro de faixa operacional para monitoramento.
- Conclusão: conectividade externa saudável e sem indício de defasagem de coleta no momento auditado.

## Backlog priorizado (ondas)

### Onda 1 — Segurança e integridade (imediato)
1. Remover segredos hardcoded e rotacionar credenciais.
2. Desversionar `.env` e revisar histórico de exposição.
3. Corrigir JSX inválido em `RealTradingPage.jsx:1828`.
4. Corrigir lifecycle de bots para impedir posições abertas em sessão inativa.

### Onda 2 — Runtime e observabilidade
1. Substituir `except ...: pass` por tratamento explícito com log estruturado.
2. Alinhar scripts de logs ao schema atual (`server_logs`) e aposentar consultas legadas.
3. Revisar SQL dinâmico utilitário com whitelists e validação estrita.

### Onda 3 — Qualidade e manutenção
1. Refatorar arquivos monolíticos (`real_trader.py`, `routes.py`, `RealTradingPage.jsx`).
2. Padronizar line endings e remover trailing whitespace.
3. Definir pipeline de lint/test/format para evitar regressões (frontend e backend).

## Artefatos técnicos gerados nesta auditoria
- `/tmp/audit_manifest_full.txt`
- `/tmp/audit_static_report.json`
- `/tmp/audit_db_report.json`
- `/tmp/audit_api_report.json`

## Conclusão
A plataforma está funcional em coleta e integração externa, mas precisa de correções imediatas em segurança, consistência de lifecycle e higienização de fluxo de erro para reduzir risco operacional.
