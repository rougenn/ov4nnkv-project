"""Скрипт для ручного тестирования join_conference."""

import asyncio
import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from followup_client import FollowUpClient
import os


async def join_conference(conference_url: str):
    """Подключение к созвону."""
    print("=" * 60)
    print("🧪 ТЕСТ: join_conference")
    print("=" * 60)
    print(f"📎 URL: {conference_url}")
    print()
    
    # Получаем credentials из .env
    email = os.getenv("FOLLOWUP_EMAIL")
    password = os.getenv("FOLLOWUP_PASSWORD")
    api_key = os.getenv("FOLLOWUP_API_KEY")
    base_url = os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech")
    
    print(f"🔑 Авторизация: {'API-ключ' if api_key else f'email={email}'}")
    print(f"🌐 API URL: {base_url}")
    print()
    
    try:
        async with FollowUpClient(
            email=email,
            password=password,
            api_key=api_key,
            base_url=base_url
        ) as client:
            print("⏳ Подключаем бота к созвону...")
            result = await client.join_conference(
                conference_url=conference_url,
                theme="Тестовый созвон"
            )
            
            print()
            print("✅ УСПЕХ!")
            print(f"📋 Результат: {result}")
            print()
            
            conference_id = result.get("id") or result.get("conferenceId") or result.get("conference_id")
            if conference_id:
                print(f"🆔 Conference ID: {conference_id}")
            
            return result
            
    except Exception as e:
        print()
        print(f"❌ ОШИБКА: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python join_conference.py <URL_созвона>")
        print()
        print("Примеры:")
        print("  python join_conference.py https://meet.google.com/abc-defg-hij")
        print("  python join_conference.py https://telemost.yandex.ru/j/123456")
        sys.exit(1)
    
    url = sys.argv[1]
    asyncio.run(join_conference(url))
