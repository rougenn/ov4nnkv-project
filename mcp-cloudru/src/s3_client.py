"""S3 клиент для работы с Cloud.ru Object Storage.

Использует boto3 с форматом tenant_id:key_id для авторизации.
"""

import logging
import os
import time
from datetime import datetime
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
import requests

logger = logging.getLogger("cloudru-s3")


class CloudRuS3Error(Exception):
    """Исключение для ошибок S3 Cloud.ru."""
    
    def __init__(self, message: str, code: str = "S3_ERROR", details: dict | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class CloudRuS3Client:
    """Клиент для работы с S3 Cloud.ru.
    
    Поддерживает:
    - Загрузка файлов
    - Скачивание файлов
    - Список объектов
    - Удаление объектов
    """
    
    def __init__(
        self,
        tenant_id: str | None = None,
        key_id: str | None = None,
        key_secret: str | None = None,
        bucket: str | None = None,
        endpoint: str = "https://s3.cloud.ru",
        region: str = "ru-central-1",
    ):
        """Инициализация клиента.
        
        Args:
            tenant_id: Tenant ID Cloud.ru
            key_id: Key ID для авторизации
            key_secret: Secret Key для авторизации
            bucket: Имя бакета по умолчанию
            endpoint: S3 endpoint URL
            region: Регион S3
        """
        self.tenant_id = tenant_id or os.environ.get("CLOUD_TENANT_ID")
        self.key_id = key_id or os.environ.get("CLOUD_KEY_ID")
        self.key_secret = key_secret or os.environ.get("CLOUD_SECRET")
        self.bucket = bucket or os.environ.get("S3_BUCKET")
        self.endpoint = endpoint or os.environ.get("S3_ENDPOINT", "https://s3.cloud.ru")
        self.region = region or os.environ.get("S3_REGION", "ru-central-1")
        
        self._client = None
        
        if not self.tenant_id or not self.key_id or not self.key_secret:
            logger.warning("S3 credentials не полностью настроены")
    
    def _get_client(self):
        """Получить или создать S3 клиент."""
        if self._client is None:
            if not self.tenant_id or not self.key_id or not self.key_secret:
                raise CloudRuS3Error(
                    "S3 credentials не настроены. Установите CLOUD_TENANT_ID, CLOUD_KEY_ID, CLOUD_SECRET",
                    code="CREDENTIALS_MISSING"
                )
            
            # Формат access_key: tenant_id:key_id
            access_key = f"{self.tenant_id}:{self.key_id}"
            
            config = Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'},
                retries={'max_attempts': 3, 'mode': 'standard'}
            )
            
            self._client = boto3.client(
                's3',
                endpoint_url=self.endpoint,
                region_name=self.region,
                aws_access_key_id=access_key,
                aws_secret_access_key=self.key_secret,
                config=config
            )
            
            logger.info(f"S3 клиент инициализирован для {self.endpoint}")
        
        return self._client
    
    def list_buckets(self) -> list[dict]:
        """Получить список бакетов."""
        try:
            client = self._get_client()
            response = client.list_buckets()
            
            return [
                {
                    "name": b["Name"],
                    "creation_date": b["CreationDate"].isoformat() if b.get("CreationDate") else None
                }
                for b in response.get("Buckets", [])
            ]
        except ClientError as e:
            raise CloudRuS3Error(f"Ошибка получения списка бакетов: {e}", code="LIST_BUCKETS_ERROR")
    
    def list_objects(
        self, 
        bucket: str | None = None, 
        prefix: str = "", 
        max_keys: int = 100
    ) -> dict:
        """Получить список объектов в бакете.
        
        Args:
            bucket: Имя бакета (или используется default)
            prefix: Префикс для фильтрации
            max_keys: Максимальное количество объектов
            
        Returns:
            dict с objects и is_truncated
        """
        bucket = bucket or self.bucket
        if not bucket:
            raise CloudRuS3Error("Бакет не указан", code="NO_BUCKET")
        
        try:
            client = self._get_client()
            response = client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            objects = []
            for obj in response.get("Contents", []):
                objects.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                    "etag": obj.get("ETag", "").strip('"'),
                })
            
            return {
                "bucket": bucket,
                "prefix": prefix,
                "objects": objects,
                "count": len(objects),
                "is_truncated": response.get("IsTruncated", False),
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise CloudRuS3Error(
                f"Ошибка получения списка объектов: {e}",
                code=error_code,
                details={"bucket": bucket, "prefix": prefix}
            )
    
    def upload_file(
        self,
        key: str,
        content: bytes | str | BinaryIO,
        bucket: str | None = None,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> dict:
        """Загрузить файл в бакет.
        
        Args:
            key: Ключ объекта (путь в бакете)
            content: Содержимое файла
            bucket: Имя бакета
            content_type: MIME тип
            metadata: Дополнительные метаданные
            
        Returns:
            dict с информацией о загруженном объекте
        """
        bucket = bucket or self.bucket
        if not bucket:
            raise CloudRuS3Error("Бакет не указан", code="NO_BUCKET")
        
        try:
            client = self._get_client()
            
            # Подготовка содержимого
            if isinstance(content, str):
                body = content.encode('utf-8')
            elif hasattr(content, 'read'):
                body = content.read()
            else:
                body = content
            
            # Загрузка без кастомных метаданных (Cloud.ru требует их подписи)
            response = client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
            
            logger.info(f"Файл загружен: s3://{bucket}/{key}")
            
            return {
                "success": True,
                "bucket": bucket,
                "key": key,
                "etag": response.get("ETag", "").strip('"'),
                "size": len(body),
                "content_type": content_type,
                "url": f"{self.endpoint}/{bucket}/{key}",
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise CloudRuS3Error(
                f"Ошибка загрузки файла: {e}",
                code=error_code,
                details={"bucket": bucket, "key": key}
            )
    
    def download_file(self, key: str, bucket: str | None = None) -> dict:
        """Скачать файл из бакета.
        
        Args:
            key: Ключ объекта
            bucket: Имя бакета
            
        Returns:
            dict с content и metadata
        """
        bucket = bucket or self.bucket
        if not bucket:
            raise CloudRuS3Error("Бакет не указан", code="NO_BUCKET")
        
        try:
            client = self._get_client()
            response = client.get_object(Bucket=bucket, Key=key)
            
            content = response["Body"].read()
            
            return {
                "success": True,
                "bucket": bucket,
                "key": key,
                "content": content,
                "content_type": response.get("ContentType"),
                "size": response.get("ContentLength"),
                "last_modified": response["LastModified"].isoformat() if response.get("LastModified") else None,
                "metadata": response.get("Metadata", {}),
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                raise CloudRuS3Error(
                    f"Объект не найден: {key}",
                    code="NOT_FOUND",
                    details={"bucket": bucket, "key": key}
                )
            raise CloudRuS3Error(
                f"Ошибка скачивания файла: {e}",
                code=error_code,
                details={"bucket": bucket, "key": key}
            )
    
    def delete_file(self, key: str, bucket: str | None = None) -> dict:
        """Удалить файл из бакета.
        
        Args:
            key: Ключ объекта
            bucket: Имя бакета
            
        Returns:
            dict с результатом
        """
        bucket = bucket or self.bucket
        if not bucket:
            raise CloudRuS3Error("Бакет не указан", code="NO_BUCKET")
        
        try:
            client = self._get_client()
            response = client.delete_object(Bucket=bucket, Key=key)
            
            logger.info(f"Файл удалён: s3://{bucket}/{key}")
            
            return {
                "success": True,
                "bucket": bucket,
                "key": key,
                "version_id": response.get("VersionId"),
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise CloudRuS3Error(
                f"Ошибка удаления файла: {e}",
                code=error_code,
                details={"bucket": bucket, "key": key}
            )
    
    def file_exists(self, key: str, bucket: str | None = None) -> bool:
        """Проверить существование файла."""
        bucket = bucket or self.bucket
        if not bucket:
            return False
        
        try:
            client = self._get_client()
            client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False





