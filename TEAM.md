# 👥 Распределение ролей (команда из 4 человек)

Проект — микросервисная платформа: AI-агент с tool-calling, MCP-серверы для внешних интеграций, два клиента (Telegram-бот и веб-UI), всё через Docker Compose. Разбит на **4 равноценные зоны**: 2 ML-инженера + 2 backend-инженера.

| # | Роль | Зона | Стек |
|---|---|---|---|
| 1 | **ML Engineer #1** — Agent | LangChain агент, A2A | LangChain, OpenRouter, A2A SDK |
| 2 | **ML Engineer #2** — RAG | поиск по знаниям, эмбеддинги | sentence-transformers, FastMCP, NumPy |
| 3 | **Backend #1** — External APIs | MCP интеграции | httpx, OAuth, FastMCP, Google APIs |
| 4 | **Backend #2** — Bot + Infra | TG-бот, Docker, CI | aiogram, asyncio, SSE, Docker |

> Тесты по своим модулям и веб-UI demo-app генерились AI (Claude/ChatGPT), потому отдельных QA/Frontend ролей нет — каждый поддерживает тесты в своей зоне.

---

## 👤 Человек 1 — ML Engineer #1 (Agent)

**Что сделал**: спроектировал LangChain-агента с tool-calling, обернул его в A2A-протокол для общения с клиентами, настроил подключение к LLM-провайдеру (OpenRouter с возможностью переключения на Gemini/OpenAI), написал системный промпт.

### Зона ответственности

```
agent/                          ← LangChain агент + A2A wrapper
├── src/agent.py                  ← 🌟 главный файл:
│                                   - фабрика create_meeting_assistant_agent()
│                                   - 11 StructuredTool (5 followup + 4 calendar + 2 rag)
│                                   - класс MCPToolClient (HTTP к MCP-серверам)
│                                   - подключение ChatOpenAI к OpenRouter/Gemini
├── src/prompts.py                ← system prompt (~10 КБ русского текста,
│                                   описание поведения, few-shot примеры)
├── src/a2a_wrapper.py            ← обёртка LangChain → A2A:
│                                   - invoke (blocking)
│                                   - stream (для live-обновлений)
├── src/agent_task_manager.py     ← A2A task executor
└── src/start_a2a.py              ← uvicorn entrypoint, AgentCard, AgentSkill
```

### Что умеет рассказать на защите

- **Tool-calling loop**: LLM получает описания tools (JSON-схемы из Pydantic), возвращает `tool_calls`, LangChain парсит → дёргает функцию → результат обратно в LLM → финальный ответ.
- **Почему `langchain-openai.ChatOpenAI`**: один клиент работает с любым OpenAI-совместимым провайдером — OpenRouter, Gemini (через `generativelanguage.googleapis.com/v1beta/openai`), OpenAI, Together, Groq. Меняешь только 3 env-переменные.
- **System prompt engineering**: чему учить агента — парсинг "завтра в 15:00" → ISO 8601, определение платформы по URL, выбор tool под задачу. Без хорошего промпта tool-calling работает плохо.
- **A2A protocol** (Agent-to-Agent от Anthropic-партнёрки): JSON-RPC методы `message/send` и `message/stream`, AgentCard для discovery (`.well-known/agent-card.json`).
- **MCPToolClient**: как подключать MCP-серверы по HTTP — `initialize` → получить `Mcp-Session-Id` → `tools/call` с SSE-парсингом ответа.

### Файлы в зоне

[agent/src/agent.py](agent/src/agent.py), [agent/src/prompts.py](agent/src/prompts.py), [agent/src/a2a_wrapper.py](agent/src/a2a_wrapper.py), [agent/src/agent_task_manager.py](agent/src/agent_task_manager.py), [agent/src/start_a2a.py](agent/src/start_a2a.py), [agent/scripts/test_llm_api.py](agent/scripts/test_llm_api.py), [agent/.env.example](agent/.env.example), [agent/.env.gemini.example](agent/.env.gemini.example).

---

## 👤 Человек 2 — ML Engineer #2 (RAG)

**Что сделал**: спроектировал и реализовал локальный RAG-сервис без облака (sentence-transformers + cosine similarity + JSON-персист), упаковал его в MCP-сервер для агента; провёл подбор embedding-модели.

### Зона ответственности

