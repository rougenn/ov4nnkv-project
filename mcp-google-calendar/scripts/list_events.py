"""
Получение списка событий из Google Calendar через Service Account.
"""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
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


def list_events(days_ahead: int = 7):
    """Получить события на указанное количество дней вперёд."""
    
    credentials = get_credentials()
    service = build('calendar', 'v3', credentials=credentials)
    
    now = datetime.utcnow()
    time_min = now.isoformat() + 'Z'
    time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'
    
    try:
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        print("=" * 60)
        print(f"Events for next {days_ahead} days")
        print("=" * 60)
        
        if not events:
            print("No events found.")
            return []
        
        events_by_day = {}
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            date_str = start.split('T')[0] if 'T' in start else start
            
            if date_str not in events_by_day:
                events_by_day[date_str] = []
            events_by_day[date_str].append(event)
        
        for date_str in sorted(events_by_day.keys()):
            print(f"\n{date_str}")
            print("-" * 40)
            for event in events_by_day[date_str]:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                summary = event.get('summary', 'No title')
                
                if 'T' in start:
                    start_time = start.split('T')[1][:5]
                    end_time = end.split('T')[1][:5]
                    print(f"  {start_time}-{end_time}  {summary}")
                else:
                    print(f"  All day       {summary}")
                
                desc = event.get('description', '')
                if desc and ('meet' in desc.lower() or 'zoom' in desc.lower() or 'telemost' in desc.lower()):
                    print(f"               Link: {desc[:60]}...")
        
        print()
        return events
        
    except Exception as e:
        print(f"Error: {e}")
        return []


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    list_events(days)
