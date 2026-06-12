FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy
WORKDIR /app
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY bot_encryptos/python_api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY bot_encryptos/python_api/ ./
COPY gerar_painel.py ./gerar_painel.py
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
