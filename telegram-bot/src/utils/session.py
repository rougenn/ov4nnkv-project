from typing import Dict, Optional
from src.services.agent_connector import AgentConnector


class SessionStore:
    """Store user sessions with agent connections"""

    _instance: Optional["SessionStore"] = None
    _store: Dict[int, AgentConnector]

    def __new__(cls) -> "SessionStore":
        if cls._instance is None:
            cls._instance = super(SessionStore, cls).__new__(cls)
            cls._instance._store = {}
        return cls._instance

    def get_agent(self, user_id: int) -> Optional[AgentConnector]:
        return self._store.get(user_id)

    def connect_agent(self, user_id: int, agent_url: str) -> None:
        self._store[user_id] = AgentConnector(agent_url)

    def disconnect_agent(self, user_id: int) -> None:
        if user_id in self._store:
            self._store.pop(user_id)

    def is_connected(self, user_id: int) -> bool:
        return user_id in self._store


session_store = SessionStore()
