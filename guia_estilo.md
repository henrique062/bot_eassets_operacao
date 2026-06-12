
---

## TEMA DA APLICAÇÃO (Dashboard Phoenix Bot) — DARK

> **IMPORTANTE:** o dashboard do Phoenix Bot (`bot_encryptos/frontend`) usa **tema ESCURO**. A paleta clara descrita no restante deste guia vale para landing pages / produtos claros; **dentro do dashboard, todas as telas (inclusive o Painel de Moedas) seguem o tema dark abaixo.** Os princípios (hierarquia, espaçamento múltiplo de 4, minimalismo, fonte) permanecem.

| Token              | Hex       | Uso                                            |
|--------------------|-----------|------------------------------------------------|
| Fundo da página    | #0f1117   | Body / fundo geral                             |
| Card / superfície  | #1a1d27   | Cards, tabelas, banners                        |
| Superfície 2       | #15171f   | Rodapés de tabela, inputs                      |
| Borda              | #2a2d3a   | Divisórias, bordas de card                     |
| Borda de linha     | #23262f   | Linhas de tabela                               |
| Texto título       | #f3f4f6   | Títulos / destaque                             |
| Texto corpo        | #d1d5db   | Texto padrão                                   |
| Texto secundário   | #9ca3af   | Subtextos                                      |
| Texto terciário    | #6b7280   | Labels, placeholders                           |
| Primária (accent)  | #6366f1   | Ações, seleção, links (hover #818cf8)          |
| Positivo / sucesso | #4ade80   | Valores positivos, OK                          |
| Negativo / erro    | #f87171   | Valores negativos, erro                        |
| Alerta             | #fbbf24   | RSI, avisos                                    |
| Roxo (T/OI forte)  | #c084fc   | Acumulação / SM focado                         |

---

## PRINCÍPIOS FUNDAMENTAIS

- Consistência: elementos de mesma função devem sempre ocupar o mesmo lugar e ter o mesmo estilo visual.
- Hierarquia Visual: use peso, cor e tamanho para indicar importância. Títulos têm mais destaque que descrições ou campos secundários.
- Regra dos Múltiplos de 4: TODOS os espaçamentos, tamanhos de componentes e bordas devem ser múltiplos de 4 (4, 8, 12, 16, 24, 32, 40, 48...).
- Abordagem Minimalista (Clean): evite ornamentos desnecessários. O design deve ser neutro, profissional e funcional.
- Padrões consistentes: pop-ups, modais e componentes de mesma função devem compartilhar a mesma estrutura visual (cabeçalho, ícone, mensagem, rodapé com ações).

---

## TIPOGRAFIA

Fonte exclusiva: Inter (Google Fonts).

### Hierarquia de Títulos (todos: Semibold / peso 600, cor Cinza 700 → #344054):

| Estilo   | Nome                        | Desktop | Mobile | Peso | Cor     |
|----------|-----------------------------|---------|--------|------|---------|
| H1       | Título Grande               | 32px    | 24px   | 600  | #344054 |
| H2       | Título                      | 24px    | 20px   | 600  | #344054 |
| H3       | Subtítulo / Título de Seção | 18px    | 16px   | 600  | #344054 |
| H4       | Título Pequeno / Label      | 14px    | 14px   | 600  | #344054 |

### Texto Padrão (Body):
- Tamanho: 14px
- Peso: Regular (400)
- Cor: Cinza 600 → #475467
- Labels de input usam H4 (semibold) para ganhar destaque sobre o body

---

## PALETA DE CORES COMPLETA

### Escala de Cinzas (base neutra de todos os projetos):

| Token     | Hex       | Uso principal                          |
|-----------|-----------|----------------------------------------|
| Cinza 0   | #FFFFFF   | Fundo de cards, modais e formulários   |
| Cinza 25  | #FCFCFD   | Superfícies levemente elevadas         |
| Cinza 50  | #F9FAFB   | Fundo da página                        |
| Cinza 100 | #F2F4F7   | Superfícies secundárias                |
| Cinza 200 | #EAECF0   | Divisórias leves / bordas fracas       |
| Cinza 300 | #D0D5DD   | Bordas de inputs, cards e componentes  |
| Cinza 400 | #98A2B3   | Placeholders e ícones desabilitados    |
| Cinza 500 | #667085   | Textos terciários / subtextos          |
| Cinza 600 | #475467   | Texto padrão / body                    |
| Cinza 700 | #344054   | Títulos e textos de destaque           |
| Cinza 800 | #1D2939   | Textos escuros / dark mode             |
| Cinza 900 | #101828   | Texto máximo contraste / quase preto   |

