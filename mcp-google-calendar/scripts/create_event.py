"""
Создание события в Google Calendar через Service Account.
Без логина и редиректов!
"""

import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID')


def get_credentials():
    """Создать credentials из переменных окружения."""
    info = {
        "type": os.getenv('GOOGLE_SERVICE_ACCOUNT_TYPE', 'service_account'),
        "project_id": os.getenv('GOOGLE_PROJECT_ID'),
        "private_key_id": os.getenv('GOOGLE_PRIVATE_KEY_ID'),
        "private_key": os.getenv('GOOGLE_PRIVATE_KEY', '').replace('\\n', '\n'),
        "client_email": os.getenv('GOOGLE_CLIENT_EMAIL'),
        "client_id": os.getenv('GOOGLE_CLIENT_ID'),
        "auth_uri": os.getenv('GOOGLE_AUTH_URI'),
        "token_uri": os.getenv('GOOGLE_TOKEN_URI'),
    }
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def create_event(
    title: str, 
    start_time: str, 
    end_time: str, 
    description: str = "",
    attendees: list[str] = None,
    add_meet: bool = False
):
    """
    Создание события через Service Account.
    
    Args:
        title: Название события
        start_time: Время начала (RFC3339, например '2025-12-11T14:00:00')
        end_time: Время окончания
        description: Описание события
        attendees: Список email участников
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
    
    # Добавляем участников
    if attendees:
        event['attendees'] = [
            {'email': email, 'responseStatus': 'needsAction'} 
            for email in attendees
        ]
    
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
        # Service Account без Domain-Wide Delegation не может отправлять приглашения
        # sendUpdates='none' — участники добавляются, но без email-уведомлений
        created_event = service.events().insert(
            calendarId=CALENDAR_ID, 
            body=event,
            conferenceDataVersion=1 if add_meet else 0,
            sendUpdates='none'
        ).execute()
        
        print("=" * 60)
        print("Event created!")
        print("=" * 60)
        print(f"ID: {created_event.get('id')}")
        print(f"Title: {created_event.get('summary')}")
        print(f"Link: {created_event.get('htmlLink')}")
        
        # Выводим ссылку на Google Meet если есть
        conference_data = created_event.get('conferenceData')
        if conference_data:
            entry_points = conference_data.get('entryPoints', [])
            for ep in entry_points:
                if ep.get('entryPointType') == 'video':
                    print(f"Google Meet: {ep.get('uri')}")
                    break
        
        # Выводим участников
        event_attendees = created_event.get('attendees', [])
        if event_attendees:
            print(f"Attendees: {', '.join(a.get('email') for a in event_attendees)}")
        
        return created_event
        
    except Exception as e:
        print("=" * 60)
        print("ERROR!")
        print("=" * 60)
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Create Google Calendar event')
    parser.add_argument('title', help='Event title')
    parser.add_argument('start_time', help='Start time (RFC3339, e.g. 2025-12-11T14:00:00)')
    parser.add_argument('end_time', help='End time')
    parser.add_argument('--description', '-d', default='', help='Event description')
    parser.add_argument('--attendees', '-a', nargs='*', help='Attendee emails')
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
