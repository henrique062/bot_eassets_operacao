# Deploy Docker na VPS

## 1. Preparar `.env`

Na VPS, copie o exemplo e preencha as credenciais:

```bash
cp .env.example .env
nano .env
```

Campos principais:

```env
EASSETS_EMAIL=seu-email
EASSETS_PASSWORD=sua-senha
DATA_DIR=/app/data
EASSETS_INTERVAL_SECONDS=1800
EASSETS_AUTO_ENABLED=1
EASSETS_HEADLESS=1
```

## 2. Subir o container

```bash
docker compose up -d --build
```

O dashboard ficará em:

```text
http://IP_DA_VPS:5050
```

## 3. Verificar logs e saúde

```bash
docker compose logs -f phoenix-dashboard
docker compose ps
curl http://127.0.0.1:5050/api/health
curl http://127.0.0.1:5050/api/eassets/status
```

## 4. Banco persistente

O SQLite fica no volume Docker `phoenix_data`, em:

```text
/app/data/dashboard.db
```

O caminho pode ser configurado de duas formas:

```env
DATA_DIR=/app/data
```

ou, se quiser apontar diretamente o arquivo:

```env
DASHBOARD_DB=/app/data/dashboard.db
```

Se ambos existirem, `DASHBOARD_DB` tem prioridade.

## 5. Backup rápido do banco

```bash
docker compose exec phoenix-dashboard cp /app/data/dashboard.db /app/data/dashboard-backup.db
docker cp phoenix-dashboard:/app/data/dashboard-backup.db ./dashboard-backup.db
```

## 6. Atualizar versão na VPS

```bash
docker compose down
docker compose up -d --build
```

## Observações

- O container usa Gunicorn com 1 worker para evitar duplicar os agendadores internos.
- O Chromium do Playwright já vem no `Dockerfile`, pela imagem oficial `mcr.microsoft.com/playwright/python:v1.44.0-jammy`.
- A captura eAssets roda a cada 30 minutos por padrão e também pode ser acionada pelo botão **Capturar IA**.
- Para usar proxy reverso, aponte Nginx/Caddy para `127.0.0.1:5050`.
