"""Integration-тесты с реальным OpenRouter API.

ВАЖНО: эти тесты делают **платные** вызовы к OpenRouter и поэтому **выключены
по умолчанию** — чтобы не сжигать токены на CI и при локальном `pytest`.

Чтобы запустить вручную:
    RUN_LLM_INTEGRATION_TESTS=1 LLM_API_KEY=sk-or-v1-... \
        uv run pytest tests/test_integration.py -v -m integration

Маркер `integration` остаётся для совместимости (можно фильтровать в CI).
"""

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_LLM_INTEGRATION_TESTS") != "1",
        reason=(
            "Integration-тесты к OpenRouter отключены (экономия токенов). "
            "Включить: RUN_LLM_INTEGRATION_TESTS=1"
        ),
    ),
]


def test_openrouter_chat_completion_returns_text():
    """Прямой OpenAI SDK-вызов к OpenRouter — проверяем что ключ/модель/эндпоинт работают."""
    from openai import OpenAI

    base_url = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

    client = OpenAI(api_key=os.getenv("LLM_API_KEY"), base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        max_tokens=20,
        temperature=0.0,
        messages=[{"role": "user", "content": "Ответь одним словом: тест"}],
    )
    content = response.choices[0].message.content
    assert content is not None
    assert len(content.strip()) > 0


def test_agent_executor_invokes_real_llm_without_tools():
    """Полный путь: создаём агента (без MCP) → отправляем простой запрос → получаем ответ."""
    from src.agent import create_meeting_assistant_agent

    executor = create_meeting_assistant_agent()
    result = executor.invoke({"input": "Скажи 'привет'", "chat_history": []})
    assert "output" in result
    assert isinstance(result["output"], str)
    assert len(result["output"]) > 0
