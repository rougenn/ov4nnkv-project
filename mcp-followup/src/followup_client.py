"""HTTP-клиент для работы с Follow-Up API.

Обеспечивает авторизацию, обработку ошибок и логирование запросов.
"""

import logging
from typing import Any

import httpx

# Настройка логирования
logger = logging.getLogger("followup_client")


class FollowUpAPIError(Exception):
    """Базовое исключение для ошибок Follow-Up API."""
    
    def __init__(self, message: str, status_code: int | None = None, details: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(FollowUpAPIError):
    """Ошибка авторизации (невалидный API-ключ или истёкший токен)."""
    pass


class NetworkError(FollowUpAPIError):
    """Сетевая ошибка (timeout, connection error)."""
    pass


class FollowUpClient:
    """HTTP-клиент для Follow-Up API.
    
    Поддерживает два варианта авторизации:
    1. Через email/password — клиент сам получит JWT токен
    2. Через готовый API-ключ (JWT токен) — используется напрямую
    
    Attributes:
        base_url: Базовый URL API
        email: Email для авторизации (опционально)
        password: Пароль для авторизации (опционально)
        _access_token: JWT токен доступа
        _client: HTTP клиент httpx
    """
    
    DEFAULT_TIMEOUT = 30.0
    
    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://api.follow-up.tech"
    ):
        """Инициализация клиента.
        
        Args:
            email: Email для авторизации в Follow-Up (опционально)
            password: Пароль для авторизации (опционально)
            api_key: Готовый API-ключ/JWT токен (опционально)
            base_url: Базовый URL API (по умолчанию https://api.follow-up.tech)
            
        Raises:
            ValueError: Если не указаны ни email/password, ни api_key
        """
        if not api_key and not (email and password):
            raise ValueError(
                "Необходимо указать либо api_key, либо email и password"
            )
        
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._access_token: str | None = api_key  # Если передан api_key, используем его сразу
        self._client: httpx.AsyncClient | None = None
        
        if api_key:
            logger.info(f"FollowUpClient инициализирован с API-ключом для {self.base_url}")
        else:
            logger.info(f"FollowUpClient инициализирован для {self.base_url}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.DEFAULT_TIMEOUT,
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "x-lang": "ru",
                }
            )
        return self._client
    
    async def close(self) -> None:
        """Закрыть HTTP клиент."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("HTTP клиент закрыт")
    
    async def login(self) -> dict:
        """Авторизация в Follow-Up API.
        
        Returns:
            dict: Данные пользователя и токены
            
        Raises:
            AuthenticationError: Неверные учётные данные
            NetworkError: Сетевая ошибка
            FollowUpAPIError: Другие ошибки API
        """
        logger.info("Выполняем авторизацию в Follow-Up API...")
        
        try:
            client = await self._get_client()
            response = await client.post(
                "/api/login",
                json={
                    "email": self.email,
                    "password": self.password,
                }
            )
            
            logger.debug(f"Login response status: {response.status_code}")
            
            if response.status_code == 401:
                raise AuthenticationError(
                    "Неверный email или пароль",
                    status_code=401
                )
            
            if response.status_code == 400:
                raise AuthenticationError(
                    "Некорректные данные для авторизации",
                    status_code=400,
                    details=response.json() if response.text else {}
                )
            
            # Follow-Up API возвращает 404 для несуществующего пользователя
            if response.status_code == 404:
                raise AuthenticationError(
                    "Пользователь не найден (неверный email или пароль)",
                    status_code=404
                )
            
            response.raise_for_status()
            data = response.json()
            
            # Сохраняем access token
            self._access_token = data["tokenPair"]["access"]["token"]
            logger.info("Авторизация успешна")
            
            return data
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout при авторизации: {e}")
            raise NetworkError(
                "Превышено время ожидания ответа от сервера",
                details={"error": str(e)}
            )
        except httpx.ConnectError as e:
            logger.error(f"Ошибка подключения: {e}")
            raise NetworkError(
                "Не удалось подключиться к серверу Follow-Up",
                details={"error": str(e)}
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка: {e.response.status_code}")
            raise FollowUpAPIError(
                f"Ошибка сервера: {e.response.status_code}",
                status_code=e.response.status_code,
                details={"error": str(e)}
            )

    async def _ensure_authenticated(self) -> None:
        """Убедиться, что клиент авторизован."""
        if not self._access_token:
            if self.email and self.password:
                await self.login()
            else:
                raise AuthenticationError(
                    "Нет токена авторизации и не указаны email/password для получения нового"
                )
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any
    ) -> dict:
        """Выполнить HTTP запрос к API.
        
        Args:
            method: HTTP метод (GET, POST, PUT, DELETE)
            endpoint: Эндпоинт API (например, /api/conference)
            **kwargs: Дополнительные параметры для httpx
            
        Returns:
            dict: JSON ответ от API
            
        Raises:
            AuthenticationError: Ошибка авторизации
            NetworkError: Сетевая ошибка
            FollowUpAPIError: Другие ошибки API
        """
        await self._ensure_authenticated()
        
        client = await self._get_client()
        
        # Добавляем Authorization header
        headers = kwargs.pop("headers", {})
        headers["authorization"] = f"Bearer {self._access_token}"
        
        logger.debug(f"Запрос: {method} {endpoint}")
        
        try:
            response = await client.request(
                method=method,
                url=endpoint,
                headers=headers,
                **kwargs
            )
            
            logger.debug(f"Ответ: {response.status_code}")
            
            # Обработка ошибок авторизации
            if response.status_code == 401:
                # Пробуем переавторизоваться только если есть credentials
                if self.email and self.password:
                    logger.warning("Токен истёк, пробуем переавторизоваться...")
                    self._access_token = None
                    await self.login()
                    
                    # Повторяем запрос с новым токеном
                    headers["authorization"] = f"Bearer {self._access_token}"
                    response = await client.request(
                        method=method,
                        url=endpoint,
                        headers=headers,
                        **kwargs
                    )
                    
                    if response.status_code == 401:
                        raise AuthenticationError(
                            "Не удалось авторизоваться",
                            status_code=401
                        )
                else:
                    raise AuthenticationError(
                        "Невалидный API-ключ",
                        status_code=401
                    )
            
            # Обработка клиентских ошибок
            if response.status_code == 400:
                error_data = response.json() if response.text else {}
                # API может вернуть список ошибок или словарь
                if isinstance(error_data, list):
                    error_message = "; ".join([str(e) for e in error_data])
                    raise FollowUpAPIError(
                        f"Некорректный запрос: {error_message}",
                        status_code=400,
                        details={"errors": error_data}
                    )
                elif isinstance(error_data, dict):
                    raise FollowUpAPIError(
                        f"Некорректный запрос: {error_data.get('message', 'Unknown error')}",
                        status_code=400,
                        details=error_data
                    )
                else:
                    raise FollowUpAPIError(
                        f"Некорректный запрос: {str(error_data)}",
                        status_code=400,
                        details={"raw": error_data}
                    )
            
            if response.status_code == 404:
                raise FollowUpAPIError(
                    "Ресурс не найден",
                    status_code=404
                )
            
            # Обработка серверных ошибок
            if response.status_code >= 500:
                raise FollowUpAPIError(
                    f"Ошибка сервера Follow-Up: {response.status_code}",
                    status_code=response.status_code
                )
            
            response.raise_for_status()
            
            # Возвращаем JSON или пустой dict
            if response.text:
                return response.json()
            return {}
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout: {method} {endpoint}")
            raise NetworkError(
                "Превышено время ожидания ответа",
                details={"method": method, "endpoint": endpoint, "error": str(e)}
            )
        except httpx.ConnectError as e:
            logger.error(f"Connection error: {method} {endpoint}")
            raise NetworkError(
                "Ошибка подключения к серверу",
                details={"method": method, "endpoint": endpoint, "error": str(e)}
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code}")
            raise FollowUpAPIError(
                f"HTTP ошибка: {e.response.status_code}",
                status_code=e.response.status_code,
                details={"error": str(e)}
            )
    
    async def join_conference(self, conference_url: str, theme: str = "Созвон") -> dict:
        """Подключить бота Follow-Up к созвону по ссылке.
        
        Args:
            conference_url: Ссылка на созвон (Zoom, Meet, Teams, Telemost и др.)
            theme: Название/тема созвона (опционально)
            
        Returns:
            dict: Данные о созданной конференции, включая conference_id
            
        Raises:
            FollowUpAPIError: Ошибка API (невалидная ссылка, созвон недоступен и т.д.)
        """
        logger.info(f"Подключаем бота к созвону: {conference_url}")
        
        # Определяем платформу и externalId по URL
        source = self._detect_platform(conference_url)
        external_id = self._extract_external_id(conference_url, source)
        
        response = await self._request(
            method="POST",
            endpoint="/api/conference/link",
            json={
                "theme": theme,
                "link": conference_url,
                "source": source,
                "externalId": external_id,
                "selectedProcessing": [],
            }
        )
        
        logger.info(f"Бот успешно подключен к созвону")
        return response
    
    def _detect_platform(self, url: str) -> str:
        """Определить платформу ВКС по URL.
        
        Args:
            url: Ссылка на созвон
            
        Returns:
            str: Идентификатор платформы для API (в формате camelCase)
        """
        url_lower = url.lower()
        
        # Формат source согласно API: zoom, googleMeet, telemost, msTeams, sbJazz, trueConf, konturTalk, skype, jitsiMeet
        if "meet.google.com" in url_lower:
            return "googleMeet"
        elif "zoom.us" in url_lower or "zoom.com" in url_lower:
            return "zoom"
        elif "teams.microsoft.com" in url_lower or "teams.live.com" in url_lower:
            return "msTeams"
        elif "telemost.yandex" in url_lower:
            return "telemost"
        elif "salutejazz" in url_lower or "jazz.sber" in url_lower:
            return "sbJazz"
        elif "trueconf" in url_lower:
            return "trueConf"
        elif "konturtalk" in url_lower or "kontur" in url_lower:
            return "konturTalk"
        elif "skype" in url_lower:
            return "skype"
        elif "meet.jit.si" in url_lower or "jitsi" in url_lower:
            return "jitsiMeet"
        else:
            # По умолчанию пробуем как googleMeet
            return "googleMeet"
    
    def _extract_external_id(self, url: str, source: str) -> str:
        """Извлечь externalId (ID встречи) из URL.
        
        Args:
            url: Ссылка на созвон
            source: Платформа ВКС
            
        Returns:
            str: ID встречи для API
        """
        import re
        
        if source == "googleMeet":
            # https://meet.google.com/abc-defg-hij -> abc-defg-hij
            match = re.search(r'meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})', url.lower())
            if match:
                return match.group(1)
        
        elif source == "zoom":
            # https://zoom.us/j/123456789 -> 123456789
            match = re.search(r'/j/(\d+)', url)
            if match:
                return match.group(1)
        
        elif source == "telemost":
            # https://telemost.yandex.ru/j/12345678901234 -> 12345678901234
            match = re.search(r'/j/(\d+)', url)
            if match:
                return match.group(1)
        
        elif source == "msTeams":
            # Для Teams ID сложнее, берём часть после meetup-join
            match = re.search(r'meetup-join/([^/]+)', url)
            if match:
                return match.group(1)
        
        # Fallback: используем последнюю часть URL
        parts = url.rstrip('/').split('/')
        return parts[-1] if parts else url

    async def get_conference_info(self, conference_id: str) -> dict:
        """Получить информацию о конференции (без транскрипции).
        
        Args:
            conference_id: ID созвона из Follow-Up
            
        Returns:
            dict: Метаданные конференции (название, дата, участники, статус и т.д.)
            
        Raises:
            FollowUpAPIError: Созвон не найден
        """
        logger.info(f"Получаем информацию о конференции: {conference_id}")
        
        conference_info = await self._request(
            method="GET",
            endpoint=f"/api/conference/{conference_id}"
        )
        
        logger.info(f"Информация о конференции {conference_id} успешно получена")
        
        return conference_info

    async def get_transcription(self, conference_id: str) -> dict:
        """Получить транскрипцию созвона.
        
        Args:
            conference_id: ID созвона из Follow-Up
            
        Returns:
            dict: Данные транскрипции с метаданными
            
        Raises:
            FollowUpAPIError: Созвон не найден, транскрипция не готова и т.д.
        """
        logger.info(f"Получаем транскрипцию для конференции: {conference_id}")
        
        # Сначала получаем информацию о конференции для метаданных
        conference_info = await self._request(
            method="GET",
            endpoint=f"/api/conference/{conference_id}"
        )
        
        # Получаем транскрипцию
        transcription_data = await self._request(
            method="GET",
            endpoint=f"/api/conference/{conference_id}/transcription"
        )
        
        logger.info(f"Транскрипция успешно получена для конференции {conference_id}")
        
        return {
            "conference_info": conference_info,
            "transcription": transcription_data
        }

    async def list_conferences(self, limit: int = 20, offset: int = 0) -> dict:
        """Получить список записанных созвонов.
        
        Args:
            limit: Количество записей (1-100)
            offset: Смещение для пагинации
            
        Returns:
            dict: Список созвонов с метаданными и общим количеством
            
        Raises:
            FollowUpAPIError: Ошибка API (кроме 404 - пустой список)
        """
        # Вычисляем номер страницы из offset
        page = (offset // limit) + 1 if limit > 0 else 1
        
        logger.info(f"Получаем список созвонов (limit={limit}, offset={offset}, page={page})")
        
        try:
            result = await self._request(
                method="POST",
                endpoint="/api/conference/listing/history",
                json={
                    "paging": {
                        "size": limit,
                        "current": page,
                    },
                    "search": None,
                    "filter": {},
                    "sort": {
                        "by": "date",
                        "order": "desc",
                    },
                }
            )
        except FollowUpAPIError as e:
            # 404 означает что нет созвонов - возвращаем пустой список
            if e.status_code == 404:
                logger.info("Нет записанных созвонов (404)")
                return {"total": 0, "conferences": []}
            raise
        
        # API возвращает объект с page (массив) и summary (pages, elements)
        if isinstance(result, list):
            conferences = result
            total = len(conferences)
        else:
            conferences = result.get("page", result.get("data", []))
            summary = result.get("summary", {})
            total = summary.get("elements", len(conferences))
        
        logger.info(f"Получено {len(conferences)} созвонов из {total}")
        
        return {
            "total": total,
            "conferences": conferences
        }

    async def download_pdf(self, conference_id: str) -> bytes:
        """Скачать PDF отчёт с транскрипцией созвона.
        
        Использует lk.follow-up.tech с next-auth авторизацией.
        
        Args:
            conference_id: ID созвона из Follow-Up (UUID)
            
        Returns:
            bytes: Содержимое PDF файла
            
        Raises:
            AuthenticationError: Ошибка авторизации
            FollowUpAPIError: PDF не найден или ошибка генерации
        """
        logger.info(f"Скачиваем PDF для конференции: {conference_id}")
        
        lk_base_url = "https://lk.follow-up.tech"
        
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            # 1. Получаем CSRF token
            csrf_resp = await client.get(f"{lk_base_url}/api/auth/csrf")
            if csrf_resp.status_code != 200:
                raise NetworkError(
                    "Не удалось получить CSRF token",
                    details={"status": csrf_resp.status_code}
                )
            
            csrf_token = csrf_resp.json().get("csrfToken")
            
            # 2. Авторизуемся через next-auth
            if not self.email or not self.password:
                raise AuthenticationError(
                    "Для скачивания PDF требуются email и password (не API-ключ)"
                )
            
            login_resp = await client.post(
                f"{lk_base_url}/api/auth/callback/credentials",
                data={
                    "email": self.email,
                    "password": self.password,
                    "csrfToken": csrf_token,
                    "callbackUrl": lk_base_url,
                    "json": "true"
                },
                headers={"content-type": "application/x-www-form-urlencoded"}
            )
            
            if login_resp.status_code != 200:
                raise AuthenticationError(
                    "Ошибка авторизации в lk.follow-up.tech",
                    status_code=login_resp.status_code
                )
            
            # 3. Проверяем сессию
            session_resp = await client.get(f"{lk_base_url}/api/auth/session")
            session_data = session_resp.json()
            
            if not session_data or not session_data.get("user"):
                raise AuthenticationError(
                    "Не удалось авторизоваться в lk.follow-up.tech"
                )
            
            # 4. Скачиваем PDF
            pdf_url = f"{lk_base_url}/conference/{conference_id}/report/transcription"
            pdf_resp = await client.get(pdf_url, params={"format": "pdf"})
            
            if pdf_resp.status_code != 200:
                raise FollowUpAPIError(
                    f"Ошибка скачивания PDF: {pdf_resp.status_code}",
                    status_code=pdf_resp.status_code
                )
            
            # Проверяем что это PDF
            if not pdf_resp.content or pdf_resp.content[:4] != b'%PDF':
                raise FollowUpAPIError(
                    "Ответ не является PDF файлом",
                    status_code=200,
                    details={"content_type": pdf_resp.headers.get("content-type")}
                )
            
            logger.info(f"PDF успешно скачан: {len(pdf_resp.content)} bytes")
            return pdf_resp.content

    async def __aenter__(self) -> "FollowUpClient":
        """Поддержка async context manager."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Закрытие клиента при выходе из контекста."""
        await self.close()
