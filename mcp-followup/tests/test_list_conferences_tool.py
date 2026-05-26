"""Тестовый скрипт для проверки tool list_conferences."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from followup_client import FollowUpClient, FollowUpAPIError


async def test_list_conferences():
    """Тестируем list_conferences через клиент."""
    print("🔍 Тестируем list_conferences tool...\n")

    async with FollowUpClient(
        email=os.getenv("FOLLOWUP_EMAIL"),
        password=os.getenv("FOLLOWUP_PASSWORD"),
        api_key=os.getenv("FOLLOWUP_API_KEY"),
        base_url=os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech"),
    ) as client:
        try:
            # Тест 1: Получение списка с дефолтными параметрами
            print("📋 Тест 1: Получение списка (limit=20, offset=0)")
            result = await client.list_conferences(limit=20, offset=0)
            print(f"   ✅ Успех! Всего созвонов: {result['total']}")
            print(f"   📊 Получено записей: {len(result['conferences'])}")
            
            if result['conferences']:
                print("\n   Первые созвоны:")
                for i, conf in enumerate(result['conferences'][:3]):
                    print(f"   {i+1}. ID: {conf.get('id', 'N/A')}")
                    print(f"      Тема: {conf.get('theme', conf.get('title', 'Без названия'))}")
                    print(f"      Статус: {conf.get('status', 'unknown')}")
            else:
                print("   📭 Список созвонов пуст")
            
            # Тест 2: Пагинация
            print("\n📋 Тест 2: Пагинация (limit=5, offset=0)")
            result2 = await client.list_conferences(limit=5, offset=0)
            print(f"   ✅ Успех! Получено: {len(result2['conferences'])} записей")
            
            # Тест 3: Пустой результат с большим offset
            print("\n📋 Тест 3: Большой offset (limit=10, offset=1000)")
            result3 = await client.list_conferences(limit=10, offset=1000)
            print(f"   ✅ Успех! Получено: {len(result3['conferences'])} записей (ожидаем 0)")
            
            print("\n" + "=" * 50)
            print("✅ Все тесты list_conferences прошли успешно!")
            print("=" * 50)
            
        except FollowUpAPIError as e:
            print(f"❌ Ошибка API: {e.message}")
            if e.status_code:
                print(f"   Код: {e.status_code}")
            if e.details:
                print(f"   Детали: {e.details}")


if __name__ == "__main__":
    asyncio.run(test_list_conferences())
