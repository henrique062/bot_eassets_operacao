# Ideias e Melhorias do Bot (Organizado)

Atualizado em: 2026-02-26

<!-- Comentário de organização: mantidos atalhos originais para facilitar navegação e contexto. -->
## Referências rápidas
#prompt
#dinheiro

[[Prompts inicio projeto]]
[[Melhorias Plataforma trader vorxia]]

## Comandos úteis
> Faça a mesma análise novamente, com atualização da planilha dos 3 bots em execução, analisando também todas as operações realizadas e validando se compensou as alterações sugeridas ou se ainda há algo para melhorar. Os dados do bot e histórico estão no banco de dados.

## Objetivo
Centralizar backlog, prioridades e diagnósticos do projeto `bot_taxa_cripto`, com foco em conta real, performance e qualidade de estratégia.

## Critérios de prioridade
- `P0` = risco financeiro, execução de ordens e inconsistência de dados.
- `P1` = aumento de performance/resultado e automações estratégicas.
- `P2` = UX/UI, visual e melhorias administrativas.

## P0 - Conta Real, Execução e Risco
- [ ] Corrigir bug grave: operação abrindo com mão maior do que o permitido.
- [ ] Corrigir delay de entrada (caso observado de ~12s mesmo com alvo de 2s após virada).
Anexo: ![[Pasted image 20260224103214.png]]
- [ ] Corrigir delay em operação manual para corretora.
- [ ] Garantir take profit opcional com ordem `limit` na operação real.
- [ ] Implementar stop loss configurável persistido no banco (por estratégia/bot).
- [ ] Implementar stop global (desligamento/proteção de risco total).
- [ ] Validar diferença de PnL apresentada no sistema (prints de 2026-02-23).
Anexo 1: ![[Pasted image 20260223133228.png]]
Anexo 2: ![[Pasted image 20260223165501.png]]
- [ ] Ajustar saldo atual para refletir dinamicamente posições em aberto.
- [ ] Exibir operações em aberto também na parte de histórico/lista inferior.
- [ ] Separar claramente lógica de operação normal por taxa e lógica counter-trade.
- [ ] Corrigir regra de sizing: valor em USD deve ser dividido sempre pela quantidade de moedas permitidas (independente das entradas válidas no ciclo).
- [ ] Adicionar campo de tempo nas operações (timestamp e tempo de permanência).
- [ ] Garantir logs de trailing stop e eventos de saída/ajuste de risco.
Anexo: ![[Pasted image 20260224235054.png]]
- [ ] Salvar logs de erro e logs de requests/respostas de ordens (Binance/Bybit).
Anexo: ![[Pasted image 20260223180038.png]]

## P1 - Estratégia, IA e Resultado
- [ ] Revisar métrica de score com base em operações reais já executadas.
- [ ] Criar relatório inteligente com métricas de moedas + análise IA e salvar histórico no banco.
- [ ] Permitir IA sugerir estratégia com saída estruturada para criar bot salvo automaticamente.
- [ ] Após fechamento de ciclo (ordens encerradas), permitir análise IA automática/manual para sugerir ajustes e persistir configuração no banco sem redeploy.
- [ ] Criar modo automático por expiração (ex.: moedas com settlement em 1h, removendo/adicionando conforme janela).
- [ ] Criar modo automático por força (usuário define quantidade de moedas + score mínimo).
- [ ] Permitir selecionar direção operacional: `long`, `short` ou `ambos`.
- [ ] Adicionar opção de peso por ativo (peso por funding rate ou % alocada personalizada).
- [ ] Criar estratégia "contra tendência na virada" (entrada antes da virada, ex.: 30s) com regras de TP/SL específicas.
- [ ] Revalidar configurações padrão das estratégias (normal/counter) usando histórico de DB + dados de mercado recentes.
- [ ] Analisar operações positivas/negativas desde 2026-02-25 e otimizar parâmetros de tempo/entrada/saída.
- [ ] Sempre analisar operações negativas para identificar se havia janela de reversão positiva.
- [ ] Criar regra para reduzir/excluir ativos com sequência de losses (cooldown/blacklist temporária).

## P1 - Gestão de Saída (Trailing, Break-even e Parcial)
- [ ] Implementar break-even automático (ex.: lucro >= 0.4% move SL para preço de entrada).
- [ ] Implementar TP parcial (ex.: 50% em +0.8%) e manter restante com trailing.
- [ ] Avaliar trailing em dois estágios (proteção inicial + captura de movimento longo).
- [ ] Avaliar combinação de trailing imediato + TP fixo.
- [ ] Definir conjunto padrão recomendado para testes controlados:
- [ ] `breakEvenAtPct = 0.4%`
- [ ] `partialTpPct = 0.8%`
- [ ] `partialTpSize = 50%`
- [ ] `trailingStartProfitPct = 1.5%`
- [ ] `trailingStopPct = 0.7%`

