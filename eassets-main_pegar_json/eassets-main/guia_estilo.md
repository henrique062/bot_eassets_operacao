
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

### Estrutura padrão de Pop-ups e Modais:
- Cabeçalho com título centralizado + botão de fechar à direita
- Ícone com fundo circular (cor clara) no centro
- Mensagem principal + mensagem secundária (menor e mais apagada)
- Rodapé: botão de voltar à esquerda (estilo ghost) + botão de ação à direita (alto contraste)
- Ação destrutiva: botão vermelho

---

## ESPAÇAMENTO (Regra de 4px — usar sempre múltiplos)

| Contexto                                  | Valor       |
|-------------------------------------------|-------------|
| Entre label e input (itens relacionados)  | 4px         |
| Gap entre ícone e texto no botão          | 8px         |
| Entre elementos dentro de uma seção       | 16px        |
| Entre blocos de conteúdo maiores          | 24px        |
| Padding interno de cards                  | 16–32px     |
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