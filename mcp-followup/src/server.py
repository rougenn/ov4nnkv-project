"""MCP сервер для интеграции с Follow-Up API.

Предоставляет tools для:
- Подключения бота к созвонам
- Получения транскрипций
- Просмотра списка записанных созвонов
"""

import logging
import os
import re
from typing import Annotated

from dotenv import load_dotenv, find_dotenv
from fastmcp import FastMCP
from pydantic import Field

try:
    from .followup_client import (
        FollowUpClient,
        FollowUpAPIError,
        AuthenticationError,
        NetworkError,
    )
except ImportError:
    from followup_client import (
        FollowUpClient,
        FollowUpAPIError,
        AuthenticationError,
        NetworkError,
    )

# Load environment variables
load_dotenv(find_dotenv())

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mcp-followup")

# Configuration
PORT = int(os.getenv("PORT", "8000"))
FOLLOWUP_EMAIL = os.getenv("FOLLOWUP_EMAIL")
FOLLOWUP_PASSWORD = os.getenv("FOLLOWUP_PASSWORD")
FOLLOWUP_API_KEY = os.getenv("FOLLOWUP_API_KEY")
FOLLOWUP_API_URL = os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech")

# Initialize MCP server
mcp = FastMCP(
    name="mcp-followup",
    instructions="MCP сервер для работы с Follow-Up API - запись и транскрибация корпоративных созвонов"
)


def _get_client() -> FollowUpClient:
    """Создать клиент Follow-Up API."""
    return FollowUpClient(
        email=FOLLOWUP_EMAIL,
        password=FOLLOWUP_PASSWORD,
        api_key=FOLLOWUP_API_KEY,
        base_url=FOLLOWUP_API_URL,
    )


def _is_valid_url(url: str) -> bool:
    """Проверить, что строка является валидным URL."""
    url_pattern = re.compile(
        r'^https?://'  # http:// или https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # домен
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # порт
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return url_pattern.match(url) is not None


def _is_conference_url(url: str) -> bool:
    """Проверить, что URL похож на ссылку для видеоконференции."""
    conference_domains = [
        "meet.google.com",
        "zoom.us", "zoom.com",
        "teams.microsoft.com", "teams.live.com",
        "telemost.yandex.ru", "telemost.yandex.com",
        "salutejazz.ru", "jazz.sber.ru",
        "konturtalk.ru",
        "meet.jit.si",
    ]
    url_lower = url.lower()
    return any(domain in url_lower for domain in conference_domains)


@mcp.tool()
async def join_conference(
    conference_url: Annotated[str, Field(
        description="Ссылка на созвон (Zoom, Google Meet, MS Teams, Яндекс Телемост, SaluteJazz, КонтурТолк, JitsiMeet)"
    )],
    theme: Annotated[str, Field(
        default="Созвон",
        description="Название/тема созвона для идентификации в списке записей"
    )] = "Созвон"
) -> dict:
    """Подключить бота Follow-Up к созвону для записи и транскрибации.
    
    Бот присоединится к указанному созвону и начнёт запись.
    После завершения созвона транскрипция будет доступна через get_transcription.
    
    Поддерживаемые платформы:
    - Google Meet
    - Zoom
    - Microsoft Teams
    - Яндекс Телемост
    - SaluteJazz
    - КонтурТолк
    - JitsiMeet
    """
    # Валидация URL
    if not conference_url or not conference_url.strip():
        return {
            "success": False,
            "error": {
                "code": "INVALID_URL",
                "message": "URL созвона не может быть пустым"
            }
        }
    
    conference_url = conference_url.strip()
    
    if not _is_valid_url(conference_url):
        return {
            "success": False,
            "error": {
                "code": "INVALID_URL",
                "message": "Указан невалидный URL. Ожидается ссылка вида https://meet.google.com/xxx-xxx-xxx"
            }
        }
    
    if not _is_conference_url(conference_url):
        logger.warning(f"URL не распознан как известная платформа ВКС: {conference_url}")
        # Не блокируем, но предупреждаем — возможно это новая/неизвестная платформа
    
    try:
        async with _get_client() as client:
            result = await client.join_conference(
                conference_url=conference_url,
                theme=theme
            )
            
            # Формируем структурированный ответ
            conference_id = result.get("id") or result.get("conferenceId") or result.get("conference_id")
            
            return {
                "success": True,
                "conference_id": conference_id,
                "message": f"Бот успешно подключается к созвону. ID конференции: {conference_id}",
                "details": {
                    "url": conference_url,
                    "theme": theme,
                    "status": result.get("status", "connecting"),
                }
            }
            
    except AuthenticationError as e:
        logger.error(f"Ошибка авторизации: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "AUTH_ERROR",
                "message": "Ошибка авторизации в Follow-Up API. Проверьте API-ключ или учётные данные."
            }
        }
    except NetworkError as e:
        logger.error(f"Сетевая ошибка: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "NETWORK_ERROR",
                "message": f"Не удалось подключиться к серверу Follow-Up: {e.message}"
            }
        }
    except FollowUpAPIError as e:
        logger.error(f"Ошибка API: {e.message} (status={e.status_code})")
        
        # Интерпретируем типичные ошибки
        error_code = "API_ERROR"
        error_message = e.message
        
        if e.status_code == 400:
            error_code = "INVALID_REQUEST"
            error_message = "Невалидная ссылка на созвон или созвон уже завершён"
        elif e.status_code == 404:
            error_code = "NOT_FOUND"
            error_message = "Созвон не найден или недоступен"
        elif e.status_code == 409:
            error_code = "ALREADY_CONNECTED"
            error_message = "Бот уже подключен к этому созвону"
        
        return {
            "success": False,
            "error": {
                "code": error_code,
                "message": error_message,
                "status_code": e.status_code,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"Внутренняя ошибка: {str(e)}"
            }
        }


