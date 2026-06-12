# Uso da Skill `analise-encryptos` e como rodar a aplicação

## Como rodar a aplicação (painel)

Pré-requisitos: Python 3 instalado. Dependência: Flask (`pip install flask`).

No PowerShell, dentro da pasta do projeto:

```powershell
cd "d:\3 - Projetos investimentos\Dash encryptos PHONIX Junho"
python app.py
```

Abre em **http://127.0.0.1:5000**. Pare com `Ctrl+C`.

Páginas (menu do topo):
- **Painel** (`/`) — ranking do último snapshot (score, setup, entrada, T/OI, banner do BTC)
- **✓ SETUP DE OURO** (`/setup`) — checklist de entrada por moeda + gate do BTC
- **📡 RADAR ACUMULAÇÃO** (`/radar`) — ranking por T/OI + persistência
- **🧠 ANÁLISES IA** (`/analises`) — análises da skill salvas no banco
- **★ TOPO RECORRENTE** (`/topo`) · **🗂 SNAPSHOTS** (`/snapshots`)

### Importar um scan novo
No painel, botão **＋ IMPORTAR JSON** → cola o conteúdo ou seleciona o arquivo
`eassets-panel-*.json` → **PROCESSAR**. Salva tudo no banco (`phoenix.db`) e abre o
painel daquele dia. Re-importar o mesmo scan (mesmo timestamp) atualiza, não duplica.

> A skill analisa o que está **no banco** (último snapshot importado). Importe o
> JSON novo ANTES de pedir a análise, senão analiso o scan antigo.

### Gerar painel estático (opcional, sem servidor)
```powershell
python gerar_painel.py
```
Gera `painel_phoenix.html` (abre offline com duplo-clique).

---

## Como usar a skill de análise

### 1. Slash command
```
/analise-encryptos
```
(pode reabrir o Claude Code se não aparecer ainda — skill nova é carregada no
início da sessão)

### 2. Linguagem natural — só pedir
Qualquer uma dessas dispara:
- "usa a skill analise-encryptos e analisa o último json"
- "roda a análise Encryptos e monta a lista"
- "analisa o último snapshot e me dá a lista ranqueada"
- "monta a lista de moedas pela metodologia"

### O que acontece ao receber
1. `python analise_dados.py` — prepara dados (BTC + candidatos + histórico)
2. Aplico o protocolo e monto a lista no chat (COMPRAR/OBSERVAR/EVITAR + fase + razão)
3. `python salvar_analise.py` — gravo no banco → aparece em **/analises**

### Variações úteis
- "analisa mas não salva no banco" → pulo o passo 3
- "analisa os top 40" → rodo `analise_dados.py 40` (mais candidatos)
- "compara com a análise de ontem" → puxo do banco e comparo vereditos

---

## Fluxo recomendado (resumo)
1. `python app.py` → abre o painel
2. **＋ IMPORTAR JSON** → processa o scan do dia
3. No chat: "usa a skill analise-encryptos e analisa o último json"
4. Vejo a lista no chat e ela fica salva em **🧠 ANÁLISES IA**
