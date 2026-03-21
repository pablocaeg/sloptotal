FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt psutil

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

RUN useradd -r -s /bin/false sloptotal && \
    mkdir -p /app/models /app/data && \
    chown -R sloptotal:sloptotal /app/models /app/data

USER sloptotal

ENV HF_HOME=/app/models
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
