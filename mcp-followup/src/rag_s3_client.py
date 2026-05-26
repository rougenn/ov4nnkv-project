"""S3 клиент для загрузки транскрипций в RAG.

Использует boto3-совместимый интерфейс для работы с любым S3-совместимым endpoint.
"""

import logging
import os
from datetime import datetime
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger("rag_s3_client")


class RAGS3Error(Exception):
    """Базовое исключение для ошибок S3 RAG."""
    
    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class RAGS3Client:
    """Клиент для работы с S3-совместимым хранилищем для транскрипций.
    
    Attributes:
        endpoint: S3 endpoint URL
        region: AWS/S3 регион
        bucket: Имя бакета
        _client: boto3 S3 клиент
    """
    
    def __init__(
        self,
        endpoint: str | None = None,
        region: str | None = None,
        bucket: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        """Инициализация S3 клиента.
        
        Args:
            endpoint: S3 endpoint URL (по умолчанию из CLOUD_RAG_S3_ENDPOINT)
            region: S3 регион (по умолчанию из CLOUD_RAG_S3_REGION)
            bucket: Имя бакета (по умолчанию из CLOUD_RAG_S3_BUCKET)
            access_key: Access key (по умолчанию из CLOUD_RAG_S3_ACCESS_KEY)
            secret_key: Secret key (по умолчанию из CLOUD_RAG_S3_SECRET_KEY)
        """
        self.endpoint = endpoint or os.environ.get("CLOUD_RAG_S3_ENDPOINT")
        self.region = region or os.environ.get("CLOUD_RAG_S3_REGION", "ru-central-1")
        self.bucket = bucket or os.environ.get("CLOUD_RAG_S3_BUCKET")
        self._access_key = access_key or os.environ.get("CLOUD_RAG_S3_ACCESS_KEY")
        self._secret_key = secret_key or os.environ.get("CLOUD_RAG_S3_SECRET_KEY")
        
        self._client = None
        
        if not self.endpoint:
            logger.warning("S3 endpoint не настроен (CLOUD_RAG_S3_ENDPOINT)")
        if not self.bucket:
            logger.warning("S3 bucket не настроен (CLOUD_RAG_S3_BUCKET)")
        if not self._access_key or not self._secret_key:
            logger.warning("S3 credentials не настроены (CLOUD_RAG_S3_ACCESS_KEY, CLOUD_RAG_S3_SECRET_KEY)")
    
    def _get_client(self):
        """Получить или создать S3 клиент."""
        if self._client is None:
            if not self._access_key or not self._secret_key:
                raise RAGS3Error(
                    "S3 credentials не настроены",
                    details={"missing": "CLOUD_RAG_S3_ACCESS_KEY или CLOUD_RAG_S3_SECRET_KEY"}
                )
            
            config = Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'},
                retries={'max_attempts': 3, 'mode': 'standard'}
            )
            
            self._client = boto3.client(
                's3',
                endpoint_url=self.endpoint,
                region_name=self.region,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                config=config
            )
            
            logger.info(f"S3 клиент инициализирован для {self.endpoint}")
        
        return self._client
    
    def upload_document(
        self,
        key: str,
        content: str,
        content_type: str = "text/markdown",
        metadata: dict | None = None
    ) -> dict:
        """Загрузить документ в S3 бакет.
        
        Args:
            key: Ключ объекта (путь в бакете, например conferences/uuid.md)
            content: Содержимое документа
            content_type: MIME-тип (по умолчанию text/markdown)
            metadata: Дополнительные метаданные объекта
            
        Returns:
            dict: Результат загрузки с информацией об объекте
            
        Raises:
            RAGS3Error: Ошибка загрузки
        """
        if not self.bucket:
            raise RAGS3Error("S3 bucket не настроен")
        
        try:
            client = self._get_client()
            
            # Подготовка метаданных
            s3_metadata = metadata or {}
            s3_metadata["uploaded_at"] = datetime.utcnow().isoformat()
            
            # Загрузка
            response = client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content.encode('utf-8'),
                ContentType=content_type,
                Metadata={k: str(v) for k, v in s3_metadata.items()}
            )
            
            logger.info(f"Документ загружен в S3: s3://{self.bucket}/{key}")
            
            return {
                "success": True,
                "bucket": self.bucket,
                "key": key,
                "etag": response.get("ETag", "").strip('"'),
                "version_id": response.get("VersionId"),
            }
            
        except NoCredentialsError as e:
            logger.error(f"S3 credentials error: {e}")
            raise RAGS3Error(
                "Неверные S3 credentials",
                details={"error": str(e)}
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"S3 ClientError: {error_code} - {error_message}")
            raise RAGS3Error(
                f"Ошибка S3: {error_message}",
                details={"code": error_code, "error": str(e)}
            )
        except Exception as e:
            logger.error(f"Unexpected S3 error: {e}")
            raise RAGS3Error(
                f"Неожиданная ошибка S3: {str(e)}",
                details={"error": str(e)}
            )
    
    def get_document(self, key: str) -> dict:
        """Получить документ из S3 бакета.
        
        Args:
            key: Ключ объекта
            
        Returns:
            dict: Содержимое и метаданные документа
            
        Raises:
            RAGS3Error: Ошибка получения
        """
        if not self.bucket:
            raise RAGS3Error("S3 bucket не настроен")
        
        try:
            client = self._get_client()
            
            response = client.get_object(
                Bucket=self.bucket,
                Key=key
            )
            
            content = response["Body"].read().decode('utf-8')
            
            return {
                "success": True,
                "content": content,
                "content_type": response.get("ContentType"),
                "metadata": response.get("Metadata", {}),
                "last_modified": response.get("LastModified"),
            }
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                raise RAGS3Error(
                    f"Документ не найден: {key}",
                    details={"code": "NOT_FOUND", "key": key}
                )
            raise RAGS3Error(
                f"Ошибка S3: {e.response.get('Error', {}).get('Message', str(e))}",
                details={"code": error_code, "error": str(e)}
            )
    
    def list_documents(self, prefix: str = "conferences/", max_keys: int = 100) -> dict:
        """Получить список документов в бакете.
        
        Args:
            prefix: Префикс для фильтрации (по умолчанию conferences/)
            max_keys: Максимальное количество объектов
            
        Returns:
            dict: Список объектов
            
        Raises:
            RAGS3Error: Ошибка получения списка
        """
        if not self.bucket:
            raise RAGS3Error("S3 bucket не настроен")
        
        try:
            client = self._get_client()
            
            response = client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            objects = []
            for obj in response.get("Contents", []):
                objects.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                })
            
            return {
                "success": True,
                "count": len(objects),
                "objects": objects,
                "is_truncated": response.get("IsTruncated", False),
            }
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise RAGS3Error(
                f"Ошибка S3: {e.response.get('Error', {}).get('Message', str(e))}",
                details={"code": error_code, "error": str(e)}
            )
    
    def delete_document(self, key: str) -> dict:
        """Удалить документ из S3 бакета.
        
        Args:
            key: Ключ объекта
            
        Returns:
            dict: Результат удаления
            
        Raises:
            RAGS3Error: Ошибка удаления
        """
        if not self.bucket:
            raise RAGS3Error("S3 bucket не настроен")
        
        try:
            client = self._get_client()
            
            response = client.delete_object(
                Bucket=self.bucket,
                Key=key
            )
            
            logger.info(f"Документ удалён из S3: s3://{self.bucket}/{key}")
            
            return {
                "success": True,
                "key": key,
                "version_id": response.get("VersionId"),
            }
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise RAGS3Error(
                f"Ошибка S3: {e.response.get('Error', {}).get('Message', str(e))}",
                details={"code": error_code, "error": str(e)}
            )


def format_transcription_document(
    conference_id: str,
    title: str,
    date: str | None,
    participants: list[str],
    duration_minutes: int | None,
    transcription_text: str,
) -> str:
    """Форматировать транскрипцию в markdown документ для RAG.
    
    Args:
        conference_id: ID конференции
        title: Название встречи
        date: Дата проведения (ISO формат)
        participants: Список участников
        duration_minutes: Длительность в минутах
        transcription_text: Текст транскрипции
        
    Returns:
        str: Markdown документ
    """
    # Форматируем дату
    date_str = "Не указана"
    if date:
        try:
            dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except (ValueError, AttributeError):
            date_str = str(date)
    
    # Форматируем участников
    participants_str = ", ".join(participants) if participants else "Не указаны"
    
    # Форматируем длительность
    duration_str = f"{duration_minutes} мин" if duration_minutes else "Не указана"
    
    # Собираем документ
    document = f"""# Встреча: {title}

**ID конференции:** {conference_id}
**Дата:** {date_str}
**Участники:** {participants_str}
**Длительность:** {duration_str}

---

## Транскрипция

{transcription_text}
"""
    
    return document




