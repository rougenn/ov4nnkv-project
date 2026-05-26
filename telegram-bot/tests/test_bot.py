"""Unit-тесты Telegram-бота."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def _bot_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "test_bot")
    monkeypatch.setenv("AGENT_API_URL", "http://localhost:10000")


class TestAgentConnector:
    def test_init_adds_trailing_slash(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        assert connector.agent_url == "https://example.com/"

    def test_init_keeps_trailing_slash(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com/")
        assert connector.agent_url == "https://example.com/"

    def test_create_payload_structure(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        payload = connector._create_payload("Hello")

        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "message/send"
        assert payload["params"]["message"]["parts"][0]["text"] == "Hello"
        assert payload["params"]["message"]["role"] == "user"
        # Каждый вызов увеличивает request_id
        payload2 = connector._create_payload("World")
        assert payload2["id"] != payload["id"]

    def test_is_retryable_error_task_failed(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        response = '{"kind": "task", "status": {"state": "failed"}}'
        assert connector._is_retryable_error(response) is True

    def test_is_retryable_error_success(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        response = '{"kind": "task", "status": {"state": "completed"}}'
        assert connector._is_retryable_error(response) is False

    def test_is_retryable_handles_invalid_json(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        assert connector._is_retryable_error("not json") is False
        assert connector._is_retryable_error("") is False

    def test_clean_response_text_truncates_long_text(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        long_text = "a" * 5000
        result = connector._clean_response_text(long_text)
        assert len(result) < 4100
        assert "[Сообщение сокращено]" in result

    def test_clean_response_text_keeps_short(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        assert connector._clean_response_text("short") == "short"

    def test_extract_text_from_artifacts(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        result = {
            "artifacts": [
                {"parts": [{"kind": "text", "text": "answer-1"}, {"kind": "text", "text": "answer-2"}]}
            ]
        }
        assert "answer-1" in connector._extract_text_from_response(result)
        assert "answer-2" in connector._extract_text_from_response(result)

    def test_extract_text_from_message_parts(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        result = {"message": {"parts": [{"kind": "text", "text": "hi"}]}}
        assert connector._extract_text_from_response(result) == "hi"

    def test_extract_text_direct_field(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")
        assert connector._extract_text_from_response({"text": "direct"}) == "direct"

    @pytest.mark.asyncio
    async def test_send_message_processes_artifacts(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "result": {
                "artifacts": [{"parts": [{"kind": "text", "text": "pong"}]}]
            }
        }
        fake_response.text = json.dumps(fake_response.json.return_value)

        with patch.object(connector.session, "post", new=AsyncMock(return_value=fake_response)):
            result = await connector.send_message("ping", max_retries=1)
            assert "pong" in result

    @pytest.mark.asyncio
    async def test_send_message_returns_user_friendly_error_on_http_500(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")

        fake_response = MagicMock()
        fake_response.status_code = 500

        with patch.object(connector.session, "post", new=AsyncMock(return_value=fake_response)):
            result = await connector.send_message("hi", max_retries=1)
            assert "🚨" in result
            assert "500" in result

    @pytest.mark.asyncio
    async def test_send_message_retries_on_exception(self):
        from src.services.agent_connector import AgentConnector
        connector = AgentConnector("https://example.com")

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {"result": {"text": "ok"}}
        ok_response.text = '{"result": {"text": "ok"}}'

        call_count = {"n": 0}

        async def flaky_post(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise httpx.ConnectError("boom")
            return ok_response

        with patch.object(connector.session, "post", new=flaky_post):
            # отключим backoff чтобы тест не висел
            with patch("asyncio.sleep", new=AsyncMock()):
                result = await connector.send_message("hi", max_retries=3)
                assert "ok" in result
                assert call_count["n"] == 2


class TestStreamMessage:
    """Парсинг SSE стрима от A2A агента."""

    @staticmethod
    def _sse_lines(events: list) -> list:
        """Превращаем список JSON-RPC ответов в SSE-строки 'data: {...}'."""
        lines = []
        for ev in events:
            lines.append(f"data: {json.dumps(ev)}")
            lines.append("")
        return lines

    @pytest.mark.asyncio
    async def test_stream_yields_status_text_done(self):
        from src.services.agent_connector import AgentConnector

        events = [
            {"jsonrpc": "2.0", "id": "1", "result": {"kind": "task", "id": "t1"}},
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "kind": "status-update",
                    "status": {
                        "state": "working",
                        "message": {"parts": [{"kind": "text", "text": "🔧 Использую инструмент: search"}]},
                    },
                    "final": False,
                },
            },
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "kind": "artifact-update",
                    "artifact": {"parts": [{"kind": "text", "text": "Ответ "}]},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "kind": "artifact-update",
                    "artifact": {"parts": [{"kind": "text", "text": "готов."}]},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "kind": "status-update",
                    "status": {"state": "completed", "message": {"parts": []}},
                    "final": True,
                },
            },
        ]

        # Мокаем stream-context-manager у self.stream_session
        connector = AgentConnector("https://example.com")

        sse_lines = self._sse_lines(events)

        class FakeStreamResponse:
            status_code = 200

            async def aiter_lines(self):
                for line in sse_lines:
                    yield line

            async def aread(self):
                return b""

        class FakeStreamCM:
            async def __aenter__(self):
                return FakeStreamResponse()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch.object(connector.stream_session, "stream", return_value=FakeStreamCM()):
            results = []
            async for ev in connector.stream_message("hi"):
                results.append(ev)

        types = [r["type"] for r in results]
        assert "status" in types
        assert "text" in types
        assert results[-1]["type"] == "done"
        # accumulated text должен дойти до done
        assert "Ответ готов." in results[-1]["content"] or any(
            "Ответ готов." in r["content"] for r in results if r["type"] == "text"
        )

    @pytest.mark.asyncio
    async def test_stream_accumulates_text_from_working_status_updates(self):
        """A2A-обёртка отдаёт ответ агента инкрементами в status-update (state=working),
        без отдельных artifact-update. Бот должен накопить текст и отдать в done."""
        from src.services.agent_connector import AgentConnector

        events = [
            {"jsonrpc": "2.0", "id": "1", "result": {"kind": "task", "id": "t1"}},
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "kind": "status-update",
                    "status": {"state": "working", "message": {"parts": [{"kind": "text", "text": "🔧 Использую инструмент: search\n"}]}},
                    "final": False,
                },
            },
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "kind": "status-update",
                    "status": {"state": "working", "message": {"parts": [{"kind": "text", "text": "Привет, "}]}},
                    "final": False,
                },
            },
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "kind": "status-update",
                    "status": {"state": "working", "message": {"parts": [{"kind": "text", "text": "это ответ."}]}},
                    "final": False,
                },
            },
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "kind": "status-update",
                    "status": {"state": "completed", "message": {"parts": []}},
                    "final": True,
                },
            },
        ]
        sse_lines = self._sse_lines(events)

        connector = AgentConnector("https://example.com")

        class FakeStreamResponse:
            status_code = 200
            async def aiter_lines(self):
                for line in sse_lines:
                    yield line
            async def aread(self):
                return b""

        class FakeStreamCM:
            async def __aenter__(self):
                return FakeStreamResponse()
            async def __aexit__(self, *a):
                return False

        with patch.object(connector.stream_session, "stream", return_value=FakeStreamCM()):
            results = [ev async for ev in connector.stream_message("hi")]

        # Должно быть: 1 status + 2 text + 1 done
        types = [r["type"] for r in results]
        assert types.count("status") == 1
        assert types.count("text") == 2
        assert results[-1]["type"] == "done"
        assert results[-1]["content"] == "Привет, это ответ."

    @pytest.mark.asyncio
    async def test_stream_yields_error_on_jsonrpc_error(self):
        from src.services.agent_connector import AgentConnector

        events = [{"jsonrpc": "2.0", "id": "1", "error": {"code": -32000, "message": "boom"}}]
        sse_lines = [f"data: {json.dumps(events[0])}", ""]

        connector = AgentConnector("https://example.com")

        class FakeStreamResponse:
            status_code = 200

            async def aiter_lines(self):
                for line in sse_lines:
                    yield line

            async def aread(self):
                return b""

        class FakeStreamCM:
            async def __aenter__(self):
                return FakeStreamResponse()

            async def __aexit__(self, *a):
                return False

        with patch.object(connector.stream_session, "stream", return_value=FakeStreamCM()):
            results = [ev async for ev in connector.stream_message("hi")]

        assert results[-1]["type"] == "error"
        assert "boom" in results[-1]["content"]

    @pytest.mark.asyncio
    async def test_stream_yields_error_on_http_non_200(self):
        from src.services.agent_connector import AgentConnector

        connector = AgentConnector("https://example.com")

        class FakeStreamResponse:
            status_code = 500

            async def aiter_lines(self):
                if False:
                    yield ""  # never

            async def aread(self):
                return b"internal error"

        class FakeStreamCM:
            async def __aenter__(self):
                return FakeStreamResponse()

            async def __aexit__(self, *a):
                return False

        with patch.object(connector.stream_session, "stream", return_value=FakeStreamCM()):
            results = [ev async for ev in connector.stream_message("hi")]

        assert results[-1]["type"] == "error"
        assert "500" in results[-1]["content"]


class TestSessionStore:
    def test_singleton(self):
        from src.utils.session import SessionStore
        store1 = SessionStore()
        store2 = SessionStore()
        assert store1 is store2

    def test_connect_and_get_agent(self):
        from src.services.agent_connector import AgentConnector
        from src.utils.session import SessionStore
        store = SessionStore()
        store.connect_agent(123, "https://example.com")
        agent = store.get_agent(123)
        assert isinstance(agent, AgentConnector)
        store.disconnect_agent(123)

    def test_disconnect_agent(self):
        from src.utils.session import SessionStore
        store = SessionStore()
        store.connect_agent(456, "https://example.com")
        store.disconnect_agent(456)
        assert store.get_agent(456) is None

    def test_is_connected(self):
        from src.utils.session import SessionStore
        store = SessionStore()
        store.connect_agent(789, "https://example.com")
        assert store.is_connected(789) is True
        assert store.is_connected(999) is False
        store.disconnect_agent(789)


class TestRequestManager:
    def test_add_and_cancel(self):
        from src.services.request_manager import RequestManager

        async def _run():
            mgr = RequestManager()
            task = asyncio.create_task(asyncio.sleep(10))
            mgr.add_request(1, task)
            assert mgr.get_active_request(1) is task
            mgr.cancel_request(1)
            assert mgr.get_active_request(1) is None
            # Дать loop'у обработать отмену
            await asyncio.sleep(0)
            assert task.cancelled()

        asyncio.run(_run())

    def test_adding_replaces_previous(self):
        from src.services.request_manager import RequestManager

        async def _run():
            mgr = RequestManager()
            t1 = asyncio.create_task(asyncio.sleep(10))
            t2 = asyncio.create_task(asyncio.sleep(10))
            mgr.add_request(1, t1)
            mgr.add_request(1, t2)
            # t1 должен быть отменён
            await asyncio.sleep(0)
            assert t1.cancelled()
            assert mgr.get_active_request(1) is t2
            mgr.cancel_request(1)

        asyncio.run(_run())
