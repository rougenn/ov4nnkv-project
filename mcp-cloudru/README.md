# MCP Cloud.ru Server

MCP сервер для работы с сервисами Cloud.ru:
- **S3 Object Storage** — загрузка, скачивание, список файлов
- **Managed RAG** — семантический поиск по базе знаний

## Инструменты (Tools)

### S3 Tools

| Tool | Описание |
|------|----------|
| `s3_list_buckets` | Список S3 бакетов |
| `s3_list_objects` | Список файлов в бакете |
| `s3_upload_text` | Загрузка текстового файла |
| `s3_download_text` | Скачивание текстового файла |
| `s3_delete_file` | Удаление файла |

### RAG Tools

| Tool | Описание |
|------|----------|
| `rag_search` | Семантический поиск по базе знаний |
| `rag_search_advanced` | Поиск с ререйнкингом для лучшей релевантности |

## Конфигурация

### Переменные окружения

```env
# Cloud.ru Credentials
CLOUD_TENANT_ID=your-tenant-id
CLOUD_KEY_ID=your-key-id
CLOUD_SECRET=your-secret-key

# S3 Configuration
S3_BUCKET=your-bucket-name
S3_ENDPOINT=https://s3.cloud.ru
S3_REGION=ru-central-1

# RAG Configuration
RAG_PUBLIC_URL=https://your-kb.managed-rag.inference.cloud.ru
RAG_VERSION_ID=your-version-id

# Server
PORT=8000
```

## Запуск

### Локально

```bash
# Установка зависимостей
uv sync

# Запуск
uv run python src/server.py
```

### Docker

```bash
# Сборка
docker build -t mcp-cloudru .

# Запуск
docker run -p 8000:8000 \
  -e CLOUD_TENANT_ID=... \
  -e CLOUD_KEY_ID=... \
  -e CLOUD_SECRET=... \
  -e S3_BUCKET=... \
  -e RAG_PUBLIC_URL=... \
  -e RAG_VERSION_ID=... \
  mcp-cloudru
```

## API

MCP сервер доступен по адресу: `http://localhost:8000/mcp`

### Пример вызова

```bash
# Список бакетов
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "s3_list_buckets"}}'

# Поиск по RAG
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "rag_search", "arguments": {"query": "что обсуждали на встрече"}}}'
```





