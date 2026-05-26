"""
Создание события в Google Calendar через OAuth2.
Позволяет приглашать гостей (attendees) без Google Workspace.
Требует одноразовой авторизации через браузер.
"""

import os
import pickle
from pathlib import Path
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
TOKEN_PATH = Path(__file__).parent / 'token.pickle'
CREDENTIALS_PATH = Path(__file__).parent / 'credentials.json'


def get_credentials():
    """Получить OAuth2 credentials с кэшированием токена."""
    creds = None
    
    # Загружаем сохранённый токен
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    
    # Если токен невалидный — обновляем или запрашиваем новый
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Файл {CREDENTIALS_PATH} не найден!\n"
                    "Скачай его из Google Cloud Console:\n"
                    "1. APIs & Services → Credentials\n"
                    "2. Create Credentials → OAuth client ID → Desktop app\n"
                    "3. Download JSON → сохрани как credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Сохраняем токен
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
    
    return creds


def create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    attendees: list[str] = None,
    add_meet: bool = False
):
    """
    Создание события через OAuth2 — поддерживает приглашение гостей.
    
    Args:
        title: Название события
        start_time: Время начала (RFC3339, например '2025-12-11T14:00:00')
        end_time: Время окончания
        description: Описание события
        attendees: Список email участников (им придут приглашения!)
        add_meet: Добавить Google Meet видеоконференцию
    """
    
    credentials = get_credentials()
    service = build('calendar', 'v3', credentials=credentials)
    
    event = {
        'summary': title,
        'description': description,
        'start': {
            'dateTime': start_time,
            'timeZone': 'Europe/Moscow',
        },
        'end': {
            'dateTime': end_time,
            'timeZone': 'Europe/Moscow',
        },
    }
    
    # Добавляем участников — им придут email-приглашения!
    if attendees:
        event['attendees'] = [{'email': email} for email in attendees]
    
    # Добавляем Google Meet
    if add_meet:
        import uuid
        event['conferenceData'] = {
            'createRequest': {
                'requestId': str(uuid.uuid4()),
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        }
    
    try:
        created_event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event,
            conferenceDataVersion=1 if add_meet else 0,
            sendUpdates='all' if attendees else 'none'
        ).execute()
        
        print("=" * 60)
        print("Event created!")
        print("=" * 60)
        print(f"ID: {created_event.get('id')}")
        print(f"Title: {created_event.get('summary')}")
        print(f"Link: {created_event.get('htmlLink')}")
        
        # Google Meet ссылка
        conference_data = created_event.get('conferenceData')
        if conference_data:
            for ep in conference_data.get('entryPoints', []):
                if ep.get('entryPointType') == 'video':
                    print(f"Google Meet: {ep.get('uri')}")
                    break
        
        # Участники
        if created_event.get('attendees'):
            emails = [a.get('email') for a in created_event['attendees']]
            print(f"Attendees: {', '.join(emails)}")
        
        return created_event
        
    except Exception as e:
        print(f"ERROR: {e}")
        return None


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Create Google Calendar event with OAuth2')
    parser.add_argument('title', help='Event title')
    parser.add_argument('start_time', help='Start time (e.g. 2025-12-11T14:00:00)')
    parser.add_argument('end_time', help='End time')
    parser.add_argument('--description', '-d', default='', help='Event description')
    parser.add_argument('--attendees', '-a', nargs='*', help='Attendee emails (will receive invites)')
    parser.add_argument('--meet', '-m', action='store_true', help='Add Google Meet')
    
    args = parser.parse_args()
    
    create_event(
        title=args.title,
        start_time=args.start_time,
        end_time=args.end_time,
        description=args.description,
        attendees=args.attendees,
        add_meet=args.meet
    )
