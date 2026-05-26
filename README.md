# Meeting Assistant Platform

Платформа для работы с корпоративными встречами: запись и транскрибация созвонов, управление календарём, поиск по истории встреч через RAG. Доступ — через Telegram-бот и веб-демо.

## Архитектура

```
┌────────────┐     ┌────────────┐     ┌────────────────┐
│ Telegram   │────▶│            │────▶│ Follow-Up MCP  │  запись/транскрипция
│ Bot        │     │   Agent    │     ├────────────────┤
└────────────┘     │ (LangChain │────▶│ Calendar MCP   │  Google Calendar (опц.)
                   │  + A2A)    │     ├────────────────┤
┌────────────┐     │            │────▶│ Local RAG MCP  │  sentence-transformers
│ Demo App   │────▶│            │     └────────────────┘  + cosine similarity
└────────────┘     └────────────┘
```

- **Agent** — LangChain + tool-calling. Любой OpenAI-совместимый LLM (по умолчанию OpenRouter).
- **MCP-серверы** — Follow-Up (созвоны), Google Calendar (опционально), локальный RAG без S3.
- **Telegram Bot** — команды `/summary`, `/search`, `/upcoming` + свободный текст; live-стриминг.
- **Demo App** — Flask-инспектор A2A с веб-интерфейсом.

## Стек

Python 3.12, LangChain, A2A SDK, FastMCP, aiogram 3, Flask, httpx, sentence-transformers.

---

## Запуск через Docker (рекомендуется)

### Что понадобится

- Docker Desktop / Docker Engine + Docker Compose v2
- ~3 ГБ свободного места (Python-образы + кеш HuggingFace для эмбеддингов)
- Креды (см. ниже)

### 1. Подготовьте `.env`-файлы

Заполните файлы для каждого сервиса. Образцы — в `.env.example`:

```bash
cp agent/.env.example          agent/.env
cp telegram-bot/.env.example   telegram-bot/.env
cp mcp-followup/.env.example   mcp-followup/.env
cp mcp-rag-local/.env.example  mcp-rag-local/.env
# Опционально:
cp mcp-google-calendar/.env.example mcp-google-calendar/.env
```

### 2. Какие credentials нужны

#### Обязательные

**`agent/.env`** — ключ LLM-провайдера. Поддерживается **любой OpenAI-совместимый эндпоинт**.

**OpenRouter** (по умолчанию):
```bash
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-XXXXXXXXXXXXXXXXXXXX     # ← получить на openrouter.ai/keys
LLM_MODEL=openai/gpt-4o-mini                  # любая модель OpenRouter
```

**Google Gemini** (есть бесплатный grant ~$300):
```bash
LLM_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai
LLM_API_KEY=AIzaSy-XXXXXXXXXXXXXXXXXXXX       # ← получить на aistudio.google.com/apikey
LLM_MODEL=gemini-2.0-flash                    # или gemini-2.5-flash / gemini-2.5-pro
```
Перед использованием нужно включить **Generative Language API** в Google Cloud Console:
[console.cloud.google.com/apis/library/generativelanguage.googleapis.com](https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com).

Готовый пресет: `cp agent/.env.gemini.example agent/.env`.

**Другие провайдеры** (OpenAI, Together, Groq, Anthropic-compat и т.д.) — просто поменяйте те же 3 переменные.

