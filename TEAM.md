# 👥 Распределение ролей (команда из 4 человек)

Проект — микросервисная платформа: AI-агент с tool-calling, 3 MCP-сервера для внешних интеграций, два клиента (Telegram-бот и веб-UI), всё через Docker Compose. Разбит на **4 равноценные зоны ответственности** по техническому стеку.

| # | Роль | Кодовая база | Ключевые технологии |
|---|---|---:|---|
| 1 | **AI/ML Engineer** — Агент и RAG | ~30% | LangChain, эмбеддинги, vector search |
| 2 | **Backend Engineer** — Внешние API | ~30% | FastMCP, httpx, OAuth, Google APIs |
| 3 | **Frontend / DevOps** — UI и инфра | ~20% | Flask, JS/CSS, Docker, CI |
| 4 | **Bot / QA Engineer** — Бот и тесты | ~20% | aiogram, asyncio, SSE, pytest |

---

## 👤 Человек 1 — AI/ML Engineer

**Что сделал**: спроектировал LangChain-агента, настроил tool-calling через OpenRouter, реализовал локальный RAG с sentence-transformers.

### Зона ответственности

```
agent/                          ← LangChain агент + A2A wrapper
├── src/agent.py                  ← фабрика агента, 11 tools, MCPToolClient
├── src/prompts.py                ← system prompt (10 KB русского текста)
├── src/a2a_wrapper.py            ← обёртка LangChain → A2A protocol
├── src/agent_task_manager.py     ← A2A task executor + streaming
└── src/start_a2a.py              ← uvicorn entrypoint

mcp-rag-local/                  ← локальный RAG MCP-сервер
├── src/store.py                  ← in-memory cosine + JSON-persist
├── src/server.py                 ← FastMCP с tools: search/add_document/rag_stats
└── tests/test_store.py           ← unit-тесты для vector store
```

### Что умеет рассказать на защите

- Как LLM становится агентом (tool-calling loop: LLM → JSON → exec → result → LLM)
- Почему `langchain-openai.ChatOpenAI` — работает с любым OpenAI-совместимым провайдером (OpenRouter, Gemini, OpenAI, Together…)
- Pydantic-схемы → автоматическая JSON-схема tools для LLM
- Почему **локальный RAG без S3**: sentence-transformers (470 МБ модель) + numpy cosine, персист в JSON. Преимущества над managed-сервисами для демо.
- Почему `paraphrase-multilingual-MiniLM-L12-v2`: 384 dim, мультиязычная, работает на CPU.
- MCP-протокол: зачем выносить tools в отдельные серверы.

### Файлы в зоне

[agent/src/agent.py](agent/src/agent.py), [agent/src/prompts.py](agent/src/prompts.py), [agent/src/a2a_wrapper.py](agent/src/a2a_wrapper.py), [agent/src/agent_task_manager.py](agent/src/agent_task_manager.py), [agent/src/start_a2a.py](agent/src/start_a2a.py), [mcp-rag-local/src/store.py](mcp-rag-local/src/store.py), [mcp-rag-local/src/server.py](mcp-rag-local/src/server.py), [agent/tests/test_agent.py](agent/tests/test_agent.py), [agent/tests/test_smoke.py](agent/tests/test_smoke.py), [mcp-rag-local/tests/test_store.py](mcp-rag-local/tests/test_store.py).

### Тесты (его)
- `agent/tests/` — 25 passed (smoke + unit для tool factories, MCPToolClient, A2A wrapper)
- `mcp-rag-local/tests/` — 8 passed (add, search, persist, cosine ranking)
- `agent/tests/test_integration.py` — 2 (skipped, дорогие LLM-вызовы)

---

## 👤 Человек 2 — Backend Engineer (внешние API)

**Что сделал**: интегрировал два внешних сервиса (Follow-Up для записи созвонов и Google Calendar для событий) через MCP-обёртки.

### Зона ответственности

```
mcp-followup/                   ← запись и транскрибация созвонов
├── src/followup_client.py        ← HTTP-клиент Follow-Up API + auth + retry
├── src/server.py                 ← FastMCP с tools: join_conference, get_transcription,
│                                   list_conferences, get_conference_info,
│                                   download_conference_pdf, sync_conference_to_rag
├── src/rag_s3_client.py          ← S3-загрузка транскрипций (boto3)
└── tests/test_unit.py            ← unit-тесты с моками httpx

mcp-google-calendar/            ← события Google Calendar
├── src/server.py                 ← FastMCP с tools: create_calendar_event,
│                                   get_events_for_date, get_upcoming_events,
│                                   get_current_time_moscow
└── scripts/setup_oauth.py        ← OAuth2 flow для refresh_token
```

### Что умеет рассказать на защите

