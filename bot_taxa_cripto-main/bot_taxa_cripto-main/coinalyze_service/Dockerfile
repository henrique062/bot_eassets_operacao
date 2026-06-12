FROM python:3.12-slim

WORKDIR /app

# Comentário de controle: instala apenas dependências do microserviço dedicado.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 8010

# Comentário de controle: health check simples para orquestração local/docker.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8010/health')" || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
