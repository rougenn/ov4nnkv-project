"""Извлечь OAuth токены из pickle и вывести для .env"""
import pickle
from pathlib import Path

TOKEN_PATH = Path(__file__).parent / 'token.pickle'

if TOKEN_PATH.exists():
    with open(TOKEN_PATH, 'rb') as f:
        creds = pickle.load(f)
    
    print("Добавьте в .env:")
    print()
    print(f"GOOGLE_OAUTH_TOKEN={creds.token}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={creds.refresh_token}")
else:
    print("token.pickle не найден")
