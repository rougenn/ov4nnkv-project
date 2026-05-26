import asyncio
import os
import json
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.followup_client import FollowUpClient


async def test_join():
    """Тест подключения к созвону."""
    client = FollowUpClient(
        email=os.getenv("FOLLOWUP_EMAIL"),
        password=os.getenv("FOLLOWUP_PASSWORD"),
        api_key=os.getenv("FOLLOWUP_API_KEY"),
        base_url=os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech")
    )
    
    try:
        result = await client.join_conference(
            conference_url="https://telemost.yandex.ru/j/46760175506615",
            theme="Тестовый созвон"
        )
        
        print("=" * 60)
        print("Результат join_conference:")
        print("=" * 60)
        print(f"Тип: {type(result)}")
        print(f"Содержимое:\n{json.dumps(result, indent=2, ensure_ascii=False)}")
        print("=" * 60)
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_join())
