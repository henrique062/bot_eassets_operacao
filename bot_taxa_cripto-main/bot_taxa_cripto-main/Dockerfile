# ===== Stage 1: Build Frontend =====
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

# Copiar package files e instalar deps
COPY frontend/package*.json ./
RUN npm ci

# Copiar código e buildar
COPY frontend/ ./
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN npm run build

# ===== Stage 2: Backend + Serve =====
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências Python
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copiar backend
COPY backend/ ./

# Copiar build do frontend
COPY --from=frontend-build /app/frontend/dist ./static

# Porta
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/stats?exchange=binance')" || exit 1

# Rodar
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
