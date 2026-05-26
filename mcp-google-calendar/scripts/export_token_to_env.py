"""Экспорт OAuth токена из pickle в .env файл."""

import pickle
import json
from pathlib import Path

TOKEN_PATH = Path(__file__).parent / 'token.pickle'
ENV_PATH = Path(__file__).parent.parent / '.env'

def export_token():
    if not TOKEN_PATH.exists():
        print("❌ token.pickle не найден")
        return
    
    with open(TOKEN_PATH, 'rb') as f:
        creds = pickle.load(f)
    
    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else []
    }
    
    token_json = json.dumps(token_data)
    
    # Читаем текущий .env
    env_content = ENV_PATH.read_text(encoding='utf-8')
    
    # Добавляем или обновляем GOOGLE_OAUTH_TOKEN
    if 'GOOGLE_OAUTH_TOKEN=' in env_content:
        lines = env_content.split('\n')
        new_lines = []
        for line in lines:
            if line.startswith('GOOGLE_OAUTH_TOKEN='):
                new_lines.append(f"GOOGLE_OAUTH_TOKEN='{token_json}'")
            else:
                new_lines.append(line)
        env_content = '\n'.join(new_lines)
    else:
        env_content += f"\n# OAuth2 Token (автоматически сгенерирован)\nGOOGLE_OAUTH_TOKEN='{token_json}'\n"
    
    ENV_PATH.write_text(env_content, encoding='utf-8')
    print("✅ Токен экспортирован в .env как GOOGLE_OAUTH_TOKEN")
    print(f"   refresh_token: {creds.refresh_token[:20]}...")

if __name__ == "__main__":
    export_token()
