"""Определение LangChain агента с поддержкой MCP инструментов."""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

try:
    from .prompts import SYSTEM_PROMPT
except ImportError:
    from prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# Pydantic модели для структурированных инструментов
class JoinConferenceInput(BaseModel):
    """Параметры для подключения к созвону."""
    conference_url: str = Field(description="Ссылка на созвон (Google Meet, Zoom, Teams и др.)")
    theme: str = Field(default="Созвон", description="Название/тема созвона")


class GetTranscriptionInput(BaseModel):
    """Параметры для получения транскрипции."""
    conference_id: str = Field(description="ID созвона (UUID формат)")


class ListConferencesInput(BaseModel):
    """Параметры для списка созвонов."""
    limit: int = Field(default=20, ge=1, le=100, description="Количество записей")
    offset: int = Field(default=0, ge=0, description="Смещение для пагинации")




# RAG Pydantic модели
class RAGSearchInput(BaseModel):
    """Параметры для поиска по базе знаний."""
    query: str = Field(description="Поисковый запрос на естественном языке")
    top_k: int = Field(default=5, ge=1, le=20, description="Количество результатов")


class RAGAddDocumentInput(BaseModel):
    """Параметры для добавления документа в базу знаний."""
    content: str = Field(description="Текст документа для добавления")
    metadata: str = Field(default="{}", description="Метаданные документа в JSON формате")


class SyncConferenceToRAGInput(BaseModel):
    """Параметры для синхронизации транскрипции в RAG."""
    conference_id: str = Field(description="ID созвона из Follow-Up (UUID формат)")


class MCPToolClient:
    """Клиент для вызова инструментов MCP-сервера.

    Сессия инициализируется на каждый вызов локально — без shared state между
    параллельными вызовами одного клиента (иначе race на self._session_id).
    """

    def __init__(self, mcp_url: str, timeout: float = 30.0):
        self.mcp_url = mcp_url.rstrip("/")
        self.timeout = timeout

    async def _initialize_session(self, client: httpx.AsyncClient) -> str:
        """Инициализировать MCP сессию и вернуть её id."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        response = await client.post(
            self.mcp_url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "meeting-assistant-agent", "version": "1.0.0"}
                }
            }
        )

        return response.headers.get("mcp-session-id") or ""

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Вызвать инструмент MCP-сервера."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            session_id = await self._initialize_session(client)

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }

            if session_id:
                headers["Mcp-Session-Id"] = session_id

            response = await client.post(
                self.mcp_url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
            )
            response.raise_for_status()

            # Парсим SSE ответ
            text = response.text
            if "data:" in text:
                # Извлекаем JSON из SSE формата
                for line in text.split("\n"):
                    if line.startswith("data:"):
                        json_str = line[5:].strip()
                        if json_str:
                            import json
                            result = json.loads(json_str)
                            if "error" in result:
                                return {"success": False, "error": result["error"]}
                            # Извлекаем structuredContent если есть
                            if "result" in result:
                                res = result["result"]
                                if "structuredContent" in res:
                                    return res["structuredContent"]
                                if "content" in res and res["content"]:
                                    # Парсим текстовый контент как JSON
                                    content = res["content"][0].get("text", "{}")
                                    try:
                                        return json.loads(content)
                                    except json.JSONDecodeError:
                                        return {"success": True, "content": content}
                            return result.get("result", result)

            result = response.json()
            if "error" in result:
                return {"success": False, "error": result["error"]}

            return result.get("result", result)

    def call_tool_sync(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Синхронная обёртка для call_tool."""
        try:
            # Используем новый event loop чтобы избежать конфликтов
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.call_tool(tool_name, arguments))
            finally:
                loop.close()

            import json
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False, indent=2)
            return str(result)
        except Exception as e:
            logger.error(f"Error calling MCP tool {tool_name}: {e}")
            return f'{{"success": false, "error": "{str(e)}"}}'