- Архитектура MCP-сервера на FastMCP: tool-декораторы, Pydantic-валидация параметров
- Авторизация Follow-Up: JWT login → `Bearer` → авто-rerefresh на 401
- Парсинг URL разных ВКС-платформ (Meet, Zoom, Teams, Телемост, Jitsi) для `externalId`
- Google Calendar: разница между Service Account (для read-only / shared calendar) и OAuth2 (для приглашений и Google Meet ссылок)
- Обработка ошибок API (404, 400, 401, 403, network timeout) с человекочитаемыми сообщениями для LLM

### Файлы в зоне

[mcp-followup/src/server.py](mcp-followup/src/server.py), [mcp-followup/src/followup_client.py](mcp-followup/src/followup_client.py), [mcp-followup/src/rag_s3_client.py](mcp-followup/src/rag_s3_client.py), [mcp-google-calendar/src/server.py](mcp-google-calendar/src/server.py), [mcp-google-calendar/scripts/](mcp-google-calendar/scripts/), [mcp-followup/tests/test_unit.py](mcp-followup/tests/test_unit.py).

### Тесты (его)
- `mcp-followup/tests/test_unit.py` — auth, retry, error mapping, platform detection
- `mcp-google-calendar/tests/test_unit.py` — валидация дат, парсинг таймзоны

---

## 👤 Человек 3 — Frontend / DevOps

**Что сделал**: спроектировал веб-UI инспектора A2A, поднял всю инфраструктуру (Docker для 6 сервисов, docker-compose с приватной сетью, GitHub Actions CI).

### Зона ответственности

```
demo-app/                       ← Flask + HTML/CSS/JS UI
├── app.py                        ← Flask: /api/send, /api/agent-card
├── templates/index.html          ← одностраничник:
│                                   - hero-секция с описанием
│                                   - 4 feature-карточки
│                                   - чат-панель + промпт-чипы
│                                   - правая панель: tabs (Agent Card / JSON / История)
│                                   - градиенты, тёмная тема, Inter + JetBrains Mono
├── requirements.txt
└── Dockerfile

docker-compose.yml              ← оркестрация 6 сервисов
├── volumes: rag-store, hf-cache
├── networks: meeting-assistant (bridge)
└── profiles: calendar (опционально)

Dockerfile×6:
├── agent/Dockerfile              ← Python 3.12 + uv sync --frozen
├── telegram-bot/Dockerfile       ← multi-stage
├── mcp-followup/Dockerfile       ← uv sync + non-root user
├── mcp-google-calendar/Dockerfile
├── mcp-rag-local/Dockerfile      ← с HF_HOME для кеша моделей
└── demo-app/Dockerfile

.github/workflows/ci.yml        ← GitHub Actions
├── compose-validate              ← syntax check
├── agent (ruff + pytest)
├── telegram-bot (ruff + pytest)
└── mcp-followup (pytest)
```

### Что умеет рассказать на защите

- Почему **docker-compose vs k8s**: для демо/dev — compose, для прода уже k8s. Здесь 6 сервисов в одной сети, hostname = container name.
- Как сервисы видят друг друга: `http://mcp-followup:8000/mcp` (внутри docker-сети), а локально снаружи `localhost:8000`.
- `profiles` в compose — Google Calendar опциональный (не у всех есть creds).
- Volume `hf-cache` — модель эмбеддингов скачивается **один раз** и переживает `docker compose down`.
- Multi-stage Dockerfile в telegram-bot — финальный образ меньше (нет uv внутри).
- Почему `--frozen` в `uv sync`: фиксируем версии из lock-файла (поймали баг с `a2a-sdk 1.0.3` vs `0.3.20`).
- UI: всё на чистом HTML+CSS+JS без фреймворков — простота для demo, нет билд-шага.
- CI: запускает 4 job'а параллельно, integration-тесты скипаются (платные LLM-вызовы).

### Файлы в зоне

[demo-app/app.py](demo-app/app.py), [demo-app/templates/index.html](demo-app/templates/index.html), [demo-app/Dockerfile](demo-app/Dockerfile), [docker-compose.yml](docker-compose.yml), [agent/Dockerfile](agent/Dockerfile), [telegram-bot/Dockerfile](telegram-bot/Dockerfile), [mcp-followup/Dockerfile](mcp-followup/Dockerfile), [mcp-google-calendar/Dockerfile](mcp-google-calendar/Dockerfile), [mcp-rag-local/Dockerfile](mcp-rag-local/Dockerfile), [.github/workflows/ci.yml](.github/workflows/ci.yml), [.gitignore](.gitignore).

---

## 👤 Человек 4 — Bot / QA Engineer

**Что сделал**: реализовал Telegram-бота с авто-подключением, slash-командами и live-стримингом ответов через SSE; написал и поддерживает тесты бота, написал документацию.

### Зона ответственности

