import json
import logging
import uuid
import httpx
import asyncio
from typing import Optional, Dict, Any, List, AsyncGenerator

logger = logging.getLogger(__name__)


class AgentConnector:
    """Connector for A2A agent communication"""

    def __init__(self, agent_url: str):
        if not agent_url.endswith("/"):
            agent_url += "/"

        self.agent_url = agent_url
        self.session = httpx.AsyncClient(
            base_url=agent_url,
            timeout=httpx.Timeout(180.0, connect=30.0),
        )
        # Отдельная сессия со стрим-таймаутами (read=∞, чтобы SSE не рвался)
        self.stream_session = httpx.AsyncClient(
            base_url=agent_url,
            timeout=httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0),
        )
        self.request_id = 0

    async def send_message(self, text_msg: str, max_retries: int = 3) -> str:
        """Send message to agent with retry logic"""
        for attempt in range(max_retries):
            try:
                result = await self._send_single_message(text_msg, attempt + 1)

                if self._is_retryable_error(result):
                    if attempt < max_retries - 1:
                        retry_delay = 2.0 * (2**attempt)
                        logger.warning(
                            f"Retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(retry_delay)
                        continue
                    return result

                return result

            except Exception as e:
                if attempt < max_retries - 1:
                    retry_delay = 1.0 * (2**attempt)
                    logger.warning(f"Request failed, retrying: {str(e)}")
                    await asyncio.sleep(retry_delay)
                else:
                    error_id = str(uuid.uuid4())[:8]
                    logger.error(f"Final attempt failed (ID: {error_id}): {str(e)}")
                    return f"🚨 Ошибка после {max_retries} попыток (ID: {error_id})\n• {str(e)}"

        return "🚨 Неизвестная ошибка"

    def _is_retryable_error(self, response_text: str) -> bool:
        """Check if response indicates a retryable error"""
        try:
            if response_text.strip().startswith("{"):
                response_data = json.loads(response_text)
                if isinstance(response_data, dict):
                    if (
                        response_data.get("kind") == "task"
                        and response_data.get("status", {}).get("state") == "failed"
                    ):
                        return True
            return False
        except json.JSONDecodeError:
            return False

    async def _send_single_message(self, text_msg: str, attempt: int) -> str:
        """Send a single message attempt"""
        payload = self._create_payload(text_msg)

        response = await self.session.post(
            "",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

        if response.status_code == 200:
            return self._process_response(response)
        else:
            return self._handle_http_error(response)

    def _create_payload(self, text_msg: str) -> Dict[str, Any]:
        """Create RPC payload for agent request"""
        self.request_id += 1
        message_id = str(uuid.uuid4())

        return {
            "jsonrpc": "2.0",
            "id": str(self.request_id),
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": message_id,
                    "parts": [{"kind": "text", "text": text_msg}],
                    "role": "user",
                },
                "configuration": {
                    "acceptedOutputModes": ["text/plain", "application/json"],
                    "historyLength": 10,
                    "blocking": True,
                    "timeout": 120000,
                },
            },
        }

    def _process_response(self, response: httpx.Response) -> str:
        """Process agent response and extract text"""
        try:
            response_data = response.json()

            if "error" in response_data:
                error = response_data["error"]
                return f"🚨 API Error: {error.get('message', 'Unknown error')}"

            result = response_data.get("result", {})
            response_text = self._extract_text_from_response(result)

            if response_text:
                return response_text

            return str(result)

        except json.JSONDecodeError:
            return f"🚨 Invalid JSON response: {response.text[:200]}..."

    def _extract_text_from_response(self, result: Dict[str, Any]) -> Optional[str]:
        """Extract text content from response"""
        text_parts = []

        # Format 1: artifacts
        if "artifacts" in result:
            artifacts = result["artifacts"]
            if isinstance(artifacts, dict):
                artifacts = [artifacts]
            for artifact in artifacts if isinstance(artifacts, list) else []:
                if "parts" in artifact:
                    text = self._extract_text_from_parts(artifact["parts"])
                    if text:
                        text_parts.append(text)

        # Format 2: message with parts
        elif "message" in result and "parts" in result["message"]:
            text = self._extract_text_from_parts(result["message"]["parts"])
            if text:
                text_parts.append(text)

        # Format 3: direct text
        elif "text" in result:
            text_parts.append(result["text"])

        if text_parts:
            final_text = "\n\n".join(text_parts)
            return self._clean_response_text(final_text)

        return None

    def _extract_text_from_parts(self, parts: List[Dict]) -> str:
        """Extract text from message parts"""
        text_parts = []
        for part in parts:
            if isinstance(part, dict) and part.get("kind") == "text":
                text_parts.append(part.get("text", ""))
        return "\n\n".join(text_parts) if text_parts else ""

    def _clean_response_text(self, text: str) -> str:
        """Clean response text for Telegram"""
        if len(text) > 4000:
            text = text[:4000] + "...\n\n[Сообщение сокращено]"
        return text

    def _handle_http_error(self, response: httpx.Response) -> str:
        """Handle HTTP errors"""
        error_id = str(uuid.uuid4())[:8]

        if response.status_code == 404:
            error_msg = "Агент не найден. Проверьте URL."
        elif response.status_code == 401:
            error_msg = "Ошибка авторизации."
        elif 500 <= response.status_code < 600:
            error_msg = f"Ошибка сервера (HTTP {response.status_code})"
        else:
            error_msg = f"HTTP ошибка: {response.status_code}"

        return f"🚨 Ошибка (ID: {error_id})\n• {error_msg}"

    def _create_stream_payload(self, text_msg: str) -> Dict[str, Any]:
        """Create RPC payload for streaming request (message/stream)."""
        self.request_id += 1
        return {
            "jsonrpc": "2.0",
            "id": str(self.request_id),
            "method": "message/stream",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "parts": [{"kind": "text", "text": text_msg}],
                    "role": "user",
                },
                "configuration": {
                    "acceptedOutputModes": ["text/plain", "application/json"],
                    "historyLength": 10,
                },
            },
        }

    async def stream_message(self, text_msg: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Стримит события от агента в формате:

            {"type": "status", "content": "🔧 Использую инструмент: X"}
            {"type": "text",   "content": "частичный ответ"}
            {"type": "done",   "content": "финальный текст"}
            {"type": "error",  "content": "...сообщение об ошибке..."}
        """
        payload = self._create_stream_payload(text_msg)
        accumulated_text = ""

        try:
            async with self.stream_session.stream(
                "POST",
                "",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:200]
                    yield {
                        "type": "error",
                        "content": f"HTTP {response.status_code}: {body}",
                    }
                    return

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.debug(f"Cannot parse SSE chunk: {raw[:120]}")
                        continue

                    if "error" in event:
                        err = event["error"]
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        yield {"type": "error", "content": msg}
                        return

                    result = event.get("result", {})
                    kind = result.get("kind")

                    if kind == "status-update":
                        status = result.get("status", {})
                        state = status.get("state")
                        msg = status.get("message", {})
                        text = self._extract_text_from_parts(msg.get("parts", [])) if msg else ""
                        is_final = result.get("final", False) or state in ("completed", "failed", "canceled")

                        if state == "failed":
                            yield {"type": "error", "content": text or accumulated_text or "Task failed"}
                            return
                        if is_final:
                            final_text = accumulated_text or text
                            yield {"type": "done", "content": self._clean_response_text(final_text)}
                            return
                        # Промежуточный working: A2A-обёртка агента льёт сюда И статусы инструментов
                        # («🔧 Использую инструмент: X»), И инкременты текстового ответа.
                        # Различаем по префиксу.
                        if text:
                            if text.lstrip().startswith("🔧"):
                                yield {"type": "status", "content": text.strip()}
                            else:
                                accumulated_text += text
                                yield {"type": "text", "content": accumulated_text}

                    elif kind == "artifact-update":
                        artifact = result.get("artifact", {})
                        text = self._extract_text_from_parts(artifact.get("parts", []))
                        if text:
                            accumulated_text += text
                            yield {"type": "text", "content": accumulated_text}

                    elif kind == "task":
                        # Initial task object — no useful payload yet, skip.
                        continue

                # Стрим закончился без явного финала — отдадим что есть.
                if accumulated_text:
                    yield {"type": "done", "content": self._clean_response_text(accumulated_text)}
                else:
                    yield {"type": "done", "content": ""}

        except httpx.HTTPError as e:
            yield {"type": "error", "content": f"Сетевая ошибка: {str(e)}"}
        except Exception as e:
            logger.exception("Stream error")
            yield {"type": "error", "content": f"Ошибка стрима: {str(e)}"}

    async def health_check(self) -> bool:
        """Check if agent is reachable"""
        try:
            response = await self.session.get("/health", timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False

    async def close(self):
        """Clean up resources"""
        await self.session.aclose()
        await self.stream_session.aclose()
