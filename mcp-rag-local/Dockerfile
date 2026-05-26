FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -y \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY src/ ./src/

RUN uv sync --no-editable

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_DISABLE_XET=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HOME=/app/.hf_cache \
    PORT=8002 \
    RAG_STORE_PATH=/app/data/rag_store.json

# Папка для персиста (монтируется как volume)
RUN mkdir -p /app/data /app/.hf_cache

EXPOSE 8002

CMD ["uv", "run", "python", "-m", "src.server"]
