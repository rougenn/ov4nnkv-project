"""MCP сервер для Cloud.ru - S3 и RAG инструменты.

Предоставляет tools для:
- Работы с S3 Object Storage (загрузка, скачивание, список файлов)
- Поиска по базе знаний RAG (семантический поиск)
"""

import logging
import os
from typing import Annotated

from dotenv import load_dotenv, find_dotenv
from fastmcp import FastMCP
from pydantic import Field

try:
    from .s3_client import CloudRuS3Client, CloudRuS3Error
    from .rag_client import CloudRuRAGClient, CloudRuRAGError
except ImportError:
    from s3_client import CloudRuS3Client, CloudRuS3Error
    from rag_client import CloudRuRAGClient, CloudRuRAGError

# Load environment variables
load_dotenv(find_dotenv())

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mcp-cloudru")

# Configuration
PORT = int(os.getenv("PORT", "8000"))

# Initialize MCP server
mcp = FastMCP(
    name="mcp-cloudru",
    instructions="""MCP сервер для работы с Cloud.ru сервисами:
- S3 Object Storage: загрузка, скачивание, список файлов
- Managed RAG: семантический поиск по базе знаний"""
)


def _get_s3_client() -> CloudRuS3Client:
    """Создать S3 клиент."""
    return CloudRuS3Client()


# Singleton RAG клиент для сохранения обновлённой версии между вызовами
_rag_client_instance: CloudRuRAGClient | None = None


def _get_rag_client() -> CloudRuRAGClient:
    """Получить RAG клиент (singleton для сохранения версии)."""
    global _rag_client_instance
    if _rag_client_instance is None:
        _rag_client_instance = CloudRuRAGClient()
    return _rag_client_instance


# ============================================
# S3 Tools
# ============================================

