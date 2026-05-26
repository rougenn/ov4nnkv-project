"""E2E-тесты для MCP Follow-Up сервера."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import re

import sys
from pathlib import Path
# Добавляем src в путь
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Импортируем напрямую из модулей (без относительных импортов)
from followup_client import (
    FollowUpClient,
    FollowUpAPIError,
    AuthenticationError,
    NetworkError,
)


# Копируем функции валидации для тестирования (чтобы не импортировать server.py)
def _is_valid_url(url: str) -> bool:
    """Проверить, что строка является валидным URL."""
    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return url_pattern.match(url) is not None


def _is_conference_url(url: str) -> bool:
    """Проверить, что URL похож на ссылку для видеоконференции."""
    conference_domains = [
        "meet.google.com",
        "zoom.us", "zoom.com",
        "teams.microsoft.com", "teams.live.com",
        "telemost.yandex.ru", "telemost.yandex.com",
        "salutejazz.ru", "jazz.sber.ru",
        "konturtalk.ru",
        "meet.jit.si",
    ]
    url_lower = url.lower()
    return any(domain in url_lower for domain in conference_domains)


class TestUrlValidation:
    """Тесты валидации URL."""
    
    def test_valid_urls(self):
        """Тест валидных URL."""
        assert _is_valid_url("https://meet.google.com/abc-defg-hij") is True
        assert _is_valid_url("https://zoom.us/j/123456789") is True
        assert _is_valid_url("http://localhost:8080/meeting") is True
    
    def test_invalid_urls(self):
        """Тест невалидных URL."""
        assert _is_valid_url("not-a-url") is False
        assert _is_valid_url("ftp://files.example.com") is False
        assert _is_valid_url("") is False
    
    def test_conference_urls(self):
        """Тест определения URL конференций."""
        assert _is_conference_url("https://meet.google.com/abc-defg-hij") is True
        assert _is_conference_url("https://zoom.us/j/123456789") is True
        assert _is_conference_url("https://teams.microsoft.com/l/meetup") is True
        assert _is_conference_url("https://telemost.yandex.ru/j/123") is True
        assert _is_conference_url("https://example.com/page") is False


class TestFollowUpClientJoinConference:
    """Тесты метода join_conference клиента."""
    
    @pytest.fixture
    def client(self):
        """Создать тестовый клиент."""
        return FollowUpClient(
            email="test@example.com",
            password="testpassword",
            base_url="https://api.follow-up.tech"
        )
    
    @pytest.mark.asyncio
    async def test_join_conference_success(self, client):
        """Тест успешного подключения к созвону."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id": "conf-123", "status": "connecting"}'
        mock_response.json.return_value = {"id": "conf-123", "status": "connecting"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.join_conference(
                conference_url="https://meet.google.com/abc-defg-hij",
                theme="Тестовый созвон"
            )
            
            assert result["id"] == "conf-123"
            mock_http_client.request.assert_called_once()
            call_kwargs = mock_http_client.request.call_args
            assert call_kwargs.kwargs["json"]["link"] == "https://meet.google.com/abc-defg-hij"
            assert call_kwargs.kwargs["json"]["source"] == "googleMeet"
            assert call_kwargs.kwargs["json"]["externalId"] == "abc-defg-hij"
    
    @pytest.mark.asyncio
    async def test_join_conference_api_error(self, client):
        """Тест обработки ошибки API при подключении."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"message": "Invalid link"}'
        mock_response.json.return_value = {"message": "Invalid link"}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(FollowUpAPIError) as exc_info:
                await client.join_conference("https://meet.google.com/invalid")
            
            assert exc_info.value.status_code == 400


class TestFollowUpClientListConferences:
    """E2E тесты метода list_conferences клиента."""
    
    @pytest.fixture
    def client(self):
        """Создать тестовый клиент."""
        return FollowUpClient(
            email="test@example.com",
            password="testpassword",
            base_url="https://api.follow-up.tech"
        )
    
    @pytest.mark.asyncio
    async def test_list_conferences_success(self, client):
        """Тест успешного получения списка созвонов."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"page": [...], "summary": {"elements": 1}}'
        mock_response.json.return_value = {
            "page": [
                {"id": "conf-1", "theme": "Встреча 1", "date": "2024-12-07T10:00:00", "duration": 1800, "status": "ready"}
            ],
            "summary": {"pages": 1, "elements": 1}
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.list_conferences(limit=20, offset=0)
            
            assert result["total"] == 1
            assert len(result["conferences"]) == 1
            assert result["conferences"][0]["id"] == "conf-1"
            
            # Проверяем что запрос был POST с правильным эндпоинтом
            mock_http_client.request.assert_called_once()
            call_kwargs = mock_http_client.request.call_args
            assert call_kwargs.kwargs["method"] == "POST"
            assert "/api/conference/listing/history" in call_kwargs.kwargs["url"]
    
    @pytest.mark.asyncio
    async def test_list_conferences_pagination(self, client):
        """Тест пагинации списка созвонов."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"page": [...], "summary": {"elements": 100}}'
        mock_response.json.return_value = {
            "page": [{"id": "conf-21", "theme": "Встреча 21"}],
            "summary": {"pages": 10, "elements": 100}
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.list_conferences(limit=10, offset=20)
            
            assert result["total"] == 100
            call_kwargs = mock_http_client.request.call_args
            # Проверяем пагинацию в JSON body
            assert call_kwargs.kwargs["json"]["paging"]["size"] == 10
            assert call_kwargs.kwargs["json"]["paging"]["current"] == 3  # page 3 for offset=20, limit=10
    
    @pytest.mark.asyncio
    async def test_list_conferences_empty_result(self, client):
        """Тест пустого списка созвонов."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"page": [], "summary": {"elements": 0}}'
        mock_response.json.return_value = {"page": [], "summary": {"pages": 0, "elements": 0}}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.list_conferences()
            
            assert result["total"] == 0
            assert result["conferences"] == []
    
    @pytest.mark.asyncio
    async def test_list_conferences_auth_error(self, client):
        """Тест ошибки авторизации при получении списка."""
        client._access_token = "invalid_token"
        client.email = None
        client.password = None
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(AuthenticationError):
                await client.list_conferences()
    
    @pytest.mark.asyncio
    async def test_list_conferences_network_error(self, client):
        """Тест сетевой ошибки при получении списка."""
        client._access_token = "test_token"
        
        import httpx
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(NetworkError):
                await client.list_conferences()
