# MCP Follow-Up Server

MCP-сервер для интеграции с [Follow-Up API](https://api.follow-up.tech/docs) — сервисом записи и транскрибации корпоративных созвонов.

## Возможности

| Tool | Описание |
|------|----------|
| `join_conference` | Подключить бота к созвону по ссылке для записи |
| `get_transcription` | Получить транскрипцию завершённого созвона |
| `list_conferences` | Получить список записанных созвонов с пагинацией |
| `get_conference_info` | Получить метаданные созвона (без транскрипции) |

## Поддерживаемые платформы ВКС

- Google Meet
- Zoom
- MS Teams
- Яндекс Телемост
- SaluteJazz
- КонтурТолк
- JitsiMeet

---

## Быстрый старт

### 1. Установка зависимостей

```bash
# Рекомендуется использовать uv
uv sync

# Или через pip
pip install -e .
```

### 2. Настройка переменных окружения

```bash
cp .env.example .env
```

Отредактируйте `.env` и добавьте ваши учётные данные Follow-Up:

```env
# Вариант 1: Авторизация через email/password
FOLLOWUP_EMAIL=your_email@example.com
FOLLOWUP_PASSWORD=your_password

# Вариант 2: Авторизация через API-ключ (JWT токен)
FOLLOWUP_API_KEY=your_jwt_token

# Опционально
FOLLOWUP_API_URL=https://api.follow-up.tech
PORT=8000
```

### 3. Запуск сервера

```bash
# Через uv (рекомендуется)
uv run python src/server.py

# Или напрямую
python src/server.py
```

Сервер будет доступен по адресу: `http://localhost:8000/mcp`

---

## Переменные окружения

| Переменная | Описание | Обязательно | По умолчанию |
|------------|----------|-------------|--------------|
| `FOLLOWUP_EMAIL` | Email для авторизации в Follow-Up | Да* | — |
| `FOLLOWUP_PASSWORD` | Пароль для авторизации | Да* | — |
| `FOLLOWUP_API_KEY` | JWT токен (альтернатива email/password) | Да* | — |
| `FOLLOWUP_API_URL` | URL API Follow-Up | Нет | `https://api.follow-up.tech` |
| `PORT` | Порт сервера | Нет | `8000` |

> *Необходимо указать либо `FOLLOWUP_API_KEY`, либо `FOLLOWUP_EMAIL` + `FOLLOWUP_PASSWORD`

---

## Доступные инструменты (Tools)

### 1. `join_conference` — Подключение к созвону

Подключает бота Follow-Up к созвону для записи и транскрибации.

**Параметры:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `conference_url` | string | Да | Ссылка на созвон |
| `theme` | string | Нет | Название/тема созвона (по умолчанию "Созвон") |

**Пример использования:**
```json
{
  "conference_url": "https://meet.google.com/abc-defg-hij",
  "theme": "Обсуждение проекта"
}
```

**Пример ответа:**
```json
{
  "success": true,
  "conference_id": "34faff15-20a3-4dee-b212-3c0a3604e239",
  "message": "Бот успешно подключается к созвону",
  "details": {
    "url": "https://meet.google.com/abc-defg-hij",
    "theme": "Обсуждение проекта",
    "status": "connecting"
  }
}
```

---

### 2. `get_transcription` — Получение транскрипции

Получает полную транскрипцию завершённого созвона с метаданными.

**Параметры:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `conference_id` | string | Да | ID созвона (UUID формат) |

**Пример использования:**
```json
{
  "conference_id": "34faff15-20a3-4dee-b212-3c0a3604e239"
}
```

**Пример ответа:**
```json
{
  "success": true,
  "conference_id": "34faff15-20a3-4dee-b212-3c0a3604e239",
  "title": "Обсуждение проекта",
  "date": "2024-12-07T14:00:00",
  "duration_minutes": 45,
  "participants": ["Иван", "Пётр", "Мария"],
  "transcription": "Иван: Привет всем! Давайте начнём...",
  "status": "completed"
}
```

---

### 3. `list_conferences` — Список созвонов

Получает список записанных созвонов с пагинацией.

**Параметры:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `limit` | int | Нет | Количество записей (1-100, по умолчанию 20) |
| `offset` | int | Нет | Смещение для пагинации (по умолчанию 0) |

**Пример использования:**
```json
{
  "limit": 10,
  "offset": 0
}
```

**Пример ответа:**
```json
{
  "success": true,
  "total": 50,
  "limit": 10,
  "offset": 0,
  "conferences": [
    {
      "id": "34faff15-20a3-4dee-b212-3c0a3604e239",
      "title": "Обсуждение проекта",
      "date": "2024-12-07T14:00:00",
      "duration_minutes": 45,
      "status": "ready"
    }
  ]
}
```

---

### 4. `get_conference_info` — Информация о созвоне

Получает метаданные созвона без загрузки полной транскрипции.

**Параметры:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `conference_id` | string | Да | ID созвона (UUID формат) |

**Пример использования:**
```json
{
  "conference_id": "34faff15-20a3-4dee-b212-3c0a3604e239"
}
```

**Пример ответа:**
```json
{
  "success": true,
  "id": "34faff15-20a3-4dee-b212-3c0a3604e239",
  "title": "Обсуждение проекта",
  "date": "2024-12-07T14:00:00",
  "duration_minutes": 45,
  "participants": ["Иван", "Пётр"],
  "status": "ready",
  "has_transcription": true
}
```

---

## Docker

### Сборка образа

```bash
docker build -t mcp-followup .

# Для linux/amd64 (для деплоя в облачный registry)
docker buildx build --platform linux/amd64 -t mcp-followup .
```

### Запуск контейнера

```bash
docker run --rm -p 8000:8000 \
  -e FOLLOWUP_EMAIL=your_email@example.com \
  -e FOLLOWUP_PASSWORD=your_password \
  mcp-followup
```

Или с использованием `.env` файла:

```bash
docker run --rm -p 8000:8000 --env-file .env mcp-followup
```

### Проверка работоспособности

```bash
# Health check
curl http://localhost:8000/health

# MCP endpoint
curl http://localhost:8000/mcp
```

---

## Деплой в Docker registry

```bash
# Сборка образа под linux/amd64
docker buildx build --platform linux/amd64 -t mcp-followup .

# Тег и push в ваш реестр
docker tag mcp-followup:latest <your-registry>/mcp-followup:v1.0.0
docker push <your-registry>/mcp-followup:v1.0.0
```

После деплоя:
1. Поднимите контейнер с переменными окружения (`FOLLOWUP_EMAIL`/`FOLLOWUP_PASSWORD` или `FOLLOWUP_API_KEY`).
2. Укажите URL MCP-сервера в `FOLLOWUP_MCP_URL` агента.

---

## Разработка

### Запуск тестов

```bash
# Все тесты
uv run pytest

# С подробным выводом
uv run pytest -v

# Только unit-тесты
uv run pytest tests/test_unit.py -v
```

### Линтинг

```bash
uv run ruff check src/
uv run ruff format src/
```

### Структура проекта

```
mcp-followup/
├── src/
│   ├── __init__.py
│   ├── server.py           # MCP сервер и tools
│   └── followup_client.py  # HTTP-клиент для Follow-Up API
├── tests/
│   ├── __init__.py
│   ├── test_unit.py        # Unit-тесты
│   └── test_e2e.py         # E2E-тесты
├── scripts/                # Скрипты для ручного тестирования API
│   ├── join_conference_with_mcp.py      # Подключение через FollowUpClient
│   ├── join_conference_without_mcp_client.py  # Отладка (raw HTTP)
│   ├── list_conferences.py              # Список созвонов
│   └── get_transcription.py             # Получение транскрипции
├── Dockerfile              # Docker-образ
├── mcp_tools.json          # Описание tools для AI Agents
├── pyproject.toml          # Зависимости проекта
├── .env.example            # Пример переменных окружения
└── README.md               # Этот файл
```

### Скрипты для тестирования

```bash
# Список созвонов
uv run python scripts/list_conferences.py

# Подключение к созвону (через клиент)
uv run python scripts/join_conference_with_mcp.py https://meet.google.com/abc-defg-hij

# Подключение к созвону (raw HTTP для отладки)
uv run python scripts/join_conference_without_mcp_client.py https://meet.google.com/abc-defg-hij

# Получение транскрипции
uv run python scripts/get_transcription.py <conference_id>
```

---

## Endpoints

| Endpoint | Описание |
|----------|----------|
| `http://localhost:8000/mcp` | MCP сервер (streamable-http) |
| `http://localhost:8000/health` | Health check |

---

## Обработка ошибок

Все tools возвращают структурированные ошибки:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Описание ошибки",
    "status_code": 404,
    "details": {}
  }
}
```

### Коды ошибок

| Код | Описание |
|-----|----------|
| `INVALID_URL` | Невалидный URL созвона |
| `INVALID_ID` | Некорректный формат ID конференции |
| `AUTH_ERROR` | Ошибка авторизации в Follow-Up API |
| `NETWORK_ERROR` | Сетевая ошибка при подключении к API |
| `NOT_FOUND` | Созвон не найден |
| `TRANSCRIPTION_NOT_READY` | Транскрипция ещё не готова |
| `NO_RECORDING` | Созвон без записи |
| `ALREADY_CONNECTED` | Бот уже подключен к созвону |
| `INTERNAL_ERROR` | Внутренняя ошибка сервера |

---

## Технологии

- Python 3.11+
- FastMCP >= 2.10.0 — фреймворк для MCP серверов
- httpx — асинхронный HTTP клиент
- Pydantic — валидация данных
- uv — менеджер зависимостей
- Docker — контейнеризация