def create_followup_tools(mcp_url: str) -> List[StructuredTool]:
    """Создаёт инструменты для Follow-Up MCP."""
    client = MCPToolClient(mcp_url)
    tools = []

    def join_conference(conference_url: str, theme: str = "Созвон") -> str:
        return client.call_tool_sync("join_conference", {
            "conference_url": conference_url,
            "theme": theme
        })

    tools.append(StructuredTool.from_function(
        func=join_conference,
        name="join_conference",
        description="Подключить бота Follow-Up к созвону для записи и транскрибации.",
        args_schema=JoinConferenceInput
    ))

    def get_transcription(conference_id: str) -> str:
        return client.call_tool_sync("get_transcription", {"conference_id": conference_id})

    tools.append(StructuredTool.from_function(
        func=get_transcription,
        name="get_transcription",
        description="Получить транскрипцию завершённого созвона по его ID.",
        args_schema=GetTranscriptionInput
    ))

    def list_conferences(limit: int = 20, offset: int = 0) -> str:
        return client.call_tool_sync("list_conferences", {"limit": limit, "offset": offset})

    tools.append(StructuredTool.from_function(
        func=list_conferences,
        name="list_conferences",
        description="Получить список записанных созвонов с пагинацией.",
        args_schema=ListConferencesInput
    ))

    def get_conference_info(conference_id: str) -> str:
        return client.call_tool_sync("get_conference_info", {"conference_id": conference_id})

    tools.append(StructuredTool.from_function(
        func=get_conference_info,
        name="get_conference_info",
        description="Получить информацию о созвоне (без транскрипции).",
        args_schema=GetTranscriptionInput
    ))

    def sync_conference_to_rag(conference_id: str) -> str:
        """Синхронизировать транскрипцию созвона в базу знаний RAG."""
        return client.call_tool_sync("sync_conference_to_rag", {"conference_id": conference_id})

    tools.append(StructuredTool.from_function(
        func=sync_conference_to_rag,
        name="sync_conference_to_rag",
        description="Синхронизировать транскрипцию созвона в базу знаний RAG. "
                    "Используй когда пользователь просит: 'Сохрани созвон в базу знаний', "
                    "'Синхронизируй встречу с RAG', 'Запомни этот созвон', "
                    "'Добавь транскрипцию в базу данных'.",
        args_schema=SyncConferenceToRAGInput
    ))

    return tools


class CreateCalendarEventInput(BaseModel):
    """Параметры для создания события в календаре."""
    title: str = Field(description="Название события/встречи")
    start_time: str = Field(description="Время начала в формате ISO 8601 (2025-12-13T15:00:00)")
    end_time: str = Field(description="Время окончания в формате ISO 8601 (2025-12-13T16:00:00)")
    description: str = Field(default="", description="Описание события")
    attendees: str = Field(default="", description="Email участников через запятую")
    add_google_meet: bool = Field(default=True, description="Добавить Google Meet видеоконференцию")


class GetEventsForDateInput(BaseModel):
    """Параметры для получения событий за день."""
    date: str = Field(default="", description="Дата в формате YYYY-MM-DD. Пусто = сегодня")


class GetUpcomingEventsInput(BaseModel):
    """Параметры для получения предстоящих событий."""
    days_ahead: int = Field(default=7, ge=1, le=30, description="Дней вперёд (1-30)")


def create_calendar_tools(mcp_url: str) -> List[StructuredTool]:
    """Создаёт инструменты для Google Calendar MCP."""
    client = MCPToolClient(mcp_url)
    tools = []

    # get_current_time_moscow
    def get_current_time_moscow() -> str:
        return client.call_tool_sync("get_current_time_moscow", {})

    tools.append(StructuredTool.from_function(
        func=get_current_time_moscow,
        name="get_current_time_moscow",
        description="Получить текущее время по Москве. Используй для определения 'сегодня', 'завтра' и т.д."
    ))

    # create_calendar_event - правильное название инструмента MCP
    def create_calendar_event(
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        attendees: str = "",
        add_google_meet: bool = True
    ) -> str:
        return client.call_tool_sync("create_calendar_event", {
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "description": description,
            "attendees": attendees,
            "add_google_meet": add_google_meet
        })

    tools.append(StructuredTool.from_function(
        func=create_calendar_event,
        name="create_calendar_event",
        description="Создать событие в Google Calendar с участниками и Google Meet. "
                    "Требует start_time и end_time в формате ISO 8601 (например 2025-12-13T15:00:00).",
        args_schema=CreateCalendarEventInput
    ))

    # get_events_for_date
    def get_events_for_date(date: str = "") -> str:
        return client.call_tool_sync("get_events_for_date", {"date": date})

    tools.append(StructuredTool.from_function(
        func=get_events_for_date,
        name="get_events_for_date",
        description="Получить события за конкретный день. Формат даты: YYYY-MM-DD. Пусто = сегодня.",
        args_schema=GetEventsForDateInput
    ))

    # get_upcoming_events
    def get_upcoming_events(days_ahead: int = 7) -> str:
        return client.call_tool_sync("get_upcoming_events", {"days_ahead": days_ahead})

    tools.append(StructuredTool.from_function(
        func=get_upcoming_events,
        name="get_upcoming_events",
        description="Получить предстоящие события на несколько дней вперёд.",
        args_schema=GetUpcomingEventsInput
    ))

    return tools


