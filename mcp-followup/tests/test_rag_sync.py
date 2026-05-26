"""Тесты для sync_conference_to_rag и S3 клиента."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Импортируем тестируемые модули
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from rag_s3_client import (
    RAGS3Client,
    RAGS3Error,
    format_transcription_document,
)


class TestFormatTranscriptionDocument:
    """Тесты форматирования документа для RAG."""
    
    def test_format_basic_document(self):
        """Тест базового форматирования документа."""
        result = format_transcription_document(
            conference_id="test-uuid-1234",
            title="Тестовая встреча",
            date="2024-12-10T14:00:00",
            participants=["Иван", "Пётр"],
            duration_minutes=30,
            transcription_text="Иван: Привет!\nПётр: Привет, как дела?"
        )
        
        assert "# Встреча: Тестовая встреча" in result
        assert "**ID конференции:** test-uuid-1234" in result
        assert "**Дата:** 10.12.2024 14:00" in result
        assert "**Участники:** Иван, Пётр" in result
        assert "**Длительность:** 30 мин" in result
        assert "## Транскрипция" in result
        assert "Иван: Привет!" in result
        assert "Пётр: Привет, как дела?" in result
    
    def test_format_document_without_participants(self):
        """Тест документа без участников."""
        result = format_transcription_document(
            conference_id="test-uuid",
            title="Встреча",
            date=None,
            participants=[],
            duration_minutes=None,
            transcription_text="Текст транскрипции"
        )
        
        assert "**Участники:** Не указаны" in result
        assert "**Длительность:** Не указана" in result
        assert "**Дата:** Не указана" in result
    
    def test_format_document_with_iso_date(self):
        """Тест корректного парсинга ISO даты."""
        result = format_transcription_document(
            conference_id="id",
            title="Test",
            date="2024-12-10T09:30:00Z",
            participants=["User"],
            duration_minutes=60,
            transcription_text="Text"
        )
        
        # Проверяем что дата распарсилась
        assert "10.12.2024" in result


class TestRAGS3Client:
    """Тесты S3 клиента."""
    
    def test_init_with_env_vars(self, monkeypatch):
        """Тест инициализации с переменными окружения."""
        monkeypatch.setenv("CLOUD_RAG_S3_ENDPOINT", "https://test-s3.example.com")
        monkeypatch.setenv("CLOUD_RAG_S3_REGION", "test-region")
        monkeypatch.setenv("CLOUD_RAG_S3_BUCKET", "test-bucket")
        monkeypatch.setenv("CLOUD_RAG_S3_ACCESS_KEY", "test-access-key")
        monkeypatch.setenv("CLOUD_RAG_S3_SECRET_KEY", "test-secret-key")
        
        client = RAGS3Client()
        
        assert client.endpoint == "https://test-s3.example.com"
        assert client.region == "test-region"
        assert client.bucket == "test-bucket"
    
    def test_init_with_params(self):
        """Тест инициализации с параметрами."""
        client = RAGS3Client(
            endpoint="https://custom-s3.com",
            region="custom-region",
            bucket="custom-bucket",
            access_key="key",
            secret_key="secret"
        )
        
        assert client.endpoint == "https://custom-s3.com"
        assert client.region == "custom-region"
        assert client.bucket == "custom-bucket"
    
    def test_upload_document_no_bucket(self):
        """Тест ошибки при отсутствии бакета."""
        client = RAGS3Client(
            endpoint="https://s3.example.com",
            bucket=None,
            access_key="key",
            secret_key="secret"
        )
        
        with pytest.raises(RAGS3Error) as exc_info:
            client.upload_document("key", "content")
        
        assert "bucket не настроен" in str(exc_info.value.message)
    
    def test_upload_document_no_credentials(self):
        """Тест ошибки при отсутствии credentials."""
        client = RAGS3Client(
            endpoint="https://s3.example.com",
            bucket="test-bucket",
            access_key=None,
            secret_key=None
        )
        
        with pytest.raises(RAGS3Error) as exc_info:
            client.upload_document("key", "content")
        
        assert "credentials не настроены" in str(exc_info.value.message)
    
    @patch('rag_s3_client.boto3.client')
    def test_upload_document_success(self, mock_boto_client):
        """Тест успешной загрузки документа."""
        # Мок S3 клиента
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {
            "ETag": '"abc123"',
            "VersionId": "v1"
        }
        mock_boto_client.return_value = mock_s3
        
        client = RAGS3Client(
            endpoint="https://s3.example.com",
            region="test-region",
            bucket="test-bucket",
            access_key="key",
            secret_key="secret"
        )
        
        result = client.upload_document(
            key="conferences/test.md",
            content="# Test content",
            content_type="text/markdown"
        )
        
        assert result["success"] is True
        assert result["bucket"] == "test-bucket"
        assert result["key"] == "conferences/test.md"
        assert result["etag"] == "abc123"
        
        # Проверяем вызов put_object
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "conferences/test.md"
        assert call_kwargs["ContentType"] == "text/markdown"
    
    @patch('rag_s3_client.boto3.client')
    def test_get_document_success(self, mock_boto_client):
        """Тест успешного получения документа."""
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"# Test content"
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "text/markdown",
            "Metadata": {"key": "value"}
        }
        mock_boto_client.return_value = mock_s3
        
        client = RAGS3Client(
            endpoint="https://s3.example.com",
            bucket="test-bucket",
            access_key="key",
            secret_key="secret"
        )
        
        result = client.get_document("conferences/test.md")
        
        assert result["success"] is True
        assert result["content"] == "# Test content"
        assert result["content_type"] == "text/markdown"
    
    @patch('rag_s3_client.boto3.client')
    def test_list_documents_success(self, mock_boto_client):
        """Тест успешного получения списка документов."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "conferences/1.md", "Size": 100, "LastModified": None},
                {"Key": "conferences/2.md", "Size": 200, "LastModified": None},
            ],
            "IsTruncated": False
        }
        mock_boto_client.return_value = mock_s3
        
        client = RAGS3Client(
            endpoint="https://s3.example.com",
            bucket="test-bucket",
            access_key="key",
            secret_key="secret"
        )
        
        result = client.list_documents(prefix="conferences/")
        
        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["objects"]) == 2


