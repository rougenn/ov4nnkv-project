"""MCP сервер для работы с Google Calendar через OAuth2.

Предоставляет tools для:
- Создания событий с гостями и Google Meet
- Получения списка встреч за день или на 7 дней вперёд
- Получения текущего времени по Москве
"""

import logging
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Annotated

from dotenv import load_dotenv, find_dotenv
from fastmcp import FastMCP
from pydantic import Field
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pytz

# Load environment variables
load_dotenv(find_dotenv())

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mcp-google-calendar")

# Configuration
PORT = int(os.getenv("PORT", "8001"))
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
SCOPES = ['https://www.googleapis.com/auth/calendar']
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Initialize MCP server
mcp = FastMCP(
    name="mcp-google-calendar",
    instructions="MCP сервер для работы с Google Calendar - создание событий и просмотр расписания"
)


def _get_oauth_credentials() -> Credentials:
    """Получить OAuth2 credentials из переменных окружения.
    
    Поддерживает два формата:
    1. Отдельные переменные: GOOGLE_OAUTH_TOKEN, GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    2. JSON в GOOGLE_OAUTH_TOKEN: {"token": "...", "refresh_token": "...", ...}
    """
    token_value = os.getenv('GOOGLE_OAUTH_TOKEN')
    if not token_value:
        raise Exception("GOOGLE_OAUTH_TOKEN не найден")
    
    token_value = token_value.strip()
    
    # Пробуем распарсить как JSON
    if token_value.startswith('{'):
        try:
            token_data = json.loads(token_value)
            creds = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes', SCOPES)
            )
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise
    else:
        # Отдельные переменные окружения (поддержка разных имён)
        refresh_token = os.getenv('GOOGLE_OAUTH_REFRESH_TOKEN') or os.getenv('GOOGLE_REFRESH_TOKEN')
        client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID') or os.getenv('GOOGLE_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET') or os.getenv('GOOGLE_CLIENT_SECRET')
        
        if not all([refresh_token, client_id, client_secret]):
            raise Exception(
                "Для работы нужны переменные: GOOGLE_OAUTH_TOKEN, "
                "GOOGLE_OAUTH_REFRESH_TOKEN, GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET"
            )
        
        # Убираем кавычки если есть
        client_id = client_id.strip().strip("'\"")
        client_secret = client_secret.strip().strip("'\"")
        refresh_token = refresh_token.strip().strip("'\"")
        token_value = token_value.strip().strip("'\"")
        
        logger.info(f"Using OAuth client_id: {client_id[:20]}...")
        
        creds = Credentials(
            token=token_value,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES
        )
    
    # Обновляем токен если истёк
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        logger.info("OAuth токен обновлён")
    
    return creds


def _get_calendar_service():
    """Создать сервис Google Calendar через OAuth2."""
    creds = _get_oauth_credentials()
    return build('calendar', 'v3', credentials=creds)