@mcp.tool()
async def get_transcription(
    conference_id: Annotated[str, Field(
        description="ID созвона из Follow-Up (UUID формат, например: 34faff15-20a3-4dee-b212-3c0a3604e239)"
    )]
) -> dict:
    """Получить транскрипцию завершённого созвона.
    
    Возвращает полный текст транскрипции с метаданными:
    - Название встречи
    - Дата и время
    - Длительность
    - Список участников
    - Текст транскрипции
    
    Транскрипция доступна только после завершения созвона и обработки записи.
    """
    # Валидация conference_id
    if not conference_id or not conference_id.strip():
        return {
            "success": False,
            "error": {
                "code": "INVALID_ID",
                "message": "ID конференции не может быть пустым"
            }
        }
    
    conference_id = conference_id.strip()
    
    # Проверка формата UUID
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    if not uuid_pattern.match(conference_id):
        return {
            "success": False,
            "error": {
                "code": "INVALID_ID",
                "message": "Некорректный формат ID конференции. Ожидается UUID (например: 34faff15-20a3-4dee-b212-3c0a3604e239)"
            }
        }
    
    try:
        async with _get_client() as client:
            result = await client.get_transcription(conference_id)
            
            conference_info = result.get("conference_info", {})
            transcription_data = result.get("transcription", {})
            
            # Извлекаем участников
            participants = []
            if "participants" in conference_info:
                participants = [p.get("name", p.get("email", "Unknown")) for p in conference_info.get("participants", [])]
            
            # Извлекаем текст транскрипции
            transcription_text = ""
            if isinstance(transcription_data, dict):
                # Транскрипция может быть в разных форматах
                transcription_text = transcription_data.get("text", "")
                if not transcription_text and "transcription" in transcription_data:
                    transcription_text = transcription_data.get("transcription", "")
                if not transcription_text and "content" in transcription_data:
                    transcription_text = transcription_data.get("content", "")
                # Если транскрипция в виде сегментов
                if not transcription_text and "segments" in transcription_data:
                    segments = transcription_data.get("segments", [])
                    transcription_text = "\n".join([
                        f"{s.get('speaker', 'Speaker')}: {s.get('text', '')}" 
                        for s in segments
                    ])
            elif isinstance(transcription_data, str):
                transcription_text = transcription_data
            elif isinstance(transcription_data, list):
                # Если это список сегментов
                transcription_text = "\n".join([
                    f"{s.get('speaker', 'Speaker')}: {s.get('text', '')}" 
                    for s in transcription_data if isinstance(s, dict)
                ])
            
            # Вычисляем длительность
            duration_minutes = None
            if conference_info.get("duration"):
                duration_minutes = int(conference_info.get("duration", 0) / 60)
            elif conference_info.get("durationMinutes"):
                duration_minutes = conference_info.get("durationMinutes")
            elif conference_info.get("startedAt") and conference_info.get("endedAt"):
                # Можно вычислить из времени начала и конца
                pass
            
            return {
                "success": True,
                "conference_id": conference_id,
                "title": conference_info.get("theme") or conference_info.get("title") or conference_info.get("name", "Без названия"),
                "date": conference_info.get("startedAt") or conference_info.get("createdAt") or conference_info.get("date"),
                "duration_minutes": duration_minutes,
                "participants": participants,
                "transcription": transcription_text,
                "status": conference_info.get("status", "unknown"),
            }
            
    except AuthenticationError as e:
        logger.error(f"Ошибка авторизации: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "AUTH_ERROR",
                "message": "Ошибка авторизации в Follow-Up API. Проверьте API-ключ или учётные данные."
            }
        }
    except NetworkError as e:
        logger.error(f"Сетевая ошибка: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "NETWORK_ERROR",
                "message": f"Не удалось подключиться к серверу Follow-Up: {e.message}"
            }
        }
    except FollowUpAPIError as e:
        logger.error(f"Ошибка API: {e.message} (status={e.status_code})")
        
        error_code = "API_ERROR"
        error_message = e.message
        
        if e.status_code == 404:
            error_code = "NOT_FOUND"
            error_message = "Созвон не найден. Проверьте правильность ID конференции."
        elif e.status_code == 400:
            error_code = "TRANSCRIPTION_NOT_READY"
            error_message = "Транскрипция ещё не готова. Созвон может быть в процессе или обработка записи не завершена."
        elif e.status_code == 403:
            error_code = "NO_RECORDING"
            error_message = "Созвон без записи или доступ к транскрипции запрещён."
        
        return {
            "success": False,
            "error": {
                "code": error_code,
                "message": error_message,
                "status_code": e.status_code,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"Внутренняя ошибка: {str(e)}"
            }
        }


