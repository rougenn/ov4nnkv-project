"""Скрипт для получения списка созвонов из Follow-Up."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from followup_client import FollowUpClient, FollowUpAPIError


async def list_conferences():
    """Получить список созвонов."""
    print("🔍 Получаем список созвонов из Follow-Up...\n")

    async with FollowUpClient(
        email=os.getenv("FOLLOWUP_EMAIL"),
        password=os.getenv("FOLLOWUP_PASSWORD"),
        api_key=os.getenv("FOLLOWUP_API_KEY"),
        base_url=os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech"),
    ) as client:
        try:
            # Получаем список конференций через правильный метод
            result = await client.list_conferences(limit=10)

            conferences = result.get("conferences", [])

            if not conferences:
                print("📭 Нет записанных созвонов")
                print("\nДля тестирования get_transcription нужно:")
                print("1. Создать созвон в Google Meet / Zoom / etc")
                print("2. Подключить бота через join_conference")
                print("3. Провести короткий созвон (1-2 мин)")
                print("4. Дождаться обработки транскрипции")
                return

            print(f"📋 Найдено созвонов: {len(conferences)}\n")
            print("=" * 80)

            for conf in conferences:
                conf_id = conf.get("id", "N/A")
                theme = conf.get("theme", conf.get("title", "Без названия"))
                status = conf.get("status", "unknown")
                # API может возвращать разные поля для даты
                date = conf.get("startedAt") or conf.get("createdAt") or conf.get("date") or "N/A"
                duration = conf.get
                print(f"🆔 ID: {conf_id}")
                print(f"   📋 Название: {theme}")
                print(f"   📅 Дата: {date}")
                print(f"   ⏱️ Длительность: {duration // 60} мин")
                print(f"   📊 Статус: {status}")
                print("-" * 80)

            print("\n💡 Скопируй ID созвона со статусом 'completed' для тестирования get_transcription")

        except FollowUpAPIError as e:
            print(f"❌ Ошибка API: {e.message}")
            if e.status_code:
                print(f"   Код: {e.status_code}")


if __name__ == "__main__":
    asyncio.run(list_conferences())
