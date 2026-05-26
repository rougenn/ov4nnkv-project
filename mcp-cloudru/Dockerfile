# Используем официальный образ Python 3.11 slim
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости и uv
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Копируем файлы конфигурации
COPY pyproject.toml README.md ./

# Копируем исходный код
COPY src/ ./src/

# Устанавливаем зависимости
RUN uv sync --no-editable

# Создаем непривилегированного пользователя
RUN useradd --create-home --shell /bin/bash --uid 1000 mcp && \
    chown -R mcp:mcp /app

# Переключаемся на непривилегированного пользователя
USER mcp

# Открываем порт
EXPOSE 8000

# Переменные окружения
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    UV_SYSTEM_PYTHON=1 \
    PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Команда запуска
CMD ["uv", "run", "python", "src/server.py"]





