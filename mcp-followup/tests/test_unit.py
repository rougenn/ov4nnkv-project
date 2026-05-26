"""Unit-тесты для FollowUpClient."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

import sys
sys.path.insert(0, str(__file__).rsplit("tests", 1)[0] + "src")

from followup_client import (
    FollowUpClient,
    FollowUpAPIError,
    AuthenticationError,
    NetworkError,
)


@pytest.fixture
def client():
    """Создать тестовый клиент."""
    return FollowUpClient(
        email="test@example.com",
        password="testpassword",
        base_url="https://api.follow-up.tech"
    )


class TestLogin:
    """Тесты авторизации."""
    
    @pytest.mark.asyncio
    async def test_login_success(self, client):
        """Тест успешной авторизации."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tokenPair": {
                "access": {"token": "test_access_token", "expiresIn": 1234567890},
                "refresh": {"token": "test_refresh_token", "expiresIn": 1234567890},
            },
            "user": {"id": "user-123", "email": "test@example.com"}
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.login()
            
            assert result["tokenPair"]["access"]["token"] == "test_access_token"
            assert client._access_token == "test_access_token"
            mock_http_client.post.assert_called_once_with(
                "/api/login",
                json={"email": "test@example.com", "password": "testpassword"}
            )
    
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client):
        """Тест авторизации с неверными учётными данными."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(AuthenticationError) as exc_info:
                await client.login()
            
            assert exc_info.value.status_code == 401
            assert "Неверный email или пароль" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_login_network_timeout(self, client):
        """Тест обработки timeout при авторизации."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(NetworkError) as exc_info:
                await client.login()
            
            assert "время ожидания" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_login_connection_error(self, client):
        """Тест обработки ошибки подключения."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(NetworkError) as exc_info:
                await client.login()
            
            assert "подключиться" in str(exc_info.value).lower()


class TestRequest:
    """Тесты метода _request."""
    
    @pytest.mark.asyncio
    async def test_request_with_auth(self, client):
        """Тест запроса с авторизацией."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": "test"}'
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client._request("GET", "/api/test")
            
            assert result == {"data": "test"}
            mock_http_client.request.assert_called_once()
            call_kwargs = mock_http_client.request.call_args
            assert call_kwargs.kwargs["headers"]["authorization"] == "Bearer test_token"
    
    @pytest.mark.asyncio
    async def test_request_401_retry(self, client):
        """Тест повторной авторизации при 401."""
        client._access_token = "old_token"
        
        # Первый ответ - 401, второй - успех
        mock_response_401 = MagicMock()
        mock_response_401.status_code = 401
        
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.text = '{"data": "success"}'
        mock_response_ok.json.return_value = {"data": "success"}
        mock_response_ok.raise_for_status = MagicMock()
        
        mock_login_response = MagicMock()
        mock_login_response.status_code = 200
        mock_login_response.json.return_value = {
            "tokenPair": {"access": {"token": "new_token"}}
        }
        mock_login_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(
                side_effect=[mock_response_401, mock_response_ok]
            )
            mock_http_client.post = AsyncMock(return_value=mock_login_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client._request("GET", "/api/test")
            
            assert result == {"data": "success"}
            assert client._access_token == "new_token"
    
    @pytest.mark.asyncio
    async def test_request_404_error(self, client):
        """Тест обработки 404 ошибки."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(FollowUpAPIError) as exc_info:
                await client._request("GET", "/api/conference/unknown")
            
            assert exc_info.value.status_code == 404
            assert "не найден" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_request_500_error(self, client):
        """Тест обработки серверной ошибки."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(FollowUpAPIError) as exc_info:
                await client._request("GET", "/api/test")
            
            assert exc_info.value.status_code == 500


class TestContextManager:
    """Тесты context manager."""
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Тест использования как async context manager."""
        async with FollowUpClient(
            email="test@example.com",
            password="test"
        ) as client:
            assert isinstance(client, FollowUpClient)


class TestConstructor:
    """Тесты конструктора."""
    
    def test_create_with_email_password(self):
        """Тест создания клиента с email/password."""
        client = FollowUpClient(email="test@example.com", password="test")
        assert client.email == "test@example.com"
        assert client.password == "test"
        assert client._access_token is None
    
    def test_create_with_api_key(self):
        """Тест создания клиента с API-ключом."""
        client = FollowUpClient(api_key="test_token")
        assert client._access_token == "test_token"
        assert client.email is None
        assert client.password is None
    
    def test_create_without_credentials_raises_error(self):
        """Тест что создание без credentials вызывает ошибку."""
        with pytest.raises(ValueError) as exc_info:
            FollowUpClient()
        assert "api_key" in str(exc_info.value).lower() or "email" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_api_key_client_401_no_retry(self):
        """Тест что клиент с API-ключом не пытается переавторизоваться при 401."""
        client = FollowUpClient(api_key="invalid_token")
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(AuthenticationError) as exc_info:
                await client._request("GET", "/api/test")
            
            assert "API-ключ" in str(exc_info.value) or exc_info.value.status_code == 401


class TestJoinConference:
    """Тесты метода join_conference."""
    
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
            assert call_kwargs.kwargs["json"]["theme"] == "Тестовый созвон"
            assert call_kwargs.kwargs["json"]["source"] == "googleMeet"
            assert call_kwargs.kwargs["json"]["externalId"] == "abc-defg-hij"
    
    @pytest.mark.asyncio
    async def test_join_conference_zoom(self, client):
        """Тест определения платформы Zoom."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id": "conf-456"}'
        mock_response.json.return_value = {"id": "conf-456"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            await client.join_conference("https://zoom.us/j/123456789")
            
            call_kwargs = mock_http_client.request.call_args
            assert call_kwargs.kwargs["json"]["source"] == "zoom"
            assert call_kwargs.kwargs["json"]["externalId"] == "123456789"
    
    @pytest.mark.asyncio
    async def test_join_conference_telemost(self, client):
        """Тест определения платформы Яндекс Телемост."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id": "conf-789"}'
        mock_response.json.return_value = {"id": "conf-789"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            await client.join_conference("https://telemost.yandex.ru/j/123456")
            
            call_kwargs = mock_http_client.request.call_args
            assert call_kwargs.kwargs["json"]["source"] == "telemost"
            assert call_kwargs.kwargs["json"]["externalId"] == "123456"
    
    @pytest.mark.asyncio
    async def test_join_conference_teams(self, client):
        """Тест определения платформы MS Teams."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id": "conf-teams"}'
        mock_response.json.return_value = {"id": "conf-teams"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            await client.join_conference("https://teams.microsoft.com/l/meetup-join/xxx")
            
            call_kwargs = mock_http_client.request.call_args
            assert call_kwargs.kwargs["json"]["source"] == "msTeams"


class TestDetectPlatform:
    """Тесты определения платформы по URL."""
    
    def test_detect_google_meet(self, client):
        """Тест определения Google Meet."""
        assert client._detect_platform("https://meet.google.com/abc-defg-hij") == "googleMeet"
    
    def test_detect_zoom(self, client):
        """Тест определения Zoom."""
        assert client._detect_platform("https://zoom.us/j/123456789") == "zoom"
        assert client._detect_platform("https://us02web.zoom.us/j/123") == "zoom"
    
    def test_detect_teams(self, client):
        """Тест определения MS Teams."""
        assert client._detect_platform("https://teams.microsoft.com/l/meetup-join/xxx") == "msTeams"
        assert client._detect_platform("https://teams.live.com/meet/xxx") == "msTeams"
    
    def test_detect_telemost(self, client):
        """Тест определения Яндекс Телемост."""
        assert client._detect_platform("https://telemost.yandex.ru/j/123456") == "telemost"
    
    def test_detect_salutejazz(self, client):
        """Тест определения SaluteJazz."""
        assert client._detect_platform("https://salutejazz.ru/xxx") == "sbJazz"
        assert client._detect_platform("https://jazz.sber.ru/xxx") == "sbJazz"
    
    def test_detect_jitsi(self, client):
        """Тест определения Jitsi."""
        assert client._detect_platform("https://meet.jit.si/MyRoom") == "jitsiMeet"
    
    def test_detect_unknown(self, client):
        """Тест неизвестной платформы — fallback на googleMeet."""
        assert client._detect_platform("https://unknown-platform.com/meeting") == "googleMeet"


class TestExtractExternalId:
    """Тесты извлечения externalId из URL."""
    
    @pytest.fixture
    def client(self):
        """Создать тестовый клиент."""
        return FollowUpClient(email="test@example.com", password="test")
    
    def test_extract_google_meet_id(self, client):
        """Тест извлечения ID Google Meet."""
        external_id = client._extract_external_id(
            "https://meet.google.com/abc-defg-hij", "googleMeet"
        )
        assert external_id == "abc-defg-hij"
    
    def test_extract_zoom_id(self, client):
        """Тест извлечения ID Zoom."""
        external_id = client._extract_external_id(
            "https://zoom.us/j/123456789", "zoom"
        )
        assert external_id == "123456789"
    
    def test_extract_telemost_id(self, client):
        """Тест извлечения ID Телемост."""
        external_id = client._extract_external_id(
            "https://telemost.yandex.ru/j/12345678901234", "telemost"
        )
        assert external_id == "12345678901234"
    
    def test_extract_fallback(self, client):
        """Тест fallback извлечения ID."""
        external_id = client._extract_external_id(
            "https://unknown.com/meeting/room123", "googleMeet"
        )
        assert external_id == "room123"


class TestGetTranscription:
    """Тесты метода get_transcription."""
    
    @pytest.mark.asyncio
    async def test_get_transcription_success(self, client):
        """Тест успешного получения транскрипции."""
        client._access_token = "test_token"
        
        # Мок для информации о конференции
        mock_conf_response = MagicMock()
        mock_conf_response.status_code = 200
        mock_conf_response.text = '{"id": "conf-123", "theme": "Тестовая встреча", "startedAt": "2024-12-07T14:00:00", "duration": 2700, "participants": [{"name": "Иван"}, {"name": "Пётр"}], "status": "completed"}'
        mock_conf_response.json.return_value = {
            "id": "conf-123",
            "theme": "Тестовая встреча",
            "startedAt": "2024-12-07T14:00:00",
            "duration": 2700,
            "participants": [{"name": "Иван"}, {"name": "Пётр"}],
            "status": "completed"
        }
        mock_conf_response.raise_for_status = MagicMock()
        
        # Мок для транскрипции
        mock_trans_response = MagicMock()
        mock_trans_response.status_code = 200
        mock_trans_response.text = '{"text": "Привет, это тестовая транскрипция."}'
        mock_trans_response.json.return_value = {"text": "Привет, это тестовая транскрипция."}
        mock_trans_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(
                side_effect=[mock_conf_response, mock_trans_response]
            )
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_transcription("34faff15-20a3-4dee-b212-3c0a3604e239")
            
            assert "conference_info" in result
            assert "transcription" in result
            assert result["conference_info"]["theme"] == "Тестовая встреча"
            assert result["transcription"]["text"] == "Привет, это тестовая транскрипция."
    
    @pytest.mark.asyncio
    async def test_get_transcription_not_found(self, client):
        """Тест когда созвон не найден."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(FollowUpAPIError) as exc_info:
                await client.get_transcription("nonexistent-id")
            
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_transcription_not_ready(self, client):
        """Тест когда транскрипция ещё не готова."""
        client._access_token = "test_token"
        
        # Конференция найдена
        mock_conf_response = MagicMock()
        mock_conf_response.status_code = 200
        mock_conf_response.text = '{"id": "conf-123", "status": "processing"}'
        mock_conf_response.json.return_value = {"id": "conf-123", "status": "processing"}
        mock_conf_response.raise_for_status = MagicMock()
        
        # Транскрипция не готова (400)
        mock_trans_response = MagicMock()
        mock_trans_response.status_code = 400
        mock_trans_response.text = '{"message": "Transcription not ready"}'
        mock_trans_response.json.return_value = {"message": "Transcription not ready"}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(
                side_effect=[mock_conf_response, mock_trans_response]
            )
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(FollowUpAPIError) as exc_info:
                await client.get_transcription("conf-123")
            
            assert exc_info.value.status_code == 400


class TestGetConferenceInfo:
    """Тесты метода get_conference_info."""
    
    @pytest.mark.asyncio
    async def test_get_conference_info_success(self, client):
        """Тест успешного получения информации о конференции."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id": "conf-123", ...}'
        mock_response.json.return_value = {
            "id": "conf-123",
            "theme": "Тестовая встреча",
            "startedAt": "2024-12-07T14:00:00",
            "duration": 2700,  # 45 минут в секундах
            "participants": [{"name": "Иван"}, {"name": "Пётр"}],
            "status": "ready"
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_conference_info("34faff15-20a3-4dee-b212-3c0a3604e239")
            
            assert result["id"] == "conf-123"
            assert result["theme"] == "Тестовая встреча"
            assert result["status"] == "ready"
            mock_http_client.request.assert_called_once()
            call_kwargs = mock_http_client.request.call_args
            assert "/api/conference/34faff15-20a3-4dee-b212-3c0a3604e239" in call_kwargs.kwargs["url"]
    
    @pytest.mark.asyncio
    async def test_get_conference_info_not_found(self, client):
        """Тест когда созвон не найден."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(FollowUpAPIError) as exc_info:
                await client.get_conference_info("nonexistent-id")
            
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_conference_info_with_hasTranscription_field(self, client):
        """Тест когда API возвращает поле hasTranscription."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id": "conf-123", ...}'
        mock_response.json.return_value = {
            "id": "conf-123",
            "theme": "Встреча с транскрипцией",
            "status": "processing",
            "hasTranscription": True
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_conference_info("conf-123")
            
            assert result["hasTranscription"] is True


class TestListConferences:
    """Тесты метода list_conferences."""
    
    @pytest.mark.asyncio
    async def test_list_conferences_success(self, client):
        """Тест успешного получения списка созвонов."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"page": [...], "summary": {"elements": 2}}'
        mock_response.json.return_value = {
            "page": [
                {"id": "conf-1", "theme": "Встреча 1", "date": "2024-12-07T10:00:00", "duration": 1800, "status": "ready"},
                {"id": "conf-2", "theme": "Встреча 2", "date": "2024-12-07T14:00:00", "duration": 3600, "status": "ready"}
            ],
            "summary": {"pages": 1, "elements": 2}
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.list_conferences(limit=20, offset=0)
            
            assert result["total"] == 2
            assert len(result["conferences"]) == 2
            assert result["conferences"][0]["id"] == "conf-1"
            mock_http_client.request.assert_called_once()
            call_kwargs = mock_http_client.request.call_args
            # Проверяем что используется POST и правильный эндпоинт
            assert call_kwargs.kwargs["method"] == "POST"
            assert "/api/conference/listing/history" in call_kwargs.kwargs["url"]
    
    @pytest.mark.asyncio
    async def test_list_conferences_with_pagination(self, client):
        """Тест пагинации списка созвонов."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"page": [...], "summary": {"elements": 50}}'
        mock_response.json.return_value = {
            "page": [{"id": "conf-3", "theme": "Встреча 3"}],
            "summary": {"pages": 5, "elements": 50}
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.list_conferences(limit=10, offset=20)
            
            assert result["total"] == 50
            call_kwargs = mock_http_client.request.call_args
            # Проверяем что передаётся правильный JSON с пагинацией
            assert call_kwargs.kwargs["json"]["paging"]["size"] == 10
            assert call_kwargs.kwargs["json"]["paging"]["current"] == 3  # offset=20, limit=10 -> page 3
    
    @pytest.mark.asyncio
    async def test_list_conferences_empty(self, client):
        """Тест пустого списка созвонов."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [], "total": 0}'
        mock_response.json.return_value = {"data": [], "total": 0}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.list_conferences()
            
            assert result["total"] == 0
            assert result["conferences"] == []
    
    @pytest.mark.asyncio
    async def test_list_conferences_list_response(self, client):
        """Тест когда API возвращает список напрямую (без обёртки)."""
        client._access_token = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '[{"id": "conf-1"}, {"id": "conf-2"}]'
        mock_response.json.return_value = [
            {"id": "conf-1", "theme": "Встреча 1"},
            {"id": "conf-2", "theme": "Встреча 2"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.list_conferences()
            
            assert result["total"] == 2
            assert len(result["conferences"]) == 2
    
    @pytest.mark.asyncio
    async def test_list_conferences_auth_error(self, client):
        """Тест ошибки авторизации при получении списка."""
        client._access_token = "invalid_token"
        client.email = None  # Отключаем retry
        client.password = None
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(AuthenticationError):
                await client.list_conferences()


class TestDownloadPdf:
    """Тесты метода download_pdf."""
    
    @pytest.mark.asyncio
    async def test_download_pdf_success(self, client):
        """Тест успешного скачивания PDF."""
        # Мок для CSRF
        mock_csrf_response = MagicMock()
        mock_csrf_response.status_code = 200
        mock_csrf_response.json.return_value = {"csrfToken": "test_csrf_token"}
        
        # Мок для login
        mock_login_response = MagicMock()
        mock_login_response.status_code = 200
        
        # Мок для session
        mock_session_response = MagicMock()
        mock_session_response.status_code = 200
        mock_session_response.json.return_value = {"user": {"email": "test@example.com"}}
        
        # Мок для PDF
        mock_pdf_response = MagicMock()
        mock_pdf_response.status_code = 200
        mock_pdf_response.content = b'%PDF-1.4 test pdf content'
        mock_pdf_response.headers = {"content-type": "application/pdf"}
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(side_effect=[
                mock_csrf_response,
                mock_session_response,
                mock_pdf_response
            ])
            mock_http_client.post = AsyncMock(return_value=mock_login_response)
            mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_http_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_http_client
            
            result = await client.download_pdf("34faff15-20a3-4dee-b212-3c0a3604e239")
            
            assert result == b'%PDF-1.4 test pdf content'
    
    @pytest.mark.asyncio
    async def test_download_pdf_requires_credentials(self):
        """Тест что для скачивания PDF нужны email/password."""
        client = FollowUpClient(api_key="test_api_key")
        
        with pytest.raises(AuthenticationError) as exc_info:
            await client.download_pdf("34faff15-20a3-4dee-b212-3c0a3604e239")
        
        assert "email и password" in str(exc_info.value.message)
    
    @pytest.mark.asyncio
    async def test_download_pdf_auth_failure(self, client):
        """Тест ошибки авторизации при скачивании PDF."""
        # Мок для CSRF
        mock_csrf_response = MagicMock()
        mock_csrf_response.status_code = 200
        mock_csrf_response.json.return_value = {"csrfToken": "test_csrf_token"}
        
        # Мок для login - неудача
        mock_login_response = MagicMock()
        mock_login_response.status_code = 401
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_csrf_response)
            mock_http_client.post = AsyncMock(return_value=mock_login_response)
            mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_http_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_http_client
            
            with pytest.raises(AuthenticationError):
                await client.download_pdf("34faff15-20a3-4dee-b212-3c0a3604e239")
    
    @pytest.mark.asyncio
    async def test_download_pdf_not_pdf_response(self, client):
        """Тест когда ответ не является PDF."""
        # Мок для CSRF
        mock_csrf_response = MagicMock()
        mock_csrf_response.status_code = 200
        mock_csrf_response.json.return_value = {"csrfToken": "test_csrf_token"}
        
        # Мок для login
        mock_login_response = MagicMock()
        mock_login_response.status_code = 200
        
        # Мок для session
        mock_session_response = MagicMock()
        mock_session_response.status_code = 200
        mock_session_response.json.return_value = {"user": {"email": "test@example.com"}}
        
        # Мок для PDF - но возвращает HTML
        mock_pdf_response = MagicMock()
        mock_pdf_response.status_code = 200
        mock_pdf_response.content = b'<!DOCTYPE html><html>'
        mock_pdf_response.headers = {"content-type": "text/html"}
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(side_effect=[
                mock_csrf_response,
                mock_session_response,
                mock_pdf_response
            ])
            mock_http_client.post = AsyncMock(return_value=mock_login_response)
            mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_http_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_http_client
            
            with pytest.raises(FollowUpAPIError) as exc_info:
                await client.download_pdf("34faff15-20a3-4dee-b212-3c0a3604e239")
            
            assert "не является PDF" in str(exc_info.value.message)