@mcp.tool()
async def list_conferences(
    limit: Annotated[int, Field(
        default=20,
        ge=1,
        le=100,
        description="Количество записей (от 1 до 100)"
    )] = 20,
    offset: Annotated[int, Field(
        default=0,
        ge=0,
        description="Смещение для пагинации (начиная с 0)"
    )] = 0
) -> dict:
    """Получить список записанных созвонов.
    
    Возвращает список всех созвонов с базовой информацией:
    - ID созвона
    - Название/тема
    - Дата проведения
    - Длительность
    - Статус
    
    Поддерживает пагинацию через параметры limit и offset.
    """
    # Валидация параметров уже выполнена Pydantic через Field constraints
    # Но добавим дополнительную проверку на случай прямого вызова
    if limit < 1:
        return {
            "success": False,
            "error": {
                "code": "INVALID_PARAMETER",
                "message": "Параметр limit должен быть >= 1"
            }
        }
    
    if limit > 100:
        return {
            "success": False,
            "error": {
                "code": "INVALID_PARAMETER",
                "message": "Параметр limit не может превышать 100"
            }
        }
    
    if offset < 0:
        return {
            "success": False,
            "error": {
                "code": "INVALID_PARAMETER",
                "message": "Параметр offset должен быть >= 0"
            }
        }
    
    try:
        async with _get_client() as client:
            result = await client.list_conferences(limit=limit, offset=offset)
            
            conferences_raw = result.get("conferences", [])
            total = result.get("total", len(conferences_raw))
            
            # Форматируем список созвонов
            conferences = []
            for conf in conferences_raw:
                # Вычисляем длительность в минутах
                duration_minutes = None
                if conf.get("duration"):
                    duration_minutes = int(conf.get("duration", 0) / 60)
                elif conf.get("durationMinutes"):
                    duration_minutes = conf.get("durationMinutes")
                
                conferences.append({
                    "id": conf.get("id"),
                    "title": conf.get("theme") or conf.get("title") or conf.get("name", "Без названия"),
                    "date": conf.get("startedAt") or conf.get("createdAt") or conf.get("date"),
                    "duration_minutes": duration_minutes,
                    "status": conf.get("status", "unknown"),
                })
            
            return {
                "success": True,
                "total": total,
                "limit": limit,
                "offset": offset,
                "conferences": conferences,
            }
            
    except AuthenticationError as e:
        logger.error(f"Ошибка авторизации: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "AUTH_ERROR",
                "message": "Ошибка авторизации в Follow-Up API. Проверьте API-ключ или учётные данные."
            }
        }
    except NetworkError as e:
        logger.error(f"Сетевая ошибка: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "NETWORK_ERROR",
                "message": f"Не удалось подключиться к серверу Follow-Up: {e.message}"
            }
        }
    except FollowUpAPIError as e:
        logger.error(f"Ошибка API: {e.message} (status={e.status_code})")
        return {
            "success": False,
            "error": {
                "code": "API_ERROR",
                "message": e.message,
                "status_code": e.status_code,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"Внутренняя ошибка: {str(e)}"
            }
        }