```
telegram-bot/                   ← aiogram 3 бот
├── main.py                       ← entrypoint, регистрация команд через set_my_commands
├── config/config.py              ← pydantic-settings (env)
├── src/handlers/common.py        ← 🌟 ключевой файл:
│                                   - /start (auto-connect)
│                                   - /upcoming, /summary, /search, /help
│                                   - свободный текст с live-стримингом
│                                   - дросселирование edit_message (1 раз/1.2 сек)
│                                   - typing-context manager
├── src/services/
│   ├── agent_connector.py        ← 🌟 A2A SSE-клиент:
│   │                                - send_message (blocking)
│   │                                - stream_message (SSE parser)
│   │                                - retry с exponential backoff
│   ├── request_manager.py        ← отмена in-flight запросов
│   └── utils/session.py          ← SessionStore (singleton)
└── tests/
    ├── test_smoke.py             ← импорты, config, init
    └── test_bot.py               ← 27 unit-тестов: AgentConnector,
                                     SSE parsing, RequestManager,
                                     session store

README.md                       ← главный README c Docker инструкцией
DEMO.md                         ← пошаговый сценарий демонстрации
TEAM.md                         ← (этот файл)
```

### Что умеет рассказать на защите

- **Live-стриминг** в Telegram: A2A `message/stream` → SSE → парсинг events типа `status-update`/`artifact-update` → `bot.edit_message_text` с дросселированием (`STREAM_EDIT_INTERVAL = 1.2s`)
- Telegram rate limit: ~30 edit/min — поэтому буферим обновления, отправляем не чаще раз в 1.2 сек
- Различение статус-строки (🔧 префикс) от инкрементов текста ответа
- Авто-подключение к агенту на `/start` (`AUTO_CONNECT_ON_START=true`) — убрали 3 лишних клика
- Slash-команды: bot.set_my_commands() — Telegram сам показывает автодополнение
- Изоляция сессий по `user_id` через singleton SessionStore
- `pytest-asyncio` + моки `httpx` — как тестировать SSE без реального сервера

### Файлы в зоне

[telegram-bot/main.py](telegram-bot/main.py), [telegram-bot/src/handlers/common.py](telegram-bot/src/handlers/common.py), [telegram-bot/src/services/agent_connector.py](telegram-bot/src/services/agent_connector.py), [telegram-bot/src/services/request_manager.py](telegram-bot/src/services/request_manager.py), [telegram-bot/src/utils/session.py](telegram-bot/src/utils/session.py), [telegram-bot/config/config.py](telegram-bot/config/config.py), [telegram-bot/src/keyboards/__init__.py](telegram-bot/src/keyboards/__init__.py), [telegram-bot/tests/](telegram-bot/tests/), [README.md](README.md), [DEMO.md](DEMO.md).

### Тесты (его)
- `telegram-bot/tests/` — **31 passed**:
  - AgentConnector: создание payload, retry, парс ответа, truncation
  - SSE-парсер: status/text/done/error события + error на 500
  - SessionStore singleton, RequestManager отмена
  - smoke: импорты всех модулей

---

## 📊 Сводная таблица

| Зона | Файлов | LOC (примерно) | Тесты |
|---|---:|---:|---:|
| AI/ML (агент + RAG) | 12 | ~1100 | 33 |
| Backend (Follow-Up + Calendar) | 8 | ~1400 | 30+ |
| Frontend / DevOps | 15 | ~900 | (compose-validate) |
| Bot / QA | 11 | ~700 | 31 |
| **Итого** | **~46** | **~4100** | **~94 unit + 2 skip** |

## 🎯 Кто что демонстрирует на защите

| Часть демо | Кто говорит |
|---|---|
| Hero-секция UI, дизайн, переключение между табами | 👤 3 (Frontend) |
| Создание встречи в Calendar + e-mail приглашение | 👤 2 (Backend) |
| Запись Telemost через Follow-Up бота | 👤 2 (Backend) |
| RAG: добавление фактов + семантический поиск | 👤 1 (AI/ML) |
| Telegram-бот, slash-команды | 👤 4 (Bot) |
| Live-стриминг в TG (🔧 Использую инструмент) | 👤 4 (Bot) |
| JSON-инспектор, Agent Card | 👤 3 (Frontend) |
| Архитектура: `docker compose ps` + диаграмма | 👤 3 (DevOps) |
| LangChain под капотом, tool-loop | 👤 1 (AI/ML) |
| CI/тесты (github actions, 94 теста) | 👤 4 (QA) |

## ⚖️ Балансировка

- Все 4 написали примерно одинаково кода (~700-1400 LOC каждый).
- Все 4 написали свои тесты (~25-30 шт каждый, кроме DevOps — у того compose-validate в CI).
- Все 4 могут говорить на защите минимум 2-3 минуты по своей зоне.
- Никто не дублирует чужой стек: ML отдельно, REST API отдельно, инфра отдельно, UX/streaming отдельно.

Если кто-то слабее — можно подвинуть scope: например, перевести один из MCP-серверов из Backend Engineer'у в AI/ML, либо часть Docker-инфры в DevOps уменьшить и добавить ему пару тестов.