def create_rag_tools(mcp_url: str) -> List[StructuredTool]:
    """Создаёт инструменты для Managed RAG MCP."""
    client = MCPToolClient(mcp_url)
    tools = []

    def rag_search(query: str, top_k: int = 5) -> str:
        """Поиск по базе знаний (транскрипции созвонов)."""
        return client.call_tool_sync("search", {"query": query, "top_k": top_k})

    tools.append(StructuredTool.from_function(
        func=rag_search,
        name="search_knowledge_base",
        description="Поиск по базе знаний с транскрипциями созвонов. "
                    "Используй для вопросов типа 'О чём говорили на встрече?', "
                    "'Какие решения приняли?', 'Что обсуждали по проекту X?'",
        args_schema=RAGSearchInput
    ))

    def rag_add_document(content: str, metadata: str = "{}") -> str:
        """Добавить документ в базу знаний."""
        import json
        try:
            meta = json.loads(metadata) if metadata else {}
        except json.JSONDecodeError:
            meta = {}
        return client.call_tool_sync("add_document", {"content": content, "metadata": meta})

    tools.append(StructuredTool.from_function(
        func=rag_add_document,
        name="add_to_knowledge_base",
        description="Добавить документ (транскрипцию) в базу знаний для последующего поиска.",
        args_schema=RAGAddDocumentInput
    ))

    return tools


def create_meeting_assistant_agent(
    followup_mcp_url: Optional[str] = None,
    gcalendar_mcp_url: Optional[str] = None,
    rag_mcp_url: Optional[str] = None,
) -> AgentExecutor:
    """Создаёт LangChain агента Meeting Assistant."""
    model_name = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
    base_url = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    api_key = os.getenv("LLM_API_KEY")

    logger.info(f"Инициализация LLM: model={model_name}, base_url={base_url}")

    default_headers = {}
    site_url = os.getenv("OPENROUTER_SITE_URL")
    app_name = os.getenv("OPENROUTER_APP_NAME")
    if site_url:
        default_headers["HTTP-Referer"] = site_url
    if app_name:
        default_headers["X-Title"] = app_name

    llm = ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.7,
        default_headers=default_headers or None,
    )

    tools: List[StructuredTool] = []

    if followup_mcp_url:
        logger.info(f"Подключаем Follow-Up MCP: {followup_mcp_url}")
        tools.extend(create_followup_tools(followup_mcp_url))

    if gcalendar_mcp_url:
        logger.info(f"Подключаем Google Calendar MCP: {gcalendar_mcp_url}")
        tools.extend(create_calendar_tools(gcalendar_mcp_url))

    if rag_mcp_url:
        logger.info(f"Подключаем Managed RAG MCP: {rag_mcp_url}")
        tools.extend(create_rag_tools(rag_mcp_url))

    if not tools:
        logger.warning("Не настроены MCP-серверы. Агент будет работать без инструментов.")
    else:
        logger.info(f"Загружено {len(tools)} инструментов: {[t.name for t in tools]}")

    system_prompt = os.getenv("AGENT_SYSTEM_PROMPT", SYSTEM_PROMPT)

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)

    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=15,
    )

    return agent_executor


def create_langchain_agent(mcp_urls: Optional[str] = None) -> AgentExecutor:
    """Создаёт агента из строки URL (для совместимости с lab3)."""
    followup_url = os.getenv("FOLLOWUP_MCP_URL")
    gcalendar_url = os.getenv("GCALENDAR_MCP_URL")
    rag_url = os.getenv("MANAGED_RAG_MCP_URL")

    if mcp_urls and not followup_url:
        urls = [u.strip() for u in mcp_urls.split(",")]
        followup_url = urls[0] if urls else None

    return create_meeting_assistant_agent(
        followup_mcp_url=followup_url,
        gcalendar_mcp_url=gcalendar_url,
        rag_mcp_url=rag_url,
    )






