"""Скрипт с детальным логированием для отладки join_conference."""

import asyncio
import sys
from pathlib import Path
import httpx
import os

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


async def join_conference_debug(conference_url: str):
    """Тест с детальным выводом."""
    print("=" * 60)
    print("🧪 DEBUG: join_conference")
    print("=" * 60)
    
    email = os.getenv("FOLLOWUP_EMAIL")
    password = os.getenv("FOLLOWUP_PASSWORD")
    base_url = os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech")
    
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # 1. Логин
        print("1️⃣ Авторизация...")
        login_resp = await client.post(
            "/api/login",
            json={"email": email, "password": password},
            headers={"accept": "application/json", "content-type": "application/json", "x-lang": "ru"}
        )
        print(f"   Status: {login_resp.status_code}")
        
        if login_resp.status_code != 200:
            print(f"   ❌ Ошибка: {login_resp.text}")
            return
        
        login_data = login_resp.json()
        token = login_data["tokenPair"]["access"]["token"]
        print(f"   ✅ Токен получен")
        
        # 2. Подключение к созвону
        print()
        print("2️⃣ Подключение к созвону...")
        print(f"   URL: {conference_url}")
        
        # Определяем source (camelCase как требует API)
        import re
        url_lower = conference_url.lower()
        
        if "meet.google.com" in url_lower:
            source = "googleMeet"
            # Извлекаем externalId: abc-defg-hij
            match = re.search(r'meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})', url_lower)
            external_id = match.group(1) if match else conference_url.split('/')[-1]
        elif "zoom" in url_lower:
            source = "zoom"
            match = re.search(r'/j/(\d+)', conference_url)
            external_id = match.group(1) if match else conference_url.split('/')[-1]
        elif "telemost" in url_lower:
            source = "telemost"
            match = re.search(r'/j/(\d+)', conference_url)
            external_id = match.group(1) if match else conference_url.split('/')[-1]
        elif "teams" in url_lower:
            source = "msTeams"
            external_id = conference_url.split('/')[-1]
        else:
            source = "googleMeet"
            external_id = conference_url.split('/')[-1]
        
        print(f"   Source: {source}")
        print(f"   External ID: {external_id}")
        
        payload = {
            "theme": "Тестовый созвон",
            "link": conference_url,
            "source": source,
            "externalId": external_id,
            "selectedProcessing": [],
        }
        print(f"   Payload: {payload}")
        
        join_resp = await client.post(
            "/api/conference/link",
            json=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Bearer {token}",
                "x-lang": "ru"
            }
        )
        
        print()
        print(f"   Status: {join_resp.status_code}")
        print(f"   Response: {join_resp.text}")
        
        if join_resp.status_code in (200, 201):
            print()
            print("✅ УСПЕХ! Бот подключается к созвону.")
            data = join_resp.json()
            print(f"   Conference ID: {data.get('id') or data.get('conferenceId')}")
        else:
            print()
            print("❌ Ошибка от API")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://meet.google.com/frh-vtbt-jou"
    asyncio.run(join_conference_debug(url))
