"""Скрипт для ручного тестирования FollowUpClient.

Использование:
    uv run python scripts/test_client.py

Требуется файл .env с переменными (один из вариантов):
    Вариант 1 (email/password):
        FOLLOWUP_EMAIL=your_email@example.com
        FOLLOWUP_PASSWORD=your_password
    
    Вариант 2 (API-ключ):
        FOLLOWUP_API_KEY=your_jwt_token
"""

import asyncio
import logging
import os
import sys

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
from followup_client import (
    FollowUpClient,
    FollowUpAPIError,
    AuthenticationError,
    NetworkError,
)

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def test_successful_login():
    """Тест успешной авторизации с реальными credentials."""
    load_dotenv()
    
    email = os.getenv("FOLLOWUP_EMAIL")
    password = os.getenv("FOLLOWUP_PASSWORD")
    api_key = os.getenv("FOLLOWUP_API_KEY")
    base_url = os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech")
    
    print(f"\n{'='*60}")
    print("🧪 ТЕСТ 1: Успешная авторизация")
    print(f"{'='*60}")
    print(f"🌐 API URL: {base_url}")
    
    # Определяем способ авторизации
    if api_key:
        print(f"🔑 Используем API-ключ")
        try:
            async with FollowUpClient(api_key=api_key, base_url=base_url) as client:
                print("\n✅ Клиент создан с API-ключом!")
                print(f"   Token установлен: {'Да' if client._access_token else 'Нет'}")
                return True
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            return False
    elif email and password:
        print(f"📧 Email: {email}")
        try:
            async with FollowUpClient(email=email, password=password, base_url=base_url) as client:
                result = await client.login()
                
                print("\n✅ Авторизация успешна!")
                print(f"   User ID: {result.get('user', {}).get('id', 'N/A')}")
                print(f"   Email: {result.get('user', {}).get('email', 'N/A')}")
                print(f"   Token получен: {'Да' if client._access_token else 'Нет'}")
                return True
                
        except AuthenticationError as e:
            print(f"\n❌ Ошибка авторизации: {e.message}")
            print(f"   Status code: {e.status_code}")
            return False
        except NetworkError as e:
            print(f"\n❌ Сетевая ошибка: {e.message}")
            return False
        except Exception as e:
            print(f"\n❌ Неожиданная ошибка: {e}")
            return False
    else:
        print("❌ Ошибка: Не заданы credentials в .env")
        print("   Укажите FOLLOWUP_EMAIL + FOLLOWUP_PASSWORD или FOLLOWUP_API_KEY")
        return False


async def test_invalid_credentials():
    """Тест авторизации с неверными credentials."""
    print(f"\n{'='*60}")
    print("🧪 ТЕСТ 2: Неверные credentials")
    print(f"{'='*60}")
    
    try:
        async with FollowUpClient(
            email="invalid@test.com",
            password="wrongpassword",
            base_url="https://api.follow-up.tech"
        ) as client:
            await client.login()
            print("❌ Ожидалась ошибка, но авторизация прошла!")
            return False
            
    except AuthenticationError as e:
        print(f"✅ Корректно обработана ошибка авторизации:")
        print(f"   Сообщение: {e.message}")
        print(f"   Status code: {e.status_code}")
        return True
    except FollowUpAPIError as e:
        # API может вернуть разные коды для неверных credentials
        print(f"✅ Обработана ошибка API (неверные credentials):")
        print(f"   Сообщение: {e.message}")
        print(f"   Status code: {e.status_code}")
        return True
    except Exception as e:
        print(f"❌ Неожиданный тип ошибки: {type(e).__name__}: {e}")
        return False


async def test_invalid_url():
    """Тест с недоступным сервером."""
    print(f"\n{'='*60}")
    print("🧪 ТЕСТ 3: Недоступный сервер")
    print(f"{'='*60}")
    
    try:
        async with FollowUpClient(
            email="test@test.com",
            password="test",
            base_url="https://invalid-server-12345.example.com"
        ) as client:
            await client.login()
            print("❌ Ожидалась ошибка, но запрос прошёл!")
            return False
            
    except NetworkError as e:
        print(f"✅ Корректно обработана сетевая ошибка:")
        print(f"   Сообщение: {e.message}")
        return True
    except Exception as e:
        print(f"❌ Неожиданный тип ошибки: {type(e).__name__}: {e}")
        return False


async def main():
    """Запуск всех тестов."""
    print("\n" + "="*60)
    print("🚀 РУЧНОЕ ТЕСТИРОВАНИЕ FollowUpClient")
    print("="*60)
    
    results = []
    
    # Тест 1: Успешная авторизация (требует реальные credentials)
    results.append(("Успешная авторизация", await test_successful_login()))
    
    # Тест 2: Неверные credentials
    results.append(("Неверные credentials", await test_invalid_credentials()))
    
    # Тест 3: Недоступный сервер
    results.append(("Недоступный сервер", await test_invalid_url()))
    
    # Итоги
    print(f"\n{'='*60}")
    print("📊 ИТОГИ ТЕСТИРОВАНИЯ")
    print(f"{'='*60}")
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status}: {name}")
        if result:
            passed += 1
    
    print(f"\n   Всего: {passed}/{len(results)} тестов прошло")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