@mcp.tool()
async def get_conference_info(
    conference_id: Annotated[str, Field(
        description="ID созвона из Follow-Up (UUID формат, например: 34faff15-20a3-4dee-b212-3c0a3604e239)"
    )]
) -> dict:
    """Получить метаданные созвона (без транскрипции).
    
    Возвращает информацию о созвоне:
    - ID созвона
    - Название/тема
    - Дата и время
    - Длительность
    - Список участников
    - Статус созвона
    - Наличие транскрипции
    
    Полезно для проверки статуса созвона или получения метаданных
    без загрузки полной транскрипции.
    """
    # Валидация conference_id
    if not conference_id or not conference_id.strip():
        return {
            "success": False,
            "error": {
                "code": "INVALID_ID",
                "message": "ID конференции не может быть пустым"
            }
        }
    
    conference_id = conference_id.strip()
    
    # Проверка формата UUID
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    if not uuid_pattern.match(conference_id):
        return {
            "success": False,
            "error": {
                "code": "INVALID_ID",
                "message": "Некорректный формат ID конференции. Ожидается UUID (например: 34faff15-20a3-4dee-b212-3c0a3604e239)"
            }
        }
    
    try:
        async with _get_client() as client:
            conference_info = await client.get_conference_info(conference_id)
            
            # Извлекаем участников
            participants = []
            if "participants" in conference_info:
                participants = [
                    p.get("name", p.get("email", "Unknown")) 
                    for p in conference_info.get("participants", [])
                ]
            
            # Вычисляем длительность в минутах
            duration_minutes = None
            if conference_info.get("duration"):
                duration_minutes = int(conference_info.get("duration", 0) / 60)
            elif conference_info.get("durationMinutes"):
                duration_minutes = conference_info.get("durationMinutes")
            
            # Определяем статус
            status = conference_info.get("status", "unknown")
            
            # Определяем наличие транскрипции
            # Транскрипция обычно доступна когда статус "ready" или "completed"
            has_transcription = status in ("ready", "completed", "transcribed")
            if "hasTranscription" in conference_info:
                has_transcription = conference_info.get("hasTranscription", False)
            elif "transcription" in conference_info:
                has_transcription = bool(conference_info.get("transcription"))
            
            return {
                "success": True,
                "id": conference_id,
                "title": conference_info.get("theme") or conference_info.get("title") or conference_info.get("name", "Без названия"),
                "date": conference_info.get("startedAt") or conference_info.get("createdAt") or conference_info.get("date"),
                "duration_minutes": duration_minutes,
                "participants": participants,
                "status": status,
                "has_transcription": has_transcription,
            }
            
    except AuthenticationError as e:
        logger.error(f"Ошибка авторизации: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "AUTH_ERROR",
                "message": "Ошибка авторизации в Follow-Up API. Проверьте API-ключ или учётные данные."
            }
        }
    except NetworkError as e:
        logger.error(f"Сетевая ошибка: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "NETWORK_ERROR",
                "message": f"Не удалось подключиться к серверу Follow-Up: {e.message}"
            }
        }
    except FollowUpAPIError as e:
        logger.error(f"Ошибка API: {e.message} (status={e.status_code})")
        
        error_code = "API_ERROR"
        error_message = e.message
        
        if e.status_code == 404 or e.status_code == 403:
            error_code = "NOT_FOUND"
            error_message = "Созвон не найден или доступ запрещён. Проверьте правильность ID конференции."
        
        return {
            "success": False,
            "error": {
                "code": error_code,
                "message": error_message,
                "status_code": e.status_code,
                "details": e.details
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"Внутренняя ошибка: {str(e)}"
            }
        }


