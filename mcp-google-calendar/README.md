# MCP Google Calendar Server

MCP-сервер для работы с Google Calendar через Service Account.

## Возможности

| Tool | Описание |
|------|----------|
| `get_current_time_moscow` | Получить текущее время по Москве |
| `create_calendar_event` | Создать событие в календаре |
| `get_events_for_date` | Получить события за конкретный день |
| `get_upcoming_events` | Получить события на N дней вперёд |

---

## Быстрый старт

### 1. Настройка Google Service Account

1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/)
2. Включите Google Calendar API
3. Создайте Service Account (IAM & Admin → Service Accounts)
4. Создайте ключ для Service Account (JSON)
5. Расшарьте календарь на email Service Account

### 2. Настройка переменных окружения

```bash
cp .env.example .env
```

Заполните `.env` данными из JSON-ключа Service Account:

```env
GOOGLE_SERVICE_ACCOUNT_TYPE=service_account
GOOGLE_PROJECT_ID=your-project-id
GOOGLE_PRIVATE_KEY_ID=...
GOOGLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
GOOGLE_CLIENT_EMAIL=your-sa@project.iam.gserviceaccount.com
GOOGLE_CLIENT_ID=...
GOOGLE_AUTH_URI=https://accounts.google.com/o/oauth2/auth
GOOGLE_TOKEN_URI=https://oauth2.googleapis.com/token

GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
```

### 3. Расшарить календарь

1. Откройте Google Calendar
2. Настройки календаря → Share with specific people
3. Добавьте email Service Account
4. Дайте права "Make changes to events"

### 4. Запуск сервера

```bash
# Установка зависимостей
uv sync

# Запуск
uv run python src/server.py
```

Сервер будет доступен: `http://localhost:8001/mcp`

---

## Доступные инструменты (Tools)

### 1. `get_current_time_moscow`

Получить текущее время по Москве.

**Пример ответа:**
```json
{
  "success": true,
  "timezone": "Europe/Moscow",
  "datetime_iso": "2025-12-10T15:30:00+03:00",
  "date": "2025-12-10",
  "time": "15:30:00",
  "formatted": "10.12.2025 15:30"
}
```

### 2. `create_calendar_event`

Создать событие в календаре.

**Параметры:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `title` | string | Да | Название события |
| `start_time` | string | Да | Время начала (ISO 8601 или YYYY-MM-DD HH:MM) |
| `end_time` | string | Да | Время окончания |
| `description` | string | Нет | Описание (ссылка на созвон) |

**Пример:**
```json
{
  "title": "Созвон с командой",
  "start_time": "2025-12-11T14:00:00",
  "end_time": "2025-12-11T15:00:00",
  "description": "https://telemost.yandex.ru/j/123456"
}
```

### 3. `get_events_for_date`

Получить события за конкретный день.

**Параметры:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `date` | string | Нет | Дата (YYYY-MM-DD), по умолчанию сегодня |

### 4. `get_upcoming_events`

Получить события на несколько дней вперёд.

**Параметры:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `days_ahead` | int | Нет | Дней вперёд (1-30, по умолчанию 7) |

---

## Docker

```bash
# Сборка
docker build -t mcp-google-calendar .

# Запуск
docker run --rm -p 8001:8001 --env-file .env mcp-google-calendar
```

---

## Переменные окружения

| Переменная | Описание | Обязательно |
|------------|----------|-------------|
| `GOOGLE_PROJECT_ID` | ID проекта в Google Cloud | Да |
| `GOOGLE_PRIVATE_KEY` | Приватный ключ Service Account | Да |
| `GOOGLE_CLIENT_EMAIL` | Email Service Account | Да |
| `GOOGLE_CALENDAR_ID` | ID календаря | Да |
| `PORT` | Порт сервера | Нет (8001) |