```
mcp-rag-local/                  ← локальный RAG MCP-сервер
├── src/store.py                  ← 🌟 vector store:
│                                   - add(content, metadata) → embedding via SentenceTransformer
│                                   - search(query, top_k) → cosine similarity через NumPy
│                                   - персист в JSON (volume rag-store в Docker)
├── src/server.py                 ← FastMCP-обёртка:
│                                   - tools: search, add_document, rag_stats
│                                   - lazy-init embedder (модель грузится при первом запросе)
│                                   - force CPU (на Apple Silicon MPS-init крашит процесс)
│                                   - HF_HUB_DISABLE_XET=1 (xet downloader сегфолтит)
├── .env.example                  ← конфиг: EMBEDDING_MODEL, RAG_STORE_PATH
├── Dockerfile                    ← volume для hf-cache (модель ~470 МБ скачивается 1 раз)
└── tests/test_store.py           ← 8 unit-тестов с фейковым embedder'ом
```

### Что умеет рассказать на защите

- **Почему локальный RAG, а не Pinecone/Weaviate/Cloud-managed**: для демо проще, никаких облачных аккаунтов, всё в JSON, легко чистится (`docker compose down -v`).
- **Выбор модели**: `paraphrase-multilingual-MiniLM-L12-v2` — 384 dim, мультиязычная, CPU-friendly, 470 МБ. Альтернативы: `e5-small-multilingual` (тоже мультиязычная), `bge-small` (быстрее, английская).
- **Cosine similarity через NumPy**: `embs @ q` после `normalize_embeddings=True` — это уже cosine. Один matmul на N документов. Для 10K документов работает за <100 мс.
- **MCP интерфейс совместим с managed-RAG**: tools называются `search` / `add_document`, агент может подменить URL без правок кода.
- **Подводные камни деплоя**: на macOS Apple Silicon (MPS) sentence-transformers иногда крашит процесс при первой загрузке через `hf_xet`. Решение: `device="cpu"` + `HF_HUB_DISABLE_XET=1`.
- **Стриминг tool-событий**: A2A `message/stream` отдаёт SSE с `status-update` / `artifact-update`. Когда агент дёргает `search_knowledge_base`, в стриме появляется `🔧 Использую инструмент: search_knowledge_base` — это видно в TG-боте.

### Файлы в зоне

[mcp-rag-local/src/store.py](mcp-rag-local/src/store.py), [mcp-rag-local/src/server.py](mcp-rag-local/src/server.py), [mcp-rag-local/Dockerfile](mcp-rag-local/Dockerfile), [mcp-rag-local/.env.example](mcp-rag-local/.env.example), [mcp-rag-local/pyproject.toml](mcp-rag-local/pyproject.toml), [mcp-rag-local/tests/test_store.py](mcp-rag-local/tests/test_store.py).

Также — RAG-tools в агенте: [agent/src/agent.py:create_rag_tools](agent/src/agent.py) (фабрика RAG-обёрток для LangChain).

---

## 👤 Человек 3 — Backend Engineer #1 (External APIs)

**Что сделал**: интегрировал два внешних сервиса — Follow-Up для записи созвонов и Google Calendar для событий. Каждый завернул в отдельный MCP-сервер, чтобы агент мог их дёргать как tools.

### Зона ответственности

```
mcp-followup/                   ← запись и транскрибация созвонов
├── src/followup_client.py        ← 🌟 HTTP-клиент Follow-Up API:
│                                   - JWT-логин через /api/login → Bearer-token
│                                   - авто-rerefresh на 401
│                                   - детекция платформы ВКС по URL
│                                     (Meet, Zoom, Teams, Телемост, Jitsi, SaluteJazz, КонтурТолк)
│                                   - download PDF через lk.follow-up.tech (next-auth CSRF)
├── src/server.py                 ← FastMCP, 6 tools:
│                                   - join_conference, get_transcription,
│                                     list_conferences, get_conference_info,
│                                     download_conference_pdf, sync_conference_to_rag
├── src/rag_s3_client.py          ← опц. boto3-клиент для S3-синка
└── tests/                        ← 20+ unit-тестов с моками httpx

mcp-google-calendar/            ← события Google Calendar
├── src/server.py                 ← 🌟 OAuth2-клиент:
│                                   - tools: create_calendar_event (с attendees,
│                                     Google Meet и e-mail приглашениями),
│                                     get_events_for_date, get_upcoming_events,
│                                     get_current_time_moscow
│                                   - таймзоны через pytz
│                                   - валидация ISO 8601
└── scripts/setup_oauth.py        ← одноразовый flow для получения refresh_token
```