class TestSyncConferenceToRAG:
    """Тесты для sync_conference_to_rag tool."""
    
    @pytest.mark.asyncio
    async def test_sync_invalid_conference_id(self):
        """Тест валидации некорректного conference_id."""
        from server import sync_conference_to_rag
        
        # Пустой ID
        result = await sync_conference_to_rag("")
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ID"
        
        # Невалидный формат
        result = await sync_conference_to_rag("not-a-uuid")
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ID"
    
    @pytest.mark.asyncio
    @patch('server._get_client')
    @patch('server._get_s3_client')
    async def test_sync_success(self, mock_s3_client, mock_followup_client):
        """Тест успешной синхронизации."""
        from server import sync_conference_to_rag
        
        # Мок Follow-Up клиента
        mock_client_instance = AsyncMock()
        mock_client_instance.get_transcription.return_value = {
            "conference_info": {
                "theme": "Тестовая встреча",
                "startedAt": "2024-12-10T14:00:00",
                "participants": [{"name": "Иван"}],
                "duration": 1800,  # 30 минут в секундах
            },
            "transcription": {
                "text": "Тестовая транскрипция"
            }
        }
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock()
        mock_followup_client.return_value = mock_client_instance
        
        # Мок S3 клиента
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload_document.return_value = {
            "success": True,
            "bucket": "test-bucket",
            "key": "conferences/test-uuid.md",
            "etag": "abc"
        }
        mock_s3_client.return_value = mock_s3_instance
        
        result = await sync_conference_to_rag("12345678-1234-1234-1234-123456789abc")
        
        assert result["success"] is True
        assert result["conference_id"] == "12345678-1234-1234-1234-123456789abc"
        assert "s3_key" in result
        assert result["title"] == "Тестовая встреча"
    
    @pytest.mark.asyncio
    @patch('server._get_client')
    async def test_sync_no_transcription(self, mock_followup_client):
        """Тест когда транскрипция пуста."""
        from server import sync_conference_to_rag
        
        mock_client_instance = AsyncMock()
        mock_client_instance.get_transcription.return_value = {
            "conference_info": {"theme": "Test"},
            "transcription": {"text": ""}  # Пустая транскрипция
        }
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock()
        mock_followup_client.return_value = mock_client_instance
        
        result = await sync_conference_to_rag("12345678-1234-1234-1234-123456789abc")
        
        assert result["success"] is False
        assert result["error"]["code"] == "NO_TRANSCRIPTION"