### Cores de Alerta (padrão universal para feedback):

| Cor            | Hex light | Hex base  | Uso                                     |
|----------------|-----------|-----------|-----------------------------------------|
| Verde 100      | #D1FADF   | —         | Fundo de toast de sucesso               |
| Verde 600      | #039855   | —         | Ícone/texto de sucesso, bordas verdes   |
| Amarelo 100    | #FEF0C7   | —         | Fundo de toast de alerta                |
| Laranja 600    | #DC6803   | —         | Ícone/texto de alerta                   |
| Vermelho 100   | #FEE4E2   | —         | Fundo de toast de erro                  |
| Vermelho 600   | #D92D20   | —         | Ícone/texto de erro, ações destrutivas  |

---

## COMPONENTES

### Inputs e Botões:
- Altura: 36px ou 40px
- Border-radius: 8px
- Borda: 1px solid #D0D5DD (Cinza 300)

### Campos de Data e Dropdowns (componentes custom — NÃO usar controles nativos):
Os controles nativos do navegador (`<select>` e `<input type=date>`) renderizam o popup pelo sistema operacional (cantos quadrados, seleção azul) e não respeitam o guia. Por isso usamos componentes próprios que renderizam o popup em React:

- **`Select`** (`components/ui/Select.tsx`): gatilho com altura 40px, raio 8px, borda #D0D5DD, seta Feather chevron-down (Cinza 400) que rotaciona ao abrir. Foco/aberto: borda primária + halo `0 0 0 3px var(--primary-50)`. Popup: fundo branco, borda Cinza 200, raio 8px, sombra padrão, padding 4px. Opção: raio 6px, hover Cinza 50; selecionada com fundo `--primary-50`, texto `--primary-700` e ícone de check `--primary-600`.
- **`DatePicker`** (`components/ui/DatePicker.tsx`): gatilho idêntico ao input (40px / raio 8px / borda #D0D5DD) com ícone de calendário Feather (Cinza 400); mostra a data em `dd/mm/aaaa` e emite ISO `yyyy-mm-dd`. Calendário: raio 12px, sombra padrão, navegação de mês com chevrons, dia selecionado em **verde esmeralda** (`--primary-600`), dia de hoje destacado em texto primário, rodapé com links "Limpar" e "Hoje".
- Ambos compartilham a mesma API dos inputs (`label`, `value`, `onChange(e => e.target.value)`, `error`, `disabled`) — o popup fecha ao clicar fora ou com `Esc`.
- `accent-color: var(--primary-600)` + `color-scheme: light` no `html` permanecem como fallback para quaisquer controles nativos remanescentes (checkbox/radio).

#### Popups dentro de modais — usar PORTAL (obrigatório):
Todo popup flutuante (dropdown, calendário, tooltip, menu) deve ser renderizado em **portal no `document.body`**, nunca como filho absoluto dentro do modal. Motivo: o modal tem `overflow-y: auto` para rolar conteúdo longo, e qualquer popup `position: absolute` interno é **cortado** pela área de rolagem (além de gerar scroll horizontal indesejado).
- Usar o componente `Popover` (`components/ui/Popover.tsx`): recebe `anchorRef`, posiciona com `position: fixed` via `getBoundingClientRect`, reposiciona em scroll/resize e **inverte para cima** (flip) quando não há espaço abaixo; faz clamp horizontal na viewport.
- `z-index`: overlay do modal = 1000; popups portados = 1100 (sempre acima).
- `matchWidth` para dropdowns (largura igual ao gatilho); `width`/`estimatedHeight` para popups de largura fixa (ex.: calendário 280px).

### Botões:
- Ação Principal: cor sólida com alto contraste (cor primária preenchida)
- Ação Secundária: fundo transparente ou borda suave (ghost/outline), visualmente mais apagado
- Ação Destrutiva: Vermelho 600 (#D92D20) como cor de fundo ou destaque
- Link de ação (ex: "Crie agora"): usar a cor primária, sem fundo

### Cards e Modais:
- Fundo: #FFFFFF (Cinza 0)
- Border-radius: 16px
- Borda opcional: 1px solid #EAECF0 (Cinza 200) — borda fraca
- Sombra: box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12)
  → X: 0 | Y: 8-12px | Blur: 24px | Opacidade: 88% (12% de preto)

#### Conteúdo não pode vazar (regra anti-overflow):
Modais com formulário usam grids de 2+ colunas. Para o conteúdo nunca estourar a largura (vazamento + scroll horizontal):
- Grids: usar `repeat(N, minmax(0, 1fr))` — NUNCA `1fr 1fr` puro (o `1fr` tem `min-width: auto` e não encolhe).
- Componentes de campo (`Input`, `Select`, `DatePicker`): wrapper sempre com `min-width: 0`; textos longos com `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`.
- Popups flutuantes nunca ficam dentro do modal — ver regra de PORTAL na seção de Data/Dropdowns.

### Estrutura padrão de Pop-ups e Modais:
- Cabeçalho com título + botão de fechar à direita
- Mensagem principal + mensagem secundária (menor e mais apagada)
- Rodapé: botão de voltar à esquerda (estilo ghost) + botão de ação à direita (alto contraste)
- Ação destrutiva: botão vermelho

#### Uso de ícone em modais (regra):
- Modais de **criação/edição (formulários)**: NÃO usar ícone com círculo central. Quando houver ícone, ele fica **inline na linha do título** (à esquerda do texto), com 20px e gap de 8px. Cor do ícone proporcional ao título.
- Ícone com **fundo circular centralizado** fica reservado apenas para **pop-ups de confirmação/alerta** (sucesso, aviso, exclusão), nunca em formulários.

---

## ESPAÇAMENTO (Regra de 4px — usar sempre múltiplos)

| Contexto                                  | Valor       |
|-------------------------------------------|-------------|
| Entre label e input (itens relacionados)  | 4px         |
| Gap entre ícone e texto no botão          | 8px         |
| Entre elementos dentro de uma seção       | 16px        |
| Entre blocos de conteúdo maiores          | 24px        |
| Padding interno de cards                  | 24–32px     |
| Margem lateral da página                  | 32px        |

Organização: use sempre containers com colunas e gap interno para controlar espaçamentos. NUNCA use layout fixo (posicionamento absoluto).

---

## ÍCONES

- Biblioteca: Feather Icons (minimalistas e profissionais)
- Proporção: o ícone deve ser proporcional ao tamanho do texto ao lado
- Gap ícone + texto: 8px
- Ícones em pop-ups: fundo circular claro + ícone escuro centralizado

---

## LAYOUT E RESPONSIVIDADE

- Fundo da página: Cinza 50 (#F9FAFB)
- Cards/formulários: branco (#FFFFFF) sobre o fundo cinza para criar contraste sutil
- Alinhamento: conteúdo centralizado horizontal e verticalmente nas telas de autenticação (login, cadastro)
- Mobile: reduzir tamanho dos títulos H1 e H2 conforme tabela de tipografia
- Containers: usar Coluna (Column) ou Linha (Row) — NUNCA layout fixo

---

## INSTRUÇÃO PADRÃO PARA GERAÇÃO DE TELAS

Sempre que gerar uma tela ou componente, siga estas diretrizes:
"Utilize abordagem minimalista (clean). Foque na hierarquia visual usando exclusivamente a fonte Inter. Mantenha todos os espaçamentos baseados na regra de múltiplos de 4px. Use a escala de cinzas (#F9FAFB fundo, #FFFFFF cards, #D0D5DD bordas, #475467 body, #344054 títulos) para neutros. Use cores de alerta universais: Verde #039855 (sucesso), Laranja #DC6803 (alerta), Vermelho #D92D20 (erro/ações destrutivas). Cards com border-radius 16px, sombra 0 8px 24px rgba(0,0,0,0.12). Inputs e botões com altura 40px e border-radius 8px. Ícones da biblioteca Feather Icons."