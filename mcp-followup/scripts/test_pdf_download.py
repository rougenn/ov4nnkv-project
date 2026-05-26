"""Тестовый скрипт для скачивания PDF отчёта из Follow-Up."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import httpx

async def test_pdf_download():
    """Тестируем скачивание PDF через lk.follow-up.tech с next-auth."""
    
    email = os.getenv("FOLLOWUP_EMAIL")
    password = os.getenv("FOLLOWUP_PASSWORD")
    api_base_url = os.getenv("FOLLOWUP_API_URL", "https://api.follow-up.tech")
    lk_base_url = "https://lk.follow-up.tech"
    
    print(f"Email: {email}")
    
    # Используем клиент с cookies
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        
        # 1. Получаем CSRF token от next-auth
        print("\n1. Получаем CSRF token...")
        csrf_resp = await client.get(f"{lk_base_url}/api/auth/csrf")
        print(f"   Status: {csrf_resp.status_code}")
        
        if csrf_resp.status_code == 200:
            csrf_data = csrf_resp.json()
            csrf_token = csrf_data.get("csrfToken")
            print(f"   CSRF Token: {csrf_token[:20]}...")
        else:
            print(f"   Error: {csrf_resp.text}")
            return
        
        # 2. Авторизуемся через next-auth credentials
        print("\n2. Авторизация через next-auth...")
        
        login_resp = await client.post(
            f"{lk_base_url}/api/auth/callback/credentials",
            data={
                "email": email,
                "password": password,
                "csrfToken": csrf_token,
                "callbackUrl": lk_base_url,
                "json": "true"
            },
            headers={"content-type": "application/x-www-form-urlencoded"}
        )
        
        print(f"   Status: {login_resp.status_code}")
        print(f"   Cookies: {list(client.cookies.keys())}")
        
        # 3. Проверяем сессию
        print("\n3. Проверяем сессию...")
        session_resp = await client.get(f"{lk_base_url}/api/auth/session")
        print(f"   Status: {session_resp.status_code}")
        session_data = session_resp.json()
        print(f"   Session: {session_data}")
        
        if not session_data or not session_data.get("user"):
            print("   ❌ Не авторизован!")
            return
        
        print(f"   ✅ Авторизован как: {session_data.get('user', {}).get('email')}")
        
        # 4. Получаем список конференций через API
        print("\n4. Получаем список конференций...")
        
        # Авторизуемся в API для получения списка
        api_login = await client.post(
            f"{api_base_url}/api/login",
            json={"email": email, "password": password}
        )
        token = api_login.json()["tokenPair"]["access"]["token"]
        
        list_resp = await client.post(
            f"{api_base_url}/api/conference/listing/history",
            headers={"authorization": f"Bearer {token}"},
            json={"paging": {"size": 5, "current": 1}, "sort": {"by": "date", "order": "desc"}}
        )
        
        conferences = list_resp.json().get("page", [])
        if not conferences:
            print("   Нет конференций!")
            return
            
        conf_id = conferences[0]["id"]
        theme = conferences[0].get("theme", "Unknown")
        print(f"   Конференция: {conf_id} ({theme})")
        
        # 5. Скачиваем PDF
        print("\n5. Скачиваем PDF...")
        
        pdf_url = f"{lk_base_url}/conference/{conf_id}/report/transcription"
        print(f"   URL: {pdf_url}?format=pdf")
        
        pdf_resp = await client.get(pdf_url, params={"format": "pdf"})
        
        print(f"   Status: {pdf_resp.status_code}")
        print(f"   Content-Type: {pdf_resp.headers.get('content-type', 'N/A')}")
        print(f"   Content-Length: {len(pdf_resp.content)} bytes")
        
        # Проверяем что это PDF
        is_pdf = pdf_resp.content[:4] == b'%PDF' if pdf_resp.content else False
        
        if pdf_resp.status_code == 200 and is_pdf:
            print("   ✅ PDF получен!")
            output_file = "test_output.pdf"
            with open(output_file, "wb") as f:
                f.write(pdf_resp.content)
            print(f"   Сохранено в {output_file} ({len(pdf_resp.content)} bytes)")
            return True
        else:
            print(f"   ❌ Не PDF")
            print(f"   First bytes: {pdf_resp.content[:100]}")
            
        return False

if __name__ == "__main__":
    result = asyncio.run(test_pdf_download())
    print(f"\nРезультат: {'✅ Успех' if result else '❌ Неудача'}")