### Что умеет рассказать на защите

- **FastMCP**: tool-декораторы автоматически создают JSON-схему из Pydantic Field-аннотаций, валидируют параметры, отдают streamable-HTTP MCP-протокол.
- **Авторизация в Follow-Up**: классическая JWT-схема. Логин → access-token (~час) → авто-refresh на 401 → если в env есть `FOLLOWUP_API_KEY`, используем его без email/password (для serverless-сценариев).
- **Парсинг URL разных платформ**: 7 платформ ВКС, каждая со своим форматом ID. Например, Meet: `https://meet.google.com/abc-defg-hij` → `externalId=abc-defg-hij`. Zoom: `/j/123456789` → `externalId=123456789`.
- **Google Calendar — Service Account vs OAuth2**: SA удобен для server-to-server, но **не может отправлять email-приглашения** (Google запретил). Для invitations нужен OAuth2 от имени реального пользователя.
- **`create_calendar_event` с attendees**: при `add_google_meet=True` Google API сам генерирует Meet-ссылку. Если есть `attendees` — рассылает приглашения на email.
- **Обработка ошибок API**: 401 → пере-логин и retry, 404 → "не найден", 400 → "плохой запрос" → агент видит понятное сообщение и сообщает пользователю.

### Файлы в зоне

[mcp-followup/src/followup_client.py](mcp-followup/src/followup_client.py), [mcp-followup/src/server.py](mcp-followup/src/server.py), [mcp-followup/src/rag_s3_client.py](mcp-followup/src/rag_s3_client.py), [mcp-google-calendar/src/server.py](mcp-google-calendar/src/server.py), [mcp-google-calendar/scripts/](mcp-google-calendar/scripts/), [mcp-followup/tests/](mcp-followup/tests/).

---

## 👤 Человек 4 — Backend Engineer #2 (Bot + Infra)

**Что сделал**: реализовал Telegram-бота на aiogram 3 с автоподключением к агенту, slash-командами и **live-стримингом ответов через SSE**; собрал всё в docker-compose с приватной сетью; настроил GitHub Actions CI.

### Зона ответственности

```
telegram-bot/                   ← aiogram 3 бот
├── main.py                       ← entrypoint, set_my_commands для авто-подсказок
├── config/config.py              ← pydantic-settings
├── src/handlers/common.py        ← 🌟 ключевой файл:
│                                   - /start с авто-подключением
│                                   - /upcoming, /summary, /search, /help
│                                   - свободный текст
│                                   - live-обновление сообщения через
│                                     bot.edit_message_text (дроссель 1.2 сек,
│                                     чтобы не словить TG rate-limit ~30/min)
│                                   - typing-context manager (анимация "печатает…")
├── src/services/
│   ├── agent_connector.py        ← 🌟 A2A SSE-клиент:
│   │                                - stream_message → парсит SSE из
│   │                                  message/stream A2A endpoint,
│   │                                  yield-ит events {status|text|done|error}
│   │                                - send_message (blocking + retry с exp backoff)
│   ├── request_manager.py        ← отмена in-flight запросов на edit-message
│   └── utils/session.py          ← SessionStore (singleton, key by user_id)
└── tests/                        ← 31 тест:
                                     - SSE parsing happy/error path
                                     - retry, payload, truncation
                                     - SessionStore, RequestManager

docker-compose.yml              ← 🌟 оркестрация 6 сервисов
├── приватная сеть meeting-assistant (bridge)
├── volumes: rag-store, hf-cache (модель эмбеддингов переживает rebuilds)
├── profiles: calendar (Google Calendar опционален)
└── environment-override: hostnames внутри сети (mcp-followup:8000, …)

Dockerfile×6                    ← все сервисы упакованы:
├── multi-stage в telegram-bot для уменьшения образа
├── non-root user в mcp-followup
└── --frozen в agent (поймали баг с a2a-sdk 1.0.3 vs 0.3.20)

.github/workflows/ci.yml        ← 4 параллельных job'а:
├── compose-validate (docker compose config)
├── agent (ruff + pytest, integration-тесты skipped — экономия токенов)
├── telegram-bot (ruff + pytest)
└── mcp-followup (pytest)
```

### Что умеет рассказать на защите