@mcp.tool()
async def download_conference_pdf(
    conference_id: Annotated[str, Field(
        description="ID созвона из Follow-Up (UUID формат, например: 34faff15-20a3-4dee-b212-3c0a3604e239)"
    )]
) -> dict:
    """Скачать PDF отчёт с транскрипцией созвона.
    
    Возвращает PDF файл в формате base64 для дальнейшего сохранения или отправки.
    PDF содержит полную транскрипцию созвона в отформатированном виде.
    
    Используйте этот инструмент когда пользователь просит:
    - "Скачай PDF отчёт по созвону"
    - "Сохрани транскрипцию в PDF"
    - "Экспортируй созвон в PDF"
    - "Дай мне PDF файл встречи"
    """
    import base64
    
    # Валидация conference_id
    if not conference_id or not conference_id.strip():
        return {
            "success": False,
            "error": {
                "code": "INVALID_ID",
                "message": "ID конференции не может быть пустым"
            }
        }
    
    conference_id = conference_id.strip()
    
    # Проверка формата UUID
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    if not uuid_pattern.match(conference_id):
        return {
            "success": False,
            "error": {
                "code": "INVALID_ID",
                "message": "Некорректный формат ID конференции. Ожидается UUID"
            }
        }
    
    # Проверяем что есть email/password для авторизации
    if not FOLLOWUP_EMAIL or not FOLLOWUP_PASSWORD:
        return {
            "success": False,
            "error": {
                "code": "CONFIG_ERROR",
                "message": "Для скачивания PDF требуются FOLLOWUP_EMAIL и FOLLOWUP_PASSWORD"
            }
        }
    
    try:
        async with _get_client() as client:
            # Скачиваем PDF
            pdf_bytes = await client.download_pdf(conference_id)
            
            # Кодируем в base64 для передачи
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            
            # Получаем информацию о конференции для имени файла
            try:
                conf_info = await client.get_conference_info(conference_id)
                title = conf_info.get("theme") or conf_info.get("title") or "conference"
                # Очищаем название для имени файла
                safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:50]
            except Exception:
                safe_title = "conference"
            
            filename = f"{safe_title}_{conference_id[:8]}.pdf"
            
            return {
                "success": True,
                "conference_id": conference_id,
                "filename": filename,
                "content_type": "application/pdf",
                "size_bytes": len(pdf_bytes),
                "pdf_base64": pdf_base64,
                "message": f"PDF отчёт успешно скачан ({len(pdf_bytes)} bytes)"
            }
            
    except AuthenticationError as e:
        logger.error(f"Ошибка авторизации: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "AUTH_ERROR",
                "message": "Ошибка авторизации. Проверьте FOLLOWUP_EMAIL и FOLLOWUP_PASSWORD."
            }
        }
    except NetworkError as e:
        logger.error(f"Сетевая ошибка: {e.message}")
        return {
            "success": False,
            "error": {
                "code": "NETWORK_ERROR",
                "message": f"Сетевая ошибка: {e.message}"
            }
        }
    except FollowUpAPIError as e:
        logger.error(f"Ошибка API: {e.message}")
        
        error_code = "API_ERROR"
        error_message = e.message
        
        if e.status_code == 404:
            error_code = "NOT_FOUND"
            error_message = "Созвон не найден или PDF недоступен"
        
        return {
            "success": False,
            "error": {
                "code": error_code,
                "message": error_message,
                "status_code": e.status_code
            }
        }
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"Внутренняя ошибка: {str(e)}"
            }
        }


def main():
    """Запуск MCP сервера."""
    print("=" * 60)
    print("🎙️ FOLLOW-UP MCP SERVER")
    print("=" * 60)
    print(f"🚀 MCP Server: http://0.0.0.0:{PORT}/mcp")
    print("=" * 60)
    
    # Проверяем наличие credentials
    if not FOLLOWUP_API_KEY and not (FOLLOWUP_EMAIL and FOLLOWUP_PASSWORD):
        print("⚠️  ВНИМАНИЕ: Не настроены учётные данные Follow-Up API!")
        print("   Установите FOLLOWUP_API_KEY или FOLLOWUP_EMAIL + FOLLOWUP_PASSWORD")
    
    # Проверяем S3 credentials для RAG
    s3_endpoint = os.getenv("CLOUD_RAG_S3_ENDPOINT")
    s3_bucket = os.getenv("CLOUD_RAG_S3_BUCKET")
    if not s3_endpoint or not s3_bucket:
        print("⚠️  ВНИМАНИЕ: Не настроены S3 credentials для RAG!")
        print("   Установите CLOUD_RAG_S3_ENDPOINT, CLOUD_RAG_S3_BUCKET, CLOUD_RAG_S3_ACCESS_KEY, CLOUD_RAG_S3_SECRET_KEY")
    
    mcp.run(transport="streamable-http", host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
