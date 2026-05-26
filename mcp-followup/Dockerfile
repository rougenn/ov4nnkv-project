# Используем официальный образ Python 3.11 slim для минимального размера
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем uv
RUN pip install --no-cache-dir uv

# Копируем файлы конфигурации сначала для лучшего кеширования Docker слоев
COPY pyproject.toml README.md ./

# Копируем исходный код приложения
COPY src/ ./src/

# Создаем uv.lock если его нет и устанавливаем зависимости
RUN uv sync --no-editable

# Создаем непривилегированного пользователя для безопасности
RUN useradd --create-home --shell /bin/bash --uid 1000 mcp && \
    chown -R mcp:mcp /app

# Переключаемся на непривилегированного пользователя
USER mcp

# Открываем порт для MCP сервера
EXPOSE 8000

# Устанавливаем переменные окружения для оптимальной работы Python
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    UV_SYSTEM_PYTHON=1 \
    PORT=8000

# Команда запуска сервера
CMD ["uv", "run", "python", "src/server.py"]
