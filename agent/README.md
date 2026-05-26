# Meeting Assistant Agent

AI-агент для работы с корпоративными созвонами на базе LangChain + A2A.

## Возможности

- 📹 Подключение к созвонам для записи и транскрибации (Follow-Up)
- 📝 Получение транскрипций завершённых созвонов
- 📅 Создание встреч в Google Calendar
- 🔍 Поиск по истории созвонов через Managed RAG

## Технологии

- LangChain — агентная логика (tools / scratchpad)
- A2A SDK — протокол для общения с клиентами (telegram-bot, demo-app)
- MCP — подключение Follow-Up / Google Calendar / RAG как инструментов
- LLM — любой OpenAI-совместимый провайдер (по умолчанию OpenRouter)

## Запуск

```bash
cp .env.example .env  # подставьте LLM_API_KEY и URL'ы MCP
uv run python -m src.start_a2a
```

Или через Docker:

```bash
docker build -t meeting-assistant-agent:latest .
docker run -p 10000:10000 --env-file .env meeting-assistant-agent:latest
```

## Smoke-проверка LLM

```bash
uv run python scripts/test_llm_api.py
```

## Переменные окружения

См. `.env.example`. Ключевые:
- `LLM_API_BASE` (по умолчанию `https://openrouter.ai/api/v1`)
- `LLM_API_KEY` — ключ OpenRouter (`sk-or-…`) или другого OpenAI-совместимого API
- `LLM_MODEL` (по умолчанию `openai/gpt-4o-mini`)
- `FOLLOWUP_MCP_URL`, `GCALENDAR_MCP_URL`, `MANAGED_RAG_MCP_URL`
- `PORT` (10000), `URL_AGENT`