def _parse_datetime(dt_str: str) -> str:
    """Парсит строку времени в ISO формат."""
    dt_str = dt_str.strip()
    if 'T' in dt_str:
        return dt_str.split('+')[0].split('Z')[0]
    for fmt in ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"]:
        try:
            return datetime.strptime(dt_str, fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return dt_str


@mcp.tool()
def get_current_time_moscow() -> dict:
    """Получить текущее время по Москве."""
    try:
        now = datetime.now(MOSCOW_TZ)
        return {
            "success": True,
            "timezone": "Europe/Moscow",
            "datetime_iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "formatted": now.strftime("%d.%m.%Y %H:%M"),
        }
    except Exception as e:
        return {"success": False, "error": {"code": "INTERNAL_ERROR", "message": str(e)}}


@mcp.tool()
def create_calendar_event(
    title: Annotated[str, Field(description="Название события/встречи")],
    start_time: Annotated[str, Field(
        description="Время начала в формате ISO 8601 (2025-12-11T14:00:00) или YYYY-MM-DD HH:MM"
    )],
    end_time: Annotated[str, Field(
        description="Время окончания в формате ISO 8601 или YYYY-MM-DD HH:MM"
    )],
    description: Annotated[str, Field(default="", description="Описание события")] = "",
    attendees: Annotated[str, Field(
        default="",
        description="Email участников через запятую (user1@gmail.com, user2@gmail.com). Им придут приглашения."
    )] = "",
    add_google_meet: Annotated[bool, Field(
        default=False,
        description="Добавить Google Meet видеоконференцию"
    )] = False
) -> dict:
    """Создать событие в Google Calendar с участниками и Google Meet."""
    if not title or not title.strip():
        return {"success": False, "error": {"code": "INVALID_PARAMETER", "message": "Название не может быть пустым"}}
    
    if not start_time or not end_time:
        return {"success": False, "error": {"code": "INVALID_PARAMETER", "message": "Время начала и окончания обязательны"}}
    
    try:
        service = _get_calendar_service()
        
        start_iso = _parse_datetime(start_time)
        end_iso = _parse_datetime(end_time)
        
        event = {
            'summary': title.strip(),
            'description': description,
            'start': {'dateTime': start_iso, 'timeZone': 'Europe/Moscow'},
            'end': {'dateTime': end_iso, 'timeZone': 'Europe/Moscow'},
        }
        
        # Участники
        attendee_list = []
        if attendees and attendees.strip():
            emails = [e.strip() for e in attendees.split(',') if e.strip()]
            event['attendees'] = [{'email': email} for email in emails]
            attendee_list = emails
        
        # Google Meet
        conference_data_version = 0
        if add_google_meet:
            event['conferenceData'] = {
                'createRequest': {
                    'requestId': str(uuid.uuid4()),
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }
            conference_data_version = 1
        
        created_event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event,
            conferenceDataVersion=conference_data_version,
            sendUpdates='all' if attendee_list else 'none'
        ).execute()
        
        logger.info(f"Создано событие: {created_event.get('id')}")
        
        result = {
            "success": True,
            "event_id": created_event.get('id'),
            "title": created_event.get('summary'),
            "start_time": start_iso,
            "end_time": end_iso,
            "link": created_event.get('htmlLink'),
            "message": f"Событие '{title}' создано"
        }
        
        # Google Meet ссылка
        conf_data = created_event.get('conferenceData')
        if conf_data:
            for ep in conf_data.get('entryPoints', []):
                if ep.get('entryPointType') == 'video':
                    result['google_meet_link'] = ep.get('uri')
                    break
        
        if attendee_list:
            result['attendees'] = attendee_list
        
        return result
        
    except Exception as e:
        logger.exception(f"Ошибка создания события: {e}")
        return {"success": False, "error": {"code": "CALENDAR_ERROR", "message": str(e)}}


@mcp.tool()
def get_events_for_date(
    date: Annotated[str, Field(
        default="",
        description="Дата в формате YYYY-MM-DD. Если не указана — сегодня."
    )] = ""
) -> dict:
    """Получить события за конкретный день."""
    try:
        if date and date.strip():
            for fmt in ["%Y-%m-%d", "%d.%m.%Y"]:
                try:
                    target_date = datetime.strptime(date.strip(), fmt)
                    break
                except ValueError:
                    continue
            else:
                return {"success": False, "error": {"code": "INVALID_DATE", "message": "Формат: YYYY-MM-DD"}}
        else:
            target_date = datetime.now(MOSCOW_TZ).replace(tzinfo=None)
        
        start_of_day = MOSCOW_TZ.localize(datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0))
        end_of_day = MOSCOW_TZ.localize(datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59))
        
        service = _get_calendar_service()
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = []
        for event in events_result.get('items', []):
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            events.append({
                "id": event.get('id'),
                "title": event.get('summary', 'Без названия'),
                "start_time": start.split('T')[1][:5] if 'T' in str(start) else "Весь день",
                "end_time": end.split('T')[1][:5] if 'T' in str(end) else "",
                "description": event.get('description', ''),
            })
        
        return {
            "success": True,
            "date": target_date.strftime("%Y-%m-%d"),
            "total": len(events),
            "events": events,
        }
        
    except Exception as e:
        logger.exception(f"Ошибка получения событий: {e}")
        return {"success": False, "error": {"code": "CALENDAR_ERROR", "message": str(e)}}


@mcp.tool()
def get_upcoming_events(
    days_ahead: Annotated[int, Field(default=7, ge=1, le=30, description="Дней вперёд (1-30)")] = 7
) -> dict:
    """Получить предстоящие события на несколько дней вперёд."""
    try:
        now = datetime.now(MOSCOW_TZ)
        end_date = now + timedelta(days=days_ahead)
        
        service = _get_calendar_service()
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=now.isoformat(),
            timeMax=end_date.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events_by_day = {}
        for event in events_result.get('items', []):
            start = event['start'].get('dateTime', event['start'].get('date'))
            date_str = start.split('T')[0] if 'T' in str(start) else start
            
            if date_str not in events_by_day:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                events_by_day[date_str] = {
                    "date": date_str,
                    "day_of_week": dt.strftime("%A"),
                    "events": []
                }
            
            end = event['end'].get('dateTime', event['end'].get('date'))
            events_by_day[date_str]["events"].append({
                "title": event.get('summary', 'Без названия'),
                "start_time": start.split('T')[1][:5] if 'T' in str(start) else "Весь день",
                "end_time": end.split('T')[1][:5] if 'T' in str(end) else "",
            })
        
        return {
            "success": True,
            "days_ahead": days_ahead,
            "total_events": len(events_result.get('items', [])),
            "days": sorted(events_by_day.values(), key=lambda x: x["date"]),
        }
        
    except Exception as e:
        logger.exception(f"Ошибка получения событий: {e}")
        return {"success": False, "error": {"code": "CALENDAR_ERROR", "message": str(e)}}


def main():
    """Запуск MCP сервера."""
    print("=" * 60)
    print("📅 GOOGLE CALENDAR MCP SERVER")
    print("=" * 60)
    print(f"🚀 MCP Server: http://0.0.0.0:{PORT}/mcp")
    
    if os.getenv('GOOGLE_OAUTH_TOKEN'):
        print("✅ OAuth2 токен найден")
    else:
        print("⚠️  OAuth2 не настроен!")
    
    print(f"📆 Calendar ID: {CALENDAR_ID[:30]}..." if len(CALENDAR_ID) > 30 else f"📆 Calendar ID: {CALENDAR_ID}")
    print("=" * 60)
    
    mcp.run(transport="streamable-http", host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
