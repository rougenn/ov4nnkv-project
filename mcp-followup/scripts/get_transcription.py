"""Скрипт для ручного тестирования get_transcription."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from followup_client import FollowUpClient, FollowUpAPIError


async def get_transcription(conference_id: str):
    """Получение транскрипции."""
    print(f"\n🔍 Получаем транскрипцию для конференции: {conference_id}")

    async with FollowUpClient(
        email=os.getenv("FOLLOWUP_EMAIL"),
        password=os.getenv("FOLLOWUP_PASSWORD"),
        api_key=os.getenv("FOLLOWUP_API_KEY"),
        base_url=os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech"),
    ) as client:
        try:
            result = await client.get_transcription(conference_id)

            print("\n✅ Транскрипция получена успешно!")
            print("=" * 60)

            conf_info = result.get("conference_info", {})
            transcription = result.get("transcription", {})

            print(f"📋 Название: {conf_info.get('theme', 'Без названия')}")
            print(f"📅 Дата: {conf_info.get('startedAt', 'N/A')}")
            print(f"⏱️ Длительность: {conf_info.get('duration', 'N/A')} сек")
            print(f"📊 Статус: {conf_info.get('status', 'N/A')}")

            participants = conf_info.get("participants", [])
            if participants:
                names = [p.get("name", p.get("email", "Unknown")) for p in participants]
                print(f"👥 Участники: {', '.join(names)}")

            print("\n📝 Транскрипция:")
            print("-" * 60)

            if isinstance(transcription, dict):
                text = transcription.get("text", transcription.get("content", ""))
                if text:
                    # Показываем первые 500 символов
                    preview = text[:500] + "..." if len(text) > 500 else text
                    print(preview)
                else:
                    print(f"Данные транскрипции: {transcription}")
            else:
                print(transcription)

        except FollowUpAPIError as e:
            print(f"\n❌ Ошибка API: {e.message}")
            print(f"   Код: {e.status_code}")
            if e.details:
                print(f"   Детали: {e.details}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python get_transcription.py <conference_id>")
        sys.exit(1)
    
    conf_id = sys.argv[1]
    asyncio.run(get_transcription(conf_id))
