"""Smoke-тесты: проверка что все модули импортируются и инициализируются."""


import pytest


@pytest.fixture(autouse=True)
def _llm_env(monkeypatch):
    """Подставляем фейковые LLM переменные, чтобы агент мог инициализироваться без реального ключа."""
    monkeypatch.setenv("LLM_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    yield


class TestImports:
    """Все ключевые модули должны импортироваться без ошибок."""

    def test_imports_prompts(self):
        from src import prompts
        assert hasattr(prompts, "SYSTEM_PROMPT")

    def test_imports_agent(self):
        from src import agent
        assert hasattr(agent, "create_meeting_assistant_agent")
        assert hasattr(agent, "MCPToolClient")

    def test_imports_a2a_wrapper(self):
        from src import a2a_wrapper
        assert hasattr(a2a_wrapper, "MeetingAssistantA2AWrapper")

    def test_imports_task_manager(self):
        from src import agent_task_manager
        assert hasattr(agent_task_manager, "MeetingAssistantAgentExecutor")


class TestConfigDefaults:
    """Дефолтные значения должны быть OpenRouter-совместимыми."""

    def test_default_base_url_is_openrouter(self, monkeypatch):
        from unittest.mock import MagicMock, patch
        monkeypatch.delenv("LLM_API_BASE", raising=False)
        from src import agent
        with patch.object(agent, "ChatOpenAI") as mock_llm:
            mock_llm.return_value = MagicMock()
            agent.create_meeting_assistant_agent()
            assert mock_llm.call_args.kwargs["base_url"] == "https://openrouter.ai/api/v1"

    def test_default_model_is_gpt_4o_mini(self, monkeypatch):
        from unittest.mock import MagicMock, patch
        monkeypatch.delenv("LLM_MODEL", raising=False)
        from src import agent
        with patch.object(agent, "ChatOpenAI") as mock_llm:
            mock_llm.return_value = MagicMock()
            agent.create_meeting_assistant_agent()
            assert mock_llm.call_args.kwargs["model"] == "openai/gpt-4o-mini"


class TestAgentInitializesWithoutMCP:
    """Агент должен инициализироваться даже без MCP-серверов."""

    def test_no_mcp(self):
        from src.agent import create_meeting_assistant_agent
        executor = create_meeting_assistant_agent()
        assert executor is not None
        assert len(executor.tools) == 0