**`telegram-bot/.env`** — токен бота от [@BotFather](https://t.me/BotFather) (`/newbot`):
```bash
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI...    # ← от BotFather
TELEGRAM_BOT_USERNAME=your_bot                # username без @
AUTO_CONNECT_ON_START=true
```

**`mcp-followup/.env`** — аккаунт на [follow-up.tech](https://follow-up.tech) (для записи созвонов):
```bash
FOLLOWUP_EMAIL=your@email.com
FOLLOWUP_PASSWORD=your_password
FOLLOWUP_API_URL=https://api.follow-up.tech
```
Если у вас нет аккаунта Follow-Up — этот сервис можно не поднимать (см. ниже).

**`mcp-rag-local/.env`** — дефолты сразу рабочие, ничего подставлять не нужно:
```bash
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RAG_STORE_PATH=/app/data/rag_store.json
HF_HUB_DISABLE_XET=1
HF_HUB_DISABLE_TELEMETRY=1
```

#### Опциональные

**`mcp-google-calendar/.env`** — Google Service Account JSON + Calendar ID. Чтобы получить:
1. [console.cloud.google.com](https://console.cloud.google.com) → создать проект → APIs → включить **Google Calendar API**.
2. IAM → Service Accounts → Create → Keys → Add key (JSON) → скачать.
3. В Google Calendar (web) → Settings → нужный календарь → Share → добавьте email сервис-аккаунта (поле `client_email` из JSON) с правом «Make changes to events».
4. Возьмите Calendar ID из Settings → Integrate calendar.
5. Заполните `GOOGLE_*` переменные согласно `.env.example`.

### 3. Поднимите всё одной командой

```bash
# Без Google Calendar (минимум)
docker compose up --build -d

# Или со всеми сервисами, включая Calendar
docker compose --profile calendar up --build -d
```

Что произойдёт:
- Соберутся образы для агента, бота, MCP-серверов и demo-app.
- Локальный RAG скачает модель эмбеддингов (~470 МБ, **один раз** — кешируется в Docker volume `hf-cache`).
- Сервисы поднимутся в одной Docker-сети и увидят друг друга по именам.

### 4. Проверьте, что работает

```bash
docker compose ps                       # все сервисы должны быть в State: Up
docker compose logs -f agent            # логи агента
docker compose logs -f telegram-bot     # логи бота
```

Открытые порты:
- **5000** — Demo App (веб-UI): http://localhost:5000
- **10000** — Agent A2A: http://localhost:10000/.well-known/agent-card.json
- **8000** — MCP Follow-Up
- **8002** — MCP Local RAG
- **8001** — MCP Google Calendar (только с `--profile calendar`)

Telegram-бот не имеет публичного порта — он сам стучится в Telegram через polling.

### 5. Остановка / пересборка

```bash
docker compose down               # остановить
docker compose down -v            # остановить + удалить volume'ы (RAG-база и кеш моделей)
docker compose up --build -d      # пересобрать после правок кода
docker compose restart agent      # рестартануть отдельный сервис
```

---

## Текущий функционал

| Функционал | Зависит от | Статус без credentials |
|---|---|---|
| Свободный диалог с агентом | OpenRouter ключ | ❌ нужен `LLM_API_KEY` |
| Запись/транскрибация созвонов (Meet, Zoom, Teams, Телемост, Jitsi, …) | Follow-Up аккаунт | ❌ нужны `FOLLOWUP_EMAIL/PASSWORD` |
| Список созвонов, метаданные, PDF | Follow-Up | ❌ так же |
| Поиск по транскрипциям (RAG) | — | ✅ работает из коробки |
| Saммари созвона по ID (`/summary`) | Follow-Up | ❌ нужен Follow-Up |
| Создание событий в Google Calendar | Google SA | ⚠️ опционально |
| `/upcoming` — предстоящие встречи | Google Calendar | ⚠️ опционально |
| Telegram-бот (UI) | TG token | ❌ нужен `TELEGRAM_BOT_TOKEN` |
| Demo App (веб-UI) | — | ✅ работает |

**Минимально рабочий набор**: только `LLM_API_KEY` (агент + RAG + Demo App + базовый Telegram-бот без записи звонков и без календаря). Дальше — по мере подключения остальных credentials.

---

## Команды Telegram-бота

- `/start` — приветствие, авто-подключение к агенту
- `/upcoming [N]` — встречи на N дней (требует Calendar)
- `/summary <conference_id>` — саммари созвона по ID (требует Follow-Up)
- `/search <запрос>` — поиск по транскрипциям (локальный RAG)
- `/help` — справка

Помимо команд понимает естественный язык: «Создай встречу на завтра в 15:00», «Подключись к https://meet.google.com/xxx», «О чём говорили на прошлой встрече?».

---

## Тесты

```bash
# Агент
cd agent && uv run pytest tests/ -v

# Telegram-бот
cd telegram-bot && uv run pytest tests/ -v

# MCP Follow-Up
cd mcp-followup && uv run pytest tests/test_unit.py -v

# Локальный RAG
cd mcp-rag-local && uv run pytest tests/ -v
```

### Integration-тесты с реальным OpenRouter

2 теста в `agent/tests/test_integration.py` делают **платные** вызовы к OpenRouter и **отключены по умолчанию для экономии токенов** — как локально, так и в CI.

Включить:
```bash
cd agent
RUN_LLM_INTEGRATION_TESTS=1 LLM_API_KEY=sk-or-v1-... \
  uv run pytest tests/test_integration.py -m integration -v
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) прогоняет всё, кроме integration.

---

## Локальная разработка (без Docker)

Если хотите дёргать сервисы напрямую через `uv` — поднимайте их по очереди:

```bash
# 1) Follow-Up MCP (порт 8000)
cd mcp-followup && uv sync && uv run python -m src.server

# 2) Локальный RAG (порт 8002; первый запуск качает модель ~470MB)
cd ../mcp-rag-local && uv sync && uv run python -m src.server

# 3) (опц.) Google Calendar (порт 8001)
cd ../mcp-google-calendar && uv sync && uv run python -m src.server

# 4) Агент (порт 10000)
cd ../agent && uv sync && uv run python -m src.start_a2a

# 5) Telegram-бот
cd ../telegram-bot && uv sync && uv run python main.py

# 6) Demo App (порт 5000)
cd ../demo-app && pip install -r requirements.txt && python app.py
```

Smoke-проверка LLM:
```bash
cd agent && uv run python scripts/test_llm_api.py
```

---

## Локальный RAG (без S3)

`mcp-rag-local` — лёгкая альтернатива managed RAG-сервисам:
- **Эмбеддинги**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (~470 MB, мультиязычная, 384 dim, CPU).
- **Vector store**: in-memory cosine similarity + персист в JSON (`/app/data/rag_store.json` внутри контейнера, volume `rag-store`).
- **Tools (совпадают по именам с managed RAG)**: `search`, `add_document`, `rag_stats`.

Очистить базу: `docker compose down -v` (удалит volume `rag-store`).

### Альтернатива: managed RAG (`mcp-cloudru`)

Если хочется managed RAG с индексацией через S3 — есть отдельный модуль `mcp-cloudru/` с tool'ами `s3_upload_text`, `rag_start_indexing`, `rag_search` и т.д. По умолчанию compose его не поднимает.

---

## Конфигурация агента (`agent/.env.example`)

| Переменная | Назначение | Дефолт |
|---|---|---|
| `LLM_API_BASE` | OpenAI-совместимый эндпоинт | `https://openrouter.ai/api/v1` |
| `LLM_API_KEY` | API-ключ LLM | — (обязательно) |
| `LLM_MODEL` | Имя модели | `openai/gpt-4o-mini` |
| `OPENROUTER_SITE_URL` | опц., заголовок `HTTP-Referer` | — |
| `OPENROUTER_APP_NAME` | опц., заголовок `X-Title` | — |
| `FOLLOWUP_MCP_URL` | URL Follow-Up MCP | задаётся compose'ом |
| `GCALENDAR_MCP_URL` | URL Calendar MCP | задаётся compose'ом |
| `MANAGED_RAG_MCP_URL` | URL RAG MCP | задаётся compose'ом |
| `PORT` | HTTP-порт A2A-сервера | `10000` |

В Docker-режиме URL'ы MCP подставляются compose'ом автоматически (`http://mcp-followup:8000/mcp` и т.д.). В .env эти переменные нужны только при локальном запуске без Docker.

## Лицензия

MIT
