"""RAG клиент для работы с Cloud.ru Managed RAG.

Использует Bearer токен для авторизации.
"""

import logging
import os
import time
import requests

logger = logging.getLogger("cloudru-rag")


class CloudRuRAGError(Exception):
    """Исключение для ошибок RAG Cloud.ru."""
    
    def __init__(self, message: str, code: str = "RAG_ERROR", details: dict | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class CloudRuRAGClient:
    """Клиент для работы с Managed RAG Cloud.ru.
    
    Поддерживает:
    - Поиск по базе знаний (retrieve)
    - Поиск с ререйнкингом
    - Запуск индексации (создание новой версии)
    """
    
    # Кэш токена
    _token_cache = {"token": None, "expires_at": 0}
    _indexing_token_cache = {"token": None, "expires_at": 0}
    
    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        rag_public_url: str | None = None,
        rag_version_id: str | None = None,
    ):
        """Инициализация клиента.
        
        Args:
            key_id: Key ID для получения токена
            key_secret: Secret Key для получения токена
            rag_public_url: Публичный URL базы знаний
            rag_version_id: ID версии базы знаний
        """
        self.key_id = key_id or os.environ.get("CLOUD_KEY_ID")
        self.key_secret = key_secret or os.environ.get("CLOUD_SECRET")
        self.rag_public_url = rag_public_url or os.environ.get("RAG_PUBLIC_URL")
        self.rag_version_id = rag_version_id or os.environ.get("RAG_VERSION_ID")
        
        # Credentials для индексации (могут отличаться от основных)
        self.indexing_key_id = os.environ.get("RAG_INDEXING_KEY_ID", "4461381aeb626292a774dc49a801636d")
        self.indexing_key_secret = os.environ.get("RAG_INDEXING_SECRET", "56cc75128e021e92a00c8c24a0c69ddd")
        
        # RAG конфигурация для индексации
        self.rag_id = os.environ.get("RAG_ID", "01598759-a542-4e4b-b7b8-7483d1b92779")
        self.project_id = os.environ.get("PROJECT_ID", "edf84599-c596-4f70-a2d9-20798a7472ed")
        self.product_instance_id = os.environ.get("PRODUCT_INSTANCE_ID", "c79b24f4-5cb3-4542-9539-512de9877b85")
        self.s3_bucket_id = os.environ.get("S3_BUCKET_ID", "a16153d2-16d4-4b36-a560-80c647e88c76")
        self.s3_bucket = os.environ.get("S3_BUCKET", "meeting-assistant-rag")
        
        if not self.rag_public_url:
            logger.warning("RAG_PUBLIC_URL не настроен")
        if not self.rag_version_id:
            logger.warning("RAG_VERSION_ID не настроен")
    
    def _get_token(self, force_refresh: bool = False) -> str:
        """Получить IAM токен с автообновлением."""
        # Проверяем кэш (обновляем за 5 минут до истечения)
        if (not force_refresh and 
            self._token_cache["token"] and 
            self._token_cache["expires_at"] > time.time() + 300):
            return self._token_cache["token"]
        
        if not self.key_id or not self.key_secret:
            raise CloudRuRAGError(
                "IAM credentials не настроены. Установите CLOUD_KEY_ID и CLOUD_SECRET",
                code="CREDENTIALS_MISSING"
            )
        
        logger.info("Получаю IAM токен...")
        
        try:
            response = requests.post(
                "https://iam.api.cloud.ru/api/v1/auth/token",
                json={"keyId": self.key_id, "secret": self.key_secret},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self._token_cache["token"] = data["access_token"]
                self._token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
                logger.info(f"Токен получен (действителен {data.get('expires_in', 3600)} сек)")
                return self._token_cache["token"]
            else:
                raise CloudRuRAGError(
                    f"Ошибка получения токена: {response.status_code}",
                    code="TOKEN_ERROR",
                    details={"status_code": response.status_code, "response": response.text[:500]}
                )
        except requests.RequestException as e:
            raise CloudRuRAGError(
                f"Сетевая ошибка при получении токена: {e}",
                code="NETWORK_ERROR"
            )
    
    def retrieve(
        self,
        query: str,
        version_id: str | None = None,
        num_results: int = 5,
        retrieval_type: str = "SEMANTIC",
    ) -> dict:
        """Поиск по базе знаний.
        
        Args:
            query: Поисковый запрос
            version_id: ID версии (или используется default)
            num_results: Количество результатов
            retrieval_type: Тип поиска (SEMANTIC, KEYWORD, HYBRID)
            
        Returns:
            dict с результатами поиска
        """
        if not self.rag_public_url:
            raise CloudRuRAGError(
                "RAG_PUBLIC_URL не настроен",
                code="CONFIG_MISSING"
            )
        
        version_id = version_id or self.rag_version_id
        if not version_id:
            raise CloudRuRAGError(
                "RAG_VERSION_ID не указан",
                code="CONFIG_MISSING"
            )
        
        token = self._get_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "knowledge_base_version": version_id,
            "query": query,
            "retrieval_configuration": {
                "number_of_results": num_results,
                "retrieval_type": retrieval_type
            }
        }
        
        try:
            url = f"{self.rag_public_url.rstrip('/')}/api/v2/retrieve"
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                
                return {
                    "success": True,
                    "query": query,
                    "version_id": version_id,
                    "count": len(results),
                    "results": [
                        {
                            "id": r.get("id"),
                            "content": r.get("content"),
                            "score": r.get("score"),
                            "metadata": r.get("metadata", {}),
                        }
                        for r in results
                    ]
                }
            else:
                raise CloudRuRAGError(
                    f"Ошибка поиска: {response.status_code}",
                    code="RETRIEVE_ERROR",
                    details={"status_code": response.status_code, "response": response.text[:500]}
                )
        except requests.RequestException as e:
            raise CloudRuRAGError(
                f"Сетевая ошибка при поиске: {e}",
                code="NETWORK_ERROR"
            )
    
    def retrieve_with_reranking(
        self,
        query: str,
        version_id: str | None = None,
        num_results: int = 10,
        num_reranked: int = 5,
        retrieval_type: str = "SEMANTIC",
        reranker_model: str = "BAAI/bge-reranker-v2-m3",
    ) -> dict:
        """Поиск с ререйнкингом результатов.
        
        Args:
            query: Поисковый запрос
            version_id: ID версии
            num_results: Количество результатов для первичного поиска
            num_reranked: Количество результатов после ререйнкинга
            retrieval_type: Тип поиска
            reranker_model: Модель ререйнкера
            
        Returns:
            dict с результатами поиска
        """
        if not self.rag_public_url:
            raise CloudRuRAGError(
                "RAG_PUBLIC_URL не настроен",
                code="CONFIG_MISSING"
            )
        
        version_id = version_id or self.rag_version_id
        if not version_id:
            raise CloudRuRAGError(
                "RAG_VERSION_ID не указан",
                code="CONFIG_MISSING"
            )
        
        token = self._get_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "knowledge_base_version": version_id,
            "query": query,
            "retrieval_configuration": {
                "number_of_results": num_results,
                "retrieval_type": retrieval_type
            },
            "reranking_configuration": {
                "model_name": reranker_model,
                "model_source": "FOUNDATION_MODELS",
                "number_of_reranked_results": num_reranked
            }
        }
        
        try:
            url = f"{self.rag_public_url.rstrip('/')}/api/v2/retrieve"
            response = requests.post(url, headers=headers, json=payload, timeout=90)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                
                return {
                    "success": True,
                    "query": query,
                    "version_id": version_id,
                    "reranked": True,
                    "count": len(results),
                    "results": [
                        {
                            "id": r.get("id"),
                            "content": r.get("content"),
                            "score": r.get("score"),
                            "metadata": r.get("metadata", {}),
                        }
                        for r in results
                    ]
                }
            else:
                raise CloudRuRAGError(
                    f"Ошибка поиска с ререйнкингом: {response.status_code}",
                    code="RETRIEVE_ERROR",
                    details={"status_code": response.status_code, "response": response.text[:500]}
                )
        except requests.RequestException as e:
            raise CloudRuRAGError(
                f"Сетевая ошибка: {e}",
                code="NETWORK_ERROR"
            )
    
    def _get_indexing_token(self, force_refresh: bool = False) -> str:
        """Получить токен для API индексации."""
        if (not force_refresh and 
            self._indexing_token_cache["token"] and 
            self._indexing_token_cache["expires_at"] > time.time() + 300):
            return self._indexing_token_cache["token"]
        
        if not self.indexing_key_id or not self.indexing_key_secret:
            raise CloudRuRAGError(
                "Indexing credentials не настроены",
                code="CREDENTIALS_MISSING"
            )
        
        logger.info("Получаю токен для индексации...")
        
        try:
            response = requests.post(
                "https://iam.api.cloud.ru/api/v1/auth/token",
                json={"keyId": self.indexing_key_id, "secret": self.indexing_key_secret},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self._indexing_token_cache["token"] = data["access_token"]
                self._indexing_token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
                logger.info("Токен для индексации получен")
                return self._indexing_token_cache["token"]
            else:
                raise CloudRuRAGError(
                    f"Ошибка получения токена индексации: {response.status_code}",
                    code="TOKEN_ERROR",
                    details={"status_code": response.status_code, "response": response.text[:500]}
                )
        except requests.RequestException as e:
            raise CloudRuRAGError(
                f"Сетевая ошибка при получении токена: {e}",
                code="NETWORK_ERROR"
            )
    
    def get_versions(self) -> dict:
        """Получить список версий RAG из S3.
        
        Сканирует папку ArtifactsManagedRAG/{rag_id}/ в S3 бакете.
        
        Returns:
            dict со списком версий
        """
        import boto3
        from botocore.config import Config
        
        try:
            # Получаем S3 credentials из окружения
            tenant_id = os.environ.get("CLOUD_TENANT_ID")
            key_id = os.environ.get("CLOUD_KEY_ID")
            key_secret = os.environ.get("CLOUD_SECRET")
            
            if not all([tenant_id, key_id, key_secret]):
                raise CloudRuRAGError(
                    "S3 credentials не настроены для получения версий",
                    code="CREDENTIALS_MISSING"
                )
            
            config = Config(signature_version='s3v4', s3={'addressing_style': 'path'})
            s3_client = boto3.client(
                's3',
                endpoint_url='https://s3.cloud.ru',
                aws_access_key_id=f"{tenant_id}:{key_id}",
                aws_secret_access_key=key_secret,
                region_name='ru-central-1',
                config=config
            )
            
            # Сканируем папку версий
            prefix = f"ArtifactsManagedRAG/{self.rag_id}/"
            response = s3_client.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix=prefix,
                Delimiter='/'
            )
            
            versions = []
            for common_prefix in response.get('CommonPrefixes', []):
                version_id = common_prefix['Prefix'].split('/')[-2]
                
                # Получаем количество файлов в версии
                files_resp = s3_client.list_objects_v2(
                    Bucket=self.s3_bucket,
                    Prefix=common_prefix['Prefix']
                )
                file_count = len(files_resp.get('Contents', []))
                
                # Определяем статус: если есть файлы - READY
                status = "READY" if file_count > 0 else "UNKNOWN"
                
                versions.append({
                    "id": version_id,
                    "status": status,
                    "file_count": file_count,
                    "is_current": version_id == self.rag_version_id
                })
            
            # Сортируем - текущая версия первая, потом по ID
            versions.sort(key=lambda x: (not x.get("is_current", False), x.get("id", "")), reverse=True)
            
            return {
                "success": True,
                "count": len(versions),
                "current_version": self.rag_version_id,
                "versions": versions
            }
            
        except Exception as e:
            if isinstance(e, CloudRuRAGError):
                raise
            raise CloudRuRAGError(
                f"Ошибка получения версий из S3: {e}",
                code="GET_VERSIONS_ERROR"
            )
    
    def get_latest_ready_version(self) -> str | None:
        """Получить ID последней готовой версии RAG (не текущей).
        
        Returns:
            ID версии или None если нет других готовых версий
        """
        try:
            result = self.get_versions()
            if result.get("success"):
                for v in result.get("versions", []):
                    # Берём первую READY версию, которая не является текущей
                    if v.get("status") == "READY" and not v.get("is_current", False):
                        return v.get("id")
                # Если нет других версий, возвращаем текущую если она READY
                for v in result.get("versions", []):
                    if v.get("status") == "READY":
                        return v.get("id")
            return None
        except Exception as e:
            logger.warning(f"Не удалось получить последнюю версию: {e}")
            return None
    
    def update_to_latest_version(self) -> dict:
        """Обновить version_id на последнюю готовую версию.
        
        Returns:
            dict с результатом
        """
        latest = self.get_latest_ready_version()
        if latest:
            old_version = self.rag_version_id
            self.rag_version_id = latest
            logger.info(f"Версия RAG обновлена: {old_version} -> {latest}")
            return {
                "success": True,
                "old_version": old_version,
                "new_version": latest,
                "message": f"Версия обновлена на {latest}"
            }
        else:
            return {
                "success": False,
                "message": "Не найдено готовых версий RAG"
            }
    
    def start_indexing(
        self,
        s3_prefix: str = "",
        description: str = "",
        extensions: list[str] | None = None,
    ) -> dict:
        """Запустить индексацию RAG (создание новой версии).
        
        Args:
            s3_prefix: Префикс в S3 бакете для индексации
            description: Описание версии
            extensions: Список расширений для обработки (по умолчанию: txt, md, pdf)
            
        Returns:
            dict с результатом запуска индексации
        """
        token = self._get_indexing_token()
        
        headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Расширения по умолчанию
        if extensions is None:
            extensions = ["txt", "md", "pdf"]
        
        # Формируем extractors для каждого типа файлов
        extractors = []
        
        extension_configs = {
            "txt": {
                "extensions_supported": ["txt"],
                "extra_envs": {
                    "PARSER_TYPE": "simpleFile",
                    "SPLITTER": "RagSplitter_RecursiveCharacterTextSplitter",
                    "CHUNK_SIZE": "1500",
                    "CHUNK_OVERLAP": "500",
                    "SEPARATORS": '["\\n\\n","\\n"," "]',
                    "IS_SEPARATOR_REGEX": "false",
                    "KEEP_SEPARATOR": "KeepSeparator_None",
                },
            },
            "md": {
                "extensions_supported": ["md"],
                "extra_envs": {
                    "PARSER_TYPE": "markdown",
                    "SPLITTER": "RagSplitter_MarkdownSplitter",
                    "CHUNK_SIZE": "1500",
                    "CHUNK_OVERLAP": "500",
                },
            },
            "pdf": {
                "extensions_supported": ["pdf"],
                "extra_envs": {
                    "PARSER_TYPE": "simplePdf",
                    "SPLITTER": "RagSplitter_RecursiveCharacterTextSplitter",
                    "CHUNK_SIZE": "1500",
                    "CHUNK_OVERLAP": "500",
                    "SEPARATORS": '["\\n\\n","\\n"," "]',
                    "IS_SEPARATOR_REGEX": "false",
                    "KEEP_SEPARATOR": "KeepSeparator_None",
                },
            },
        }
        
        for ext in extensions:
            if ext in extension_configs:
                config = extension_configs[ext]
                extractors.append({
                    "cpu_requested": 1000,
                    "ram_requested": 1024,
                    "replicas": 1,
                    "image": "evo-inference-container-images.pkg.sbercloud.tech/products/evo-ai-assistant/backend/ragaas-etl-extractor/prod:v1.0.9",
                    "extensions_supported": config["extensions_supported"],
                    "extra_envs": config["extra_envs"],
                })
        
        payload = {
            "project_id": self.project_id,
            "rag_id": self.rag_id,
            "product_instance_id": self.product_instance_id,
            "cpu_requested": 2,
            "ram_requested": 2,
            "deploy_params": {
                "version": "v0",
                "transformer": {
                    "model": "openai",
                    "extra_envs": {
                        "EMBEDDER_NAME": "Qwen/Qwen3-Embedding-0.6B",
                        "EMBEDDER_MODEL_ID": "Qwen/Qwen3-Embedding-0.6B",
                        "EMBEDDER_TYPE": "foundationModels",
                    },
                },
                "extractors": extractors,
                "options": {
                    "auth_is_enabled": False,
                    "service_account_id": "",
                    "logaas_is_enabled": False,
                    "logaas_log_group_id": "",
                },
                "s3_storage": {
                    "s3_bucket_id": self.s3_bucket_id,
                    "s3_bucket": self.s3_bucket,
                    "s3_prefix": s3_prefix,
                },
            },
            "embedder": {
                "name": "Qwen/Qwen3-Embedding-0.6B",
                "model_id": "Qwen/Qwen3-Embedding-0.6B",
                "type": "foundationModels",
            },
            "options": {
                "auth_is_enabled": False,
                "service_account_id": "",
                "logaas_is_enabled": False,
                "logaas_log_group_id": "",
            },
            "description": description,
        }
        
        try:
            url = "https://console.cloud.ru/u-api/managed-rag/user-plane/api/v1/rags/runs"
            logger.info(f"Запуск индексации RAG: rag_id={self.rag_id}, s3_prefix={s3_prefix}")
            
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code in (200, 201, 202):
                data = response.json() if response.text else {}
                logger.info(f"Индексация запущена успешно")
                
                return {
                    "success": True,
                    "message": "Индексация RAG успешно запущена",
                    "rag_id": self.rag_id,
                    "project_id": self.project_id,
                    "s3_bucket": self.s3_bucket,
                    "s3_prefix": s3_prefix,
                    "extensions": extensions,
                    "response": data,
                }
            else:
                logger.error(f"Ошибка запуска индексации: {response.status_code} - {response.text[:500]}")
                raise CloudRuRAGError(
                    f"Ошибка запуска индексации: {response.status_code}",
                    code="INDEXING_ERROR",
                    details={
                        "status_code": response.status_code,
                        "response": response.text[:500]
                    }
                )
        except requests.RequestException as e:
            raise CloudRuRAGError(
                f"Сетевая ошибка при запуске индексации: {e}",
                code="NETWORK_ERROR"
            )





