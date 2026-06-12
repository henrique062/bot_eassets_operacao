# Automacao eAssets AI

Esta integracao abre `https://eassets.ai/panel` com Playwright, faz login, aciona o botao **Export for AI**, gera o JSON pelo botao **Copy**, valida o snapshot e salva no SQLite em `snapshots`.

## `.env` no projeto

O app carrega automaticamente o arquivo `.env` da raiz do projeto.

```env
EASSETS_EMAIL=seu-email
EASSETS_PASSWORD=sua-senha
EASSETS_INTERVAL_SECONDS=1800
EASSETS_AUTO_ENABLED=1
EASSETS_HEADLESS=1
```

O arquivo `.env` esta no `.gitignore` para nao ser versionado.

## Variaveis de ambiente opcionais

Se preferir sobrescrever pelo terminal antes de iniciar o Flask:

```powershell
$env:EASSETS_INTERVAL_SECONDS="1800"
```

O modo headless fica ativo por padrao. Para depurar vendo o navegador:

```powershell
$env:EASSETS_HEADLESS="0"
```

Para desativar a captura automatica no startup:

```powershell
$env:EASSETS_AUTO_ENABLED="0"
```

## Instalacao

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso

- Automatico: ao iniciar `python app.py`, a captura roda a cada 30 minutos se as credenciais existirem no ambiente.
- Manual: clique em **Capturar IA** no topo do dashboard.
- API manual: `POST /api/eassets/import`.
- Status: `GET /api/eassets/status`.

Se o site mudar os textos `Export for AI` ou `Copy`, ajuste os seletores em `eassets_scraper.py`.