@mcp.tool()
async def s3_list_buckets() -> dict:
    """Получить список S3 бакетов в Cloud.ru.
    
    Возвращает список всех доступных бакетов с датой создания.
    """
    try:
        client = _get_s3_client()
        buckets = client.list_buckets()
        
        return {
            "success": True,
            "count": len(buckets),
            "buckets": buckets,
        }
    except CloudRuS3Error as e:
        logger.error(f"Ошибка S3: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


@mcp.tool()
async def s3_list_objects(
    bucket: Annotated[str | None, Field(
        default=None,
        description="Имя бакета (если не указано, используется S3_BUCKET из конфигурации)"
    )] = None,
    prefix: Annotated[str, Field(
        default="",
        description="Префикс для фильтрации объектов (например, 'documents/')"
    )] = "",
    max_keys: Annotated[int, Field(
        default=50,
        ge=1,
        le=1000,
        description="Максимальное количество объектов (1-1000)"
    )] = 50,
) -> dict:
    """Получить список файлов в S3 бакете.
    
    Возвращает список объектов с информацией о размере и дате изменения.
    Поддерживает фильтрацию по префиксу.
    """
    try:
        client = _get_s3_client()
        result = client.list_objects(
            bucket=bucket,
            prefix=prefix,
            max_keys=max_keys
        )
        
        return {
            "success": True,
            **result
        }
    except CloudRuS3Error as e:
        logger.error(f"Ошибка S3: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


@mcp.tool()
async def s3_upload_text(
    key: Annotated[str, Field(
        description="Ключ объекта (путь в бакете, например: 'documents/report.txt')"
    )],
    content: Annotated[str, Field(
        description="Текстовое содержимое файла"
    )],
    bucket: Annotated[str | None, Field(
        default=None,
        description="Имя бакета (если не указано, используется S3_BUCKET)"
    )] = None,
    content_type: Annotated[str, Field(
        default="text/plain",
        description="MIME тип (text/plain, text/markdown, application/json и т.д.)"
    )] = "text/plain",
) -> dict:
    """Загрузить текстовый файл в S3 бакет.
    
    Используйте для загрузки текстовых документов, markdown файлов, JSON и т.д.
    """
    if not key or not key.strip():
        return {
            "success": False,
            "error": {
                "code": "INVALID_KEY",
                "message": "Ключ объекта не может быть пустым"
            }
        }
    
    if not content:
        return {
            "success": False,
            "error": {
                "code": "EMPTY_CONTENT",
                "message": "Содержимое файла не может быть пустым"
            }
        }
    
    try:
        client = _get_s3_client()
        result = client.upload_file(
            key=key.strip(),
            content=content,
            bucket=bucket,
            content_type=content_type
        )
        
        return {
            "success": True,
            "message": f"Файл успешно загружен: {key}",
            **result
        }
    except CloudRuS3Error as e:
        logger.error(f"Ошибка S3: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


@mcp.tool()
async def s3_download_text(
    key: Annotated[str, Field(
        description="Ключ объекта (путь в бакете)"
    )],
    bucket: Annotated[str | None, Field(
        default=None,
        description="Имя бакета"
    )] = None,
) -> dict:
    """Скачать текстовый файл из S3 бакета.
    
    Возвращает содержимое файла как текст.
    """
    if not key or not key.strip():
        return {
            "success": False,
            "error": {
                "code": "INVALID_KEY",
                "message": "Ключ объекта не может быть пустым"
            }
        }
    
    try:
        client = _get_s3_client()
        result = client.download_file(key=key.strip(), bucket=bucket)
        
        # Декодируем содержимое как текст
        content = result.pop("content")
        try:
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            text_content = content.decode('latin-1')
        
        return {
            "success": True,
            "content": text_content,
            **result
        }
    except CloudRuS3Error as e:
        logger.error(f"Ошибка S3: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


@mcp.tool()
async def s3_delete_file(
    key: Annotated[str, Field(
        description="Ключ объекта для удаления"
    )],
    bucket: Annotated[str | None, Field(
        default=None,
        description="Имя бакета"
    )] = None,
) -> dict:
    """Удалить файл из S3 бакета.
    
    Внимание: операция необратима!
    """
    if not key or not key.strip():
        return {
            "success": False,
            "error": {
                "code": "INVALID_KEY",
                "message": "Ключ объекта не может быть пустым"
            }
        }
    
    try:
        client = _get_s3_client()
        result = client.delete_file(key=key.strip(), bucket=bucket)
        
        return {
            "success": True,
            "message": f"Файл успешно удалён: {key}",
            **result
        }
    except CloudRuS3Error as e:
        logger.error(f"Ошибка S3: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


# ============================================
# RAG Tools
# ============================================

@mcp.tool()
async def rag_search(
    query: Annotated[str, Field(
        description="Поисковый запрос на естественном языке"
    )],
    num_results: Annotated[int, Field(
        default=5,
        ge=1,
        le=20,
        description="Количество результатов (1-20)"
    )] = 5,
) -> dict:
    """Семантический поиск по базе знаний RAG.
    
    Выполняет поиск по индексированным документам и возвращает
    наиболее релевантные фрагменты.
    
    Используйте для:
    - Поиска информации в документах
    - Ответов на вопросы по содержимому базы знаний
    - Нахождения релевантных фрагментов текста
    """
    if not query or not query.strip():
        return {
            "success": False,
            "error": {
                "code": "EMPTY_QUERY",
                "message": "Поисковый запрос не может быть пустым"
            }
        }
    
    try:
        client = _get_rag_client()
        result = client.retrieve(
            query=query.strip(),
            num_results=num_results
        )
        
        return result
    except CloudRuRAGError as e:
        logger.error(f"Ошибка RAG: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


@mcp.tool()
async def rag_search_advanced(
    query: Annotated[str, Field(
        description="Поисковый запрос на естественном языке"
    )],
    num_results: Annotated[int, Field(
        default=10,
        ge=1,
        le=50,
        description="Количество результатов первичного поиска (1-50)"
    )] = 10,
    num_reranked: Annotated[int, Field(
        default=5,
        ge=1,
        le=20,
        description="Количество результатов после ререйнкинга (1-20)"
    )] = 5,
    retrieval_type: Annotated[str, Field(
        default="SEMANTIC",
        description="Тип поиска: SEMANTIC, KEYWORD или HYBRID"
    )] = "SEMANTIC",
) -> dict:
    """Продвинутый поиск по базе знаний RAG с ререйнкингом.
    
    Выполняет двухэтапный поиск:
    1. Первичный поиск для получения кандидатов
    2. Ререйнкинг для улучшения релевантности результатов
    
    Используйте для более точных результатов поиска.
    """
    if not query or not query.strip():
        return {
            "success": False,
            "error": {
                "code": "EMPTY_QUERY",
                "message": "Поисковый запрос не может быть пустым"
            }
        }
    
    if retrieval_type not in ("SEMANTIC", "KEYWORD", "HYBRID"):
        return {
            "success": False,
            "error": {
                "code": "INVALID_RETRIEVAL_TYPE",
                "message": "retrieval_type должен быть SEMANTIC, KEYWORD или HYBRID"
            }
        }
    
    try:
        client = _get_rag_client()
        result = client.retrieve_with_reranking(
            query=query.strip(),
            num_results=num_results,
            num_reranked=num_reranked,
            retrieval_type=retrieval_type
        )
        
        return result
    except CloudRuRAGError as e:
        logger.error(f"Ошибка RAG: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


@mcp.tool()
async def rag_start_indexing(
    s3_prefix: Annotated[str, Field(
        default="",
        description="Префикс в S3 бакете для индексации (например, 'documents/'). Пустая строка = весь бакет"
    )] = "",
    description: Annotated[str, Field(
        default="",
        description="Описание новой версии RAG"
    )] = "",
    extensions: Annotated[str, Field(
        default="txt,md,pdf",
        description="Расширения файлов через запятую (например: 'txt,md,pdf')"
    )] = "txt,md,pdf",
) -> dict:
    """Запустить индексацию RAG — создание новой версии базы знаний.
    
    Сканирует документы в S3 бакете и создаёт новую версию RAG с индексированными данными.
    
    Поддерживаемые форматы: txt, md, pdf
    
    Используйте когда:
    - Добавили новые документы в S3
    - Нужно обновить базу знаний
    - Хотите переиндексировать документы
    
    После запуска индексация выполняется асинхронно (несколько минут).
    Новая версия RAG станет доступна после завершения.
    """
    try:
        # Парсим расширения
        ext_list = [e.strip().lower() for e in extensions.split(",") if e.strip()]
        if not ext_list:
            ext_list = ["txt", "md", "pdf"]
        
        # Проверяем допустимые расширения
        valid_extensions = {"txt", "md", "pdf"}
        invalid = set(ext_list) - valid_extensions
        if invalid:
            return {
                "success": False,
                "error": {
                    "code": "INVALID_EXTENSIONS",
                    "message": f"Недопустимые расширения: {invalid}. Допустимы: txt, md, pdf"
                }
            }
        
        client = _get_rag_client()
        result = client.start_indexing(
            s3_prefix=s3_prefix.strip(),
            description=description.strip(),
            extensions=ext_list
        )
        
        return result
    except CloudRuRAGError as e:
        logger.error(f"Ошибка RAG индексации: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


@mcp.tool()
async def rag_get_versions() -> dict:
    """Получить список всех версий RAG с их статусами.
    
    Возвращает список версий базы знаний с информацией:
    - ID версии
    - Статус (READY, RUNNING, FAILED)
    - Дата создания
    - Описание
    
    Используйте для:
    - Проверки статуса индексации
    - Просмотра доступных версий
    - Выбора версии для использования
    """
    try:
        client = _get_rag_client()
        result = client.get_versions()
        return result
    except CloudRuRAGError as e:
        logger.error(f"Ошибка получения версий: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


@mcp.tool()
async def rag_update_version() -> dict:
    """Обновить RAG на последнюю готовую версию.
    
    Автоматически находит последнюю версию со статусом READY
    и переключает поиск на неё.
    
    Используйте после завершения индексации, чтобы:
    - Начать использовать новую версию базы знаний
    - Не менять RAG_VERSION_ID вручную
    
    Возвращает старую и новую версию для подтверждения.
    """
    try:
        client = _get_rag_client()
        result = client.update_to_latest_version()
        return result
    except CloudRuRAGError as e:
        logger.error(f"Ошибка обновления версии: {e.message}")
        return {
            "success": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        }


def main():
    """Запуск MCP сервера."""
    print("=" * 60)
    print("☁️  CLOUD.RU MCP SERVER")
    print("=" * 60)
    print(f"🚀 MCP Server: http://0.0.0.0:{PORT}/mcp")
    print("=" * 60)
    
    # Проверяем конфигурацию
    tenant_id = os.getenv("CLOUD_TENANT_ID")
    key_id = os.getenv("CLOUD_KEY_ID")
    key_secret = os.getenv("CLOUD_SECRET")
    s3_bucket = os.getenv("S3_BUCKET")
    rag_url = os.getenv("RAG_PUBLIC_URL")
    rag_version = os.getenv("RAG_VERSION_ID")
    
    print("\n📋 Конфигурация:")
    print(f"   CLOUD_TENANT_ID: {'✅' if tenant_id else '❌ не установлен'}")
    print(f"   CLOUD_KEY_ID: {'✅' if key_id else '❌ не установлен'}")
    print(f"   CLOUD_SECRET: {'✅' if key_secret else '❌ не установлен'}")
    print(f"   S3_BUCKET: {s3_bucket or '❌ не установлен'}")
    print(f"   RAG_PUBLIC_URL: {'✅' if rag_url else '❌ не установлен'}")
    print(f"   RAG_VERSION_ID: {rag_version[:8] + '...' if rag_version else '❌ не установлен'}")
    
    if not all([tenant_id, key_id, key_secret]):
        print("\n⚠️  ВНИМАНИЕ: Не все credentials настроены!")
        print("   Установите CLOUD_TENANT_ID, CLOUD_KEY_ID, CLOUD_SECRET")
    
    print("\n" + "=" * 60)
    
    mcp.run(transport="streamable-http", host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()





