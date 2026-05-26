"""
Настройка OAuth2 для Google Calendar MCP.
Запустите один раз — токен сохранится в .env.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

ENV_PATH = Path(__file__).parent.parent / '.env'
load_dotenv(ENV_PATH)

SCOPES = ['https://www.googleapis.com/auth/calendar']


def setup_oauth():
    client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("❌ Добавьте в .env:")
        print("GOOGLE_OAUTH_CLIENT_ID=...")
        print("GOOGLE_OAUTH_CLIENT_SECRET=...")
        return
    
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
        }
    }
    
    print("🔐 Откроется браузер для авторизации...")
    
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)
    
    # Сохраняем токен в .env
    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else []
    }
    
    token_json = json.dumps(token_data)
    env_content = ENV_PATH.read_text(encoding='utf-8')
    
    if 'GOOGLE_OAUTH_TOKEN=' in env_content:
        lines = [
            f"GOOGLE_OAUTH_TOKEN='{token_json}'" if line.startswith('GOOGLE_OAUTH_TOKEN=') else line
            for line in env_content.split('\n')
        ]
        env_content = '\n'.join(lines)
    else:
        env_content += f"\n# OAuth2 Token\nGOOGLE_OAUTH_TOKEN='{token_json}'\n"
    
    ENV_PATH.write_text(env_content, encoding='utf-8')
    
    print("✅ OAuth2 настроен! Токен сохранён в .env")
    print("   Теперь можно приглашать гостей и создавать Google Meet")


if __name__ == "__main__":
    setup_oauth()
