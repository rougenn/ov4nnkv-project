"""Unit-тесты для Meeting Assistant Agent."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _llm_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")


class TestPrompts:
    def test_system_prompt_exists(self):
        from src.prompts import SYSTEM_PROMPT
        assert SYSTEM_PROMPT is not None
        assert len(SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_meeting_capabilities(self):
        from src.prompts import SYSTEM_PROMPT
        # Промпт должен описывать ключевые tool-и
        assert "join_conference" in SYSTEM_PROMPT
        assert "get_transcription" in SYSTEM_PROMPT
        assert "search_knowledge_base" in SYSTEM_PROMPT


class TestMCPToolClient:
    def test_init_default_timeout(self):
        from src.agent import MCPToolClient
        client = MCPToolClient("http://localhost:8000/mcp")
        assert client.mcp_url == "http://localhost:8000/mcp"
        assert client.timeout == 30.0

    def test_init_strips_trailing_slash(self):
        from src.agent import MCPToolClient
        client = MCPToolClient("http://localhost:8000/mcp/")
        assert client.mcp_url == "http://localhost:8000/mcp"

    def test_custom_timeout(self):
        from src.agent import MCPToolClient
        client = MCPToolClient("http://localhost:8000/mcp", timeout=10.0)
        assert client.timeout == 10.0

    def test_call_tool_sync_handles_exception(self):
        from src.agent import MCPToolClient
        # Заведомо мёртвый порт + микро-таймаут, чтобы не зависеть от того,
        # запущен ли локально настоящий MCP на 8000.
        client = MCPToolClient("http://127.0.0.1:1/mcp", timeout=0.1)
        result = client.call_tool_sync("nonexistent_tool", {})
        assert isinstance(result, str)
        payload = json.loads(result)
        assert payload["success"] is False
        assert "error" in payload


class TestToolFactories:
    def test_create_followup_tools_count_and_names(self):
        from src.agent import create_followup_tools
        tools = create_followup_tools("http://localhost:8000/mcp")
        names = {t.name for t in tools}
        assert names == {
            "join_conference",
            "get_transcription",
            "list_conferences",
            "get_conference_info",
            "sync_conference_to_rag",
        }

    def test_create_calendar_tools_count_and_names(self):
        from src.agent import create_calendar_tools
        tools = create_calendar_tools("http://localhost:8001/mcp")
        names = {t.name for t in tools}
        assert names == {
            "get_current_time_moscow",
            "create_calendar_event",
            "get_events_for_date",
            "get_upcoming_events",
        }

    def test_create_rag_tools_count_and_names(self):
        from src.agent import create_rag_tools
        tools = create_rag_tools("http://localhost:8002/mcp")
        names = {t.name for t in tools}
        assert names == {"search_knowledge_base", "add_to_knowledge_base"}


class TestAgentBuilder:
    def test_no_mcp_has_no_tools(self):
        from src.agent import create_meeting_assistant_agent
        executor = create_meeting_assistant_agent()
        assert len(executor.tools) == 0

    def test_with_all_mcps(self):
        from src.agent import create_meeting_assistant_agent
        executor = create_meeting_assistant_agent(
            followup_mcp_url="http://localhost:8000/mcp",
            gcalendar_mcp_url="http://localhost:8001/mcp",
            rag_mcp_url="http://localhost:8002/mcp",
        )
        # 5 followup + 4 calendar + 2 rag
        assert len(executor.tools) == 11

    def test_with_followup_only(self):
        from src.agent import create_meeting_assistant_agent
        executor = create_meeting_assistant_agent(
            followup_mcp_url="http://localhost:8000/mcp"
        )
        assert len(executor.tools) == 5

    def test_openrouter_headers_set(self, monkeypatch):
        """Если заданы OPENROUTER_SITE_URL/APP_NAME — они должны лететь в default_headers."""
        monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")
        monkeypatch.setenv("OPENROUTER_APP_NAME", "TestApp")
        with patch("src.agent.ChatOpenAI") as mock_llm:
            mock_llm.return_value = MagicMock()
            from src.agent import create_meeting_assistant_agent
            create_meeting_assistant_agent()
            kwargs = mock_llm.call_args.kwargs
            assert kwargs["default_headers"] == {
                "HTTP-Referer": "https://example.com",
                "X-Title": "TestApp",
            }

    def test_openrouter_headers_omitted_when_unset(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_SITE_URL", raising=False)
        monkeypatch.delenv("OPENROUTER_APP_NAME", raising=False)
        with patch("src.agent.ChatOpenAI") as mock_llm:
            mock_llm.return_value = MagicMock()
            from src.agent import create_meeting_assistant_agent
            create_meeting_assistant_agent()
            kwargs = mock_llm.call_args.kwargs
            assert kwargs["default_headers"] is None


class TestA2AWrapper:
    def test_session_history_per_session(self):
        from src.a2a_wrapper import MeetingAssistantA2AWrapper
        wrapper = MeetingAssistantA2AWrapper(MagicMock())
        h1 = wrapper._get_session_history("s1")
        h2 = wrapper._get_session_history("s2")
        assert h1 == []
        assert h2 == []
        h1.append(("human", "hi"))
        # Та же сессия — тот же список
        assert wrapper._get_session_history("s1") == [("human", "hi")]
        # Другая сессия — изолированная
        assert wrapper._get_session_history("s2") == []

    def test_supported_content_types(self):
        from src.a2a_wrapper import MeetingAssistantA2AWrapper
        assert "text" in MeetingAssistantA2AWrapper.SUPPORTED_CONTENT_TYPES
        assert "text/plain" in MeetingAssistantA2AWrapper.SUPPORTED_CONTENT_TYPES

    @pytest.mark.asyncio
    async def test_invoke_calls_executor_and_updates_history(self):
        from src.a2a_wrapper import MeetingAssistantA2AWrapper
        mock_executor = MagicMock()
        mock_executor.invoke = MagicMock(return_value={"output": "hello back"})
        wrapper = MeetingAssistantA2AWrapper(mock_executor)
        result = await wrapper.invoke("ping", "session-1")
        assert result["is_task_complete"] is True
        assert result["is_error"] is False
        assert result["content"] == "hello back"
        history = wrapper._get_session_history("session-1")
        assert history == [("human", "ping"), ("assistant", "hello back")]

    @pytest.mark.asyncio
    async def test_invoke_handles_exception(self):
        from src.a2a_wrapper import MeetingAssistantA2AWrapper
        mock_executor = MagicMock()
        mock_executor.invoke = MagicMock(side_effect=RuntimeError("boom"))
        wrapper = MeetingAssistantA2AWrapper(mock_executor)
        result = await wrapper.invoke("ping", "session-2")
        assert result["is_error"] is True
        assert "boom" in result["content"]
