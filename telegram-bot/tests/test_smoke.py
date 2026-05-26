"""Smoke-тесты telegram-бота: импорты и базовая инициализация."""

import pytest


@pytest.fixture(autouse=True)
def _bot_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "test_bot")
    monkeypatch.setenv("AGENT_API_URL", "http://localhost:10000")


class TestImports:
    def test_imports_config(self):
        from config import config as cfg_module
        assert hasattr(cfg_module, "Config")

    def test_imports_handlers(self):
        from src.handlers import common
        assert hasattr(common, "router")

    def test_imports_keyboards(self):
        from src import keyboards as kb
        assert hasattr(kb, "main_menu")

    def test_imports_services(self):
        from src.services.agent_connector import AgentConnector
        from src.services.request_manager import request_manager
        from src.utils.session import SessionStore

        assert AgentConnector is not None
        assert request_manager is not None
        assert SessionStore is not None


class TestConfigLoading:
    def test_config_loads_from_env(self):
        from config.config import Config
        cfg = Config()
        assert cfg.TELEGRAM_BOT_TOKEN == "test:token"
        assert cfg.AGENT_API_URL == "http://localhost:10000"
        # Новая дефолтная фича
        assert cfg.AUTO_CONNECT_ON_START is True


class TestAgentConnectorInit:
    def test_connector_normalizes_url(self):
        from src.services.agent_connector import AgentConnector
        c = AgentConnector("http://localhost:10000")
        assert c.agent_url.endswith("/")

    def test_connector_creates_session(self):
        from src.services.agent_connector import AgentConnector
        c = AgentConnector("http://localhost:10000")
        assert c.session is not None
        assert c.request_id == 0