- **Live-стриминг в Telegram** — это killer-feature. Сообщение "🤔 Думаю…" меняется в реальном времени: `🔧 Использую инструмент: search_knowledge_base` → текст ответа → финал. Технически: aiogram + `bot.edit_message_text` + дросселирование (Telegram rate-limit 30/min на чат).
- **SSE-парсер для A2A** — `message/stream` отдаёт `data: {jsonrpc, result: {kind: status-update|artifact-update}}` → парсим, различаем статусы (`🔧 …`) от инкрементов текста по префиксу, аккумулируем.
- **Авто-подключение**: `AUTO_CONNECT_ON_START=true` — убрали 3 лишних клика. Юзер сразу пишет вопрос.
- **Slash-команды**: `bot.set_my_commands()` — Telegram показывает автодополнение в меню `/`.
- **Docker Compose**: 6 контейнеров в одной приватной сети. Внутри сети сервисы видят друг друга по имени контейнера, наружу пробрасываются нужные порты.
- **Volume `hf-cache`**: модель эмбеддингов (470 МБ) скачивается **один раз** и переживает `docker compose down`. Без этого билд RAG-сервиса = 5 минут каждый раз.
- **CI**: 4 job'а параллельно, integration-тесты выключены через `pytest.mark.skipif(RUN_LLM_INTEGRATION_TESTS != "1")` — экономия токенов на дорогих LLM-вызовах.

### Файлы в зоне

[telegram-bot/main.py](telegram-bot/main.py), [telegram-bot/src/handlers/common.py](telegram-bot/src/handlers/common.py), [telegram-bot/src/services/agent_connector.py](telegram-bot/src/services/agent_connector.py), [telegram-bot/src/services/request_manager.py](telegram-bot/src/services/request_manager.py), [telegram-bot/src/utils/session.py](telegram-bot/src/utils/session.py), [telegram-bot/tests/](telegram-bot/tests/), [docker-compose.yml](docker-compose.yml), все Dockerfile, [.github/workflows/ci.yml](.github/workflows/ci.yml).

---

## 📊 Сводная таблица

| Зона | Ключевые файлы | Тестов |
|---|---|---:|
| ML #1 — Agent | `agent/src/*` (LangChain, A2A) | 25 |
| ML #2 — RAG | `mcp-rag-local/src/*` + streaming в боте | 8 |
| Backend #1 — External APIs | `mcp-followup/`, `mcp-google-calendar/` | 20+ |
| Backend #2 — Bot + Infra | `telegram-bot/`, `docker-compose.yml`, CI | 31 |
| **Итого** | **~46 файлов** | **~84 unit + 2 skip** |

## 🎯 Кто что демонстрирует на защите

| Часть демо | Кто говорит |
|---|---|
| Архитектура: `docker compose ps` + диаграмма | 👤 4 (Infra) |
| Hero-секция UI, инспектор A2A, Agent Card | 👤 1 (Agent) |
| LangChain tool-loop, prompt engineering | 👤 1 (Agent) |
| Создание встречи в Calendar + e-mail приглашение | 👤 3 (External APIs) |
| Запись Telemost через Follow-Up | 👤 3 (External APIs) |
| RAG: добавление фактов + семантический поиск | 👤 2 (RAG) |
| Выбор embedding модели, cosine similarity | 👤 2 (RAG) |
| Telegram-бот, slash-команды, авто-подключение | 👤 4 (Bot) |
| Live-стриминг ответа в TG (🔧 Использую инструмент) | 👤 4 (Bot) + 👤 1 (Agent stream) |
| MCP-протокол — зачем выносим tools в отдельные сервисы | 👤 1 (Agent) |
| CI/тесты | 👤 4 (Infra) |

## ⚖️ Балансировка

- **2 ML-щика**: один отвечает за «голову» агента (LangChain, prompt engineering, LLM-провайдер), второй — за «память» (RAG + tool-event streaming).
- **2 backend-инженера**: один на внешние REST-интеграции (Follow-Up, Google), второй на пользовательский слой (TG-бот, Docker, CI).
- **Frontend (`demo-app/templates/index.html`) и тесты сгенерированы AI** — каждый поддерживает тесты в своей зоне (правит при изменениях), демо-UI поддерживает Infra-инженер (он же отвечает за деплой).
- Никто не дублирует чужой стек: ML работает с LLM и эмбеддингами, Backend — с REST API и сетью/деплоем.
