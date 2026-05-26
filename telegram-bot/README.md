# Meeting Assistant Telegram Bot

Telegram-бот для взаимодействия с AI-агентом Meeting Assistant. Позволяет управлять созвонами, получать транскрипции и искать информацию по истории встреч через Telegram.

## Возможности

- 📅 Создание встреч в календаре через естественный язык
- 🎙 Подключение бота Follow-Up к созвонам для записи
- 🔍 Поиск по транскрипциям прошлых встреч
- 💬 Ответы на вопросы по содержимому встреч

## Быстрый старт

### 1. Создание бота в Telegram

1. Откройте [@BotFather](https://t.me/botfather) в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен

### 2. Настройка окружения

```bash
# Скопируйте пример конфигурации
cp .env.example .env

# Отредактируйте .env файл
```

Заполните переменные:
```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_BOT_USERNAME=your_bot_username
AGENT_API_URL=http://localhost:10000
```

### 3. Установка зависимостей

```bash
# С использованием uv
uv sync

# Или pip
pip install -e .
```

### 4. Запуск

```bash
# Локально
python main.py

# Или через uv
uv run python main.py
```

## Docker

### Сборка образа

```bash
docker build -t meeting-assistant-telegram-bot .
```

### Запуск контейнера

```bash
docker run --rm --env-file .env meeting-assistant-telegram-bot
```

### Docker Compose

```yaml
version: '3.8'

services:
  telegram-bot:
    build: .
    container_name: meeting-assistant-bot
    restart: unless-stopped
    env_file:
      - .env
```

```bash
docker-compose up -d
```

## Использование

### Команды

- `/start` — главное меню (с авто-подключением к агенту, если задана `AUTO_CONNECT_ON_START=true`)
- `/upcoming [N]` — предстоящие встречи на N дней (по умолчанию 7)
- `/summary <conference_id>` — краткое саммари созвона по его ID
- `/search <запрос>` — поиск по транскрипциям через RAG
- `/help` — список команд

### Примеры запросов к агенту

После подключения к агенту вы можете отправлять текстовые сообщения:

**Создание встреч:**
```
Создай встречу "Обсуждение релиза" на завтра в 14:00 на час
Запланируй созвон с командой в пятницу в 10:00
```

**Подключение к созвонам:**
```
Подключись к созвону https://meet.google.com/xxx-xxx-xxx
Запиши встречу по ссылке https://zoom.us/j/123456789
```

**Поиск по встречам:**
```
О чём говорили на прошлой встрече?
Найди все упоминания бюджета
Какие задачи назначили Васе за последнюю неделю?
```

**Список созвонов:**
```
Покажи последние созвоны
Какие встречи были на этой неделе?
```

## Конфигурация

| Переменная | Описание | Обязательно |
|-----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота от BotFather | Да |
| `TELEGRAM_BOT_USERNAME` | Username бота (без @) | Да |
| `AGENT_API_URL` | URL A2A агента | Да |
| `HANDLE_MESSAGE_EDITS` | Обрабатывать редактирование сообщений | Нет (default: true) |
| `EDIT_RESPONSE_TIMEOUT` | Таймаут для отмены запроса при редактировании (сек) | Нет (default: 30) |
| `AUTO_CONNECT_ON_START` | Подключаться к агенту сразу при `/start` | Нет (default: true) |

## Структура проекта

```
telegram-bot/
├── main.py                 # Точка входа
├── config/
│   ├── __init__.py
│   └── config.py           # Конфигурация через pydantic-settings
├── src/
│   ├── handlers/
│   │   ├── __init__.py
│   │   └── common.py       # Обработчики команд и сообщений
│   ├── keyboards/
│   │   └── __init__.py     # Inline клавиатуры
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent_connector.py  # Интеграция с A2A агентом
│   │   └── request_manager.py  # Управление запросами
│   └── utils/
│       ├── __init__.py
│       └── session.py      # Управление сессиями пользователей
├── tests/
│   ├── __init__.py
│   └── test_bot.py
├── pyproject.toml
├── Dockerfile
├── .env.example
└── README.md
```

## Устранение неполадок

### Бот не отвечает

1. Проверьте что `TELEGRAM_BOT_TOKEN` корректен
2. Убедитесь что бот запущен (`python main.py`)
3. Проверьте логи на наличие ошибок

### Нет ответа от агента

1. Проверьте что `AGENT_API_URL` корректен
2. Убедитесь что агент доступен по сети
3. Проверьте что агент задеплоен и работает

### Ошибки подключения

1. Проверьте интернет-соединение
2. Убедитесь что URL агента доступен
3. Попробуйте переподключиться через меню бота

## Разработка

### Запуск тестов

```bash
pytest tests/ -v
```

### Форматирование кода

```bash
black .
ruff check .
```

## Технологии

- Python 3.11+
- aiogram 3 (Telegram Bot API)
- httpx (HTTP клиент)
- pydantic-settings (конфигурация)
