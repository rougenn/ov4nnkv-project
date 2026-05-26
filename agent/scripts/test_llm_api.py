#!/usr/bin/env python3
"""Smoke-проверка LLM API (OpenRouter или OpenAI-совместимый эндпоинт).

Usage:
    cd agent && uv run python scripts/test_llm_api.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

    if not api_key:
        print("❌ LLM_API_KEY не задан — заполните .env")
        return 1

    print(f"Endpoint: {base_url}")
    print(f"Model:    {model}")
    print(f"API key:  {api_key[:14]}…")
    print("-" * 50)

    try:
        from openai import OpenAI
    except ImportError:
        print("❌ Установите openai: uv add openai (или pip install openai)")
        return 1

    default_headers = {}
    if site := os.getenv("OPENROUTER_SITE_URL"):
        default_headers["HTTP-Referer"] = site
    if app := os.getenv("OPENROUTER_APP_NAME"):
        default_headers["X-Title"] = app

    client = OpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers or None)

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=50,
            temperature=0.0,
            messages=[{"role": "user", "content": "Скажи одно слово: ок"}],
        )
        content = response.choices[0].message.content
        print(f"✅ Ответ: {content}")
        return 0
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