## P1 - Performance e Escalabilidade
- [ ] Investigar picos de CPU na VPS (coleta, processamento, render e loops assíncronos).
- [ ] Avaliar criação de views/materialized views para consultas muito frequentes.
- [ ] Otimizar atualização de valores em tela para atualizar apenas campos que mudam.
- [ ] Avaliar canal de preços em tempo real via SSE leve:
- [ ] Backend mantém WS da Binance no startup.
- [ ] Novo endpoint `/api/prices/events` com payload enxuto `{symbol: price}` a cada ~1s.
- [ ] Frontend atualiza apenas coluna de preço; funding segue polling (ex.: 60s).
- [ ] Revisar arquitetura de ingestão de dados para reduzir latência e carga sem perder precisão.

## P1 - Filtros e Qualidade de Dados
- [ ] Corrigir seletor/filtro de funding rate (há relato de falhas).
- [ ] Adicionar filtros rápidos fixos no dashboard: `1h`, `4h`, `8h`.
- [ ] Adicionar filtro de volatilidade (se viável).
- [ ] Adicionar filtro de operação por menor fund ratio.
- [ ] Adicionar filtro de fund ratio mínimo para validação de entrada.
- [ ] Salvar no histórico o fund ratio do momento exato da entrada da operação.

## P2 - UX/UI e Produto
- [ ] Corrigir menu mobile quebrado e ajustar responsividade geral.
- [ ] Melhorar renderização da análise IA (markdown bonito no frontend).
- [ ] Exibir, abaixo da análise IA, lista de moedas recomendadas em grid.
- [ ] Melhorar visual de ícones e layout geral.
- [ ] Substituir emojis por ícones consistentes em todo o sistema.
- [ ] Adicionar foto ao lado do nome do usuário.
- [ ] Mostrar quantidade de canais ao lado de instâncias.
- [ ] Permitir clicar no nome e abrir lista/grid de canais.
- [ ] Adicionar botão para desativar Bybit no frontend.
- [ ] Criar tela admin em Configurações com diagnóstico em tempo real do cálculo do score.

## P2 - Relatórios e Análises Visuais
- [ ] Relatório com operações abertas + banca total em jogo nos bots ativos.
- [ ] Investigar caso específico de operação com erro em relatório ("fazer análise porque esse deu errado").
Anexo: ![[Pasted image 20260221180431.png]]
- [ ] Página separada com projeção de resultado (incluindo preço atual), curva de crescimento e drawdown.
- [ ] Exportar planilha informativa após análises de performance/estratégia.

## Bugs e Pendências Pontuais
- [ ] "Copiar estratégia salva para o grid" não aplica todos os campos corretamente.
- [ ] Validar erro mostrado no print de 2026-02-25 16:27:21.
Anexo: ![[Pasted image 20260225162721.png]]
- [ ] Revisar estilo `.session-card-exchange` (tipografia e legibilidade).

## Itens Concluídos (histórico)
- [x] Tela de logs com histórico, bots e ações de copiar estratégia.
- [x] Salvar estratégias no banco e selecionar estratégia salva na criação de operação.
- [x] Botão para copiar estratégia a partir de bot em execução.
- [x] Estratégias focadas em maior funding rate.
- [x] Mudança de métricas anualizadas para base mensal.
- [x] Correção inicial de filtro fund rate (revalidar, há novo relato de falha).

## Solicitações amplas para auditoria (macro)
- [ ] Auditoria completa da aplicação com foco em conta real (erros, processos e segurança operacional).
- [ ] Revisão de banco de dados para consistência, desempenho e suporte às novas features.
- [ ] Definir presets lucrativos (editáveis) com base em análise do paper + real.
- [ ] Consolidar plano de execução por frentes: backend, banco, frontend, Python e UX/UI.

## Comandos úteis (dev local)
```bash
cd backend
python main.py

cd frontend
npm run dev
```

## Prompt útil para reanálise periódica
```text
Faça a mesma análise novamente, com atualização da planilha dos 3 bots em execução, analisando também todas as operações realizadas e validando se compensou as alterações sugeridas ou se ainda há algo para melhorar. Os dados do bot e histórico estão no banco de dados.
```

## Segurança
- Credenciais sensíveis não devem ficar neste arquivo.
- Manter chaves de API apenas em `.env` seguro.
- Se alguma chave já foi exposta, rotacionar imediatamente.
