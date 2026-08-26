"""
GigaChat API Connector - Pure async implementation for no-GIL
OAuth flow как в официальном SDK - ПОЛНЫЙ КОД
"""

import asyncio
import json
import uuid
from typing import Optional, List, Dict, AsyncIterator, Any
from datetime import datetime, timedelta, timezone

import httpx

from core.base_class.base_connectors import LLMConnector
from core.registry import register_connector, dependence_connector
from models.gigachat_models import (
    GigaChatMessage,
    GigaChatChatRequest,
    GigaChatChatResponse,
    GigaChatFileInfo,
    GigaChatTokenResponse,
    GigaChatModelInfo,
    GigaChatHealthCheckResponse,
    GigaChatFileUploadRequest,
)


@register_connector("GigaChat")
@dependence_connector("LLM")
class GigaChatConnector(LLMConnector):
    """GigaChat REST API wrapper using httpx (Pure async implementation)"""

    # MIME type mapping
    MIME_TYPES = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".bmp": "image/bmp",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".aac": "audio/aac",
        ".mp4": "video/mp4",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".mov": "video/quicktime",
        ".wmv": "video/x-ms-wmv",
        ".flv": "video/x-flv",
        ".zip": "application/zip",
        ".tar": "application/x-tar",
        ".gz": "application/gzip",
        ".7z": "application/x-7z-compressed",
        ".rar": "application/x-rar-compressed",
        ".json": "application/json",
        ".xml": "application/xml",
        ".html": "text/html",
        ".css": "text/css",
        ".sql": "text/sql",
        ".py": "text/plain",
        ".java": "text/plain",
        ".cpp": "text/plain",
        ".go": "text/plain",
        ".rs": "text/plain",
    }

    def __init__(
        self,
        get_logger,
        base_url: str,
        api_version: str,
        oauth_url: str,
        credentials: Optional[str] = None,
        model: str = "GigaChat-Max",
        scope: str = "GIGACHAT_API_B2B",
        verify_ssl: bool = False,
        timeout: float = 30.0,
        max_connections: int = 10,
    ):
        super().__init__(name="GigaChat")
        self.logger = get_logger()
        self.model = model
        self.scope = scope
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_connections = max_connections

        # Используем переданные URL из настроек
        self.BASE_URL = base_url.rstrip("/")
        self.API_VERSION = api_version
        self.OAUTH_URL = oauth_url.rstrip("/")

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None
        self._health_status = False

        # OAuth tokens
        self.credentials = credentials
        self.access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    @classmethod
    def from_config(cls, config: Any, **kwargs) -> "GigaChatConnector":
        """
        Create GigaChatConnector from config.

        Args:
            config: Settings object with config.gigachat
            **kwargs: Additional arguments (ignored for compatibility)

        Returns:
            Configured GigaChatConnector instance
        """
        from utils.logging import get_logger_from_config

        return cls(
            get_logger=lambda: get_logger_from_config(config),
            credentials=config.gigachat.access_token,
            model=config.gigachat.model,
            scope=config.gigachat.scope,
            verify_ssl=config.gigachat.verify_ssl,
            timeout=float(config.gigachat.request_timeout_seconds),
            max_connections=config.gigachat.max_connections,
            base_url=config.gigachat.base_url,
            api_version=config.gigachat.api_version,
            oauth_url=config.gigachat.oauth_url,
        )

    async def _refresh_access_token(self) -> None:
        """Получить access_token по credentials"""
        if not self.credentials:
            raise ValueError("No credentials available for OAuth")

        headers = {
            "Authorization": f"Basic {self.credentials}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {"scope": self.scope}

        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=10.0) as client:
            resp = await client.post(self.OAUTH_URL, headers=headers, data=data)
            resp.raise_for_status()

        body = resp.json()

        token_response = GigaChatTokenResponse.from_api_response(body)

        self.access_token = token_response.access_token
        # Use the expires_in from the response if available and reasonable, otherwise default to 29 minutes
        if token_response.expires_in and 0 < token_response.expires_in < 86400:  # Less than a day in seconds
            # It's a duration in seconds
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_response.expires_in)
        else:
            # Default to 29 minutes if no valid expires_in provided
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=29)

        self.logger.info("Access token refreshed")

    async def _ensure_token(self) -> None:
        """Обновить токен если просрочен"""
        if (
            not self.access_token
            or not self._token_expires_at
            or datetime.now(timezone.utc) >= self._token_expires_at
        ):
            await self._refresh_access_token()

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        if not self.access_token:
            raise ValueError("Access token not available")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def _get_mime_type(self, filename: str) -> str:
        """Get MIME type from filename"""
        filename_lower = filename.lower()
        for ext, mime_type in self.MIME_TYPES.items():
            if filename_lower.endswith(ext):
                return mime_type
        return "application/octet-stream"

    async def initialize(self) -> None:
        """Initialize async HTTP client"""
        try:
            if not self.credentials and not self.access_token:
                raise ValueError("No credentials or access_token provided")

            limits = httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_connections // 2,
            )

            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=self.timeout,
                verify=self.verify_ssl,
                limits=limits,
            )

            # Получаем токен при инициализации (если используем OAuth flow)
            await self._ensure_token()
            self._set_health(True)
            self.logger.info(
                f"GigaChat initialized with model {self.model}, scope {self.scope}"
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize GigaChat: {e}")
            self._set_health(False)
            raise

    async def shutdown(self) -> None:
        """Shutdown async HTTP client"""
        if self._client:
            try:
                await self._client.aclose()
                self.logger.info("GigaChat HTTP client closed")
            except Exception as e:
                self.logger.error(f"Error closing HTTP client: {e}")

    async def upload_file(
        self,
        file_data: Any,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        if not self._client:
            raise RuntimeError("GigaChat client not initialized")

        await self._ensure_token()
        try:
            timeout = timeout or self.timeout

            if hasattr(file_data, "read"):
                if not filename and hasattr(file_data, "name"):
                    filename = file_data.name
                    if "/" in filename:
                        filename = filename.split("/")[-1]
                    if "\\" in filename:
                        filename = filename.split("\\")[-1]
                file_data = file_data.read()

            if not filename:
                filename = f"file_{uuid.uuid4().hex[:8]}"

            if mime_type is None:
                mime_type = self._get_mime_type(filename)
                self.logger.debug(
                    f"Auto-detected MIME type: {mime_type} for {filename}"
                )

            files = {"file": (filename, file_data, mime_type)}

            # Using the new data model for the request
            upload_request = GigaChatFileUploadRequest(purpose="general")
            data = upload_request.to_dict()

            self.logger.debug(f"Uploading file: {filename} ({len(file_data)} bytes)")

            response = await asyncio.wait_for(
                self._client.post(
                    f"/{self.API_VERSION}/files",
                    files=files,
                    data=data,
                    headers=self._get_auth_headers(),
                ),
                timeout=timeout,
            )
            if response.status_code >= 400:
                self.logger.error("Upload response body: %s", response.text)
            response.raise_for_status()

            result = response.json()
            # Using the new data model to process the response
            file_info = GigaChatFileInfo.from_api_response(result)
            self.logger.info(f"File uploaded successfully: {file_info.file_id}")
            return file_info.file_id

        except asyncio.TimeoutError:
            self.logger.error(f"Upload timeout after {timeout}s")
            raise TimeoutError(f"Upload exceeded {timeout} seconds")
        except Exception as e:
            self.logger.error(f"Error uploading file: {e}", exc_info=True)
            raise

    async def upload_files_concurrent(
        self,
        files: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> List[str]:
        timeout = timeout or self.timeout
        tasks = [
            self.upload_file(
                file_data=f["data"],
                filename=f.get("filename"),
                mime_type=f.get("mime_type", "application/octet-stream"),
                timeout=timeout,
            )
            for f in files
        ]
        self.logger.info(f"Uploading {len(files)} files concurrently")
        results = await asyncio.gather(*tasks, return_exceptions=False)
        successfully_uploaded = [r for r in results if r]
        self.logger.info(
            f"Successfully uploaded {len(successfully_uploaded)}/{len(files)} files"
        )
        return successfully_uploaded

    async def chat(
        self,
        prompt: str,
        file_ids: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        stream: bool = False,
    ) -> Any:
        if not self._client:
            raise RuntimeError("GigaChat client not initialized")

        timeout = timeout or self.timeout

        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_message: Dict[str, Any] = {"role": "user", "content": prompt}
        if file_ids:
            # attachments: [[file_id1], [file_id2], ...]
            user_message["attachments"] = file_ids
        messages.append(user_message)

        payload = self._build_chat_payload(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
        )

        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        self.logger.debug(
            "Chat payload:\n%s",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

        if stream:
            return self._chat_stream(payload, headers, timeout)
        return await self._chat_complete(payload, headers, timeout)

    def _build_chat_payload(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:

        # Convert message dictionaries to GigaChatMessage objects
        gigachat_messages = [
            GigaChatMessage(
                role=msg["role"],
                content=msg["content"],
                attachments=msg.get("attachments")
            )
            for msg in messages
        ]

        chat_request = GigaChatChatRequest(
            messages=gigachat_messages,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )
        return chat_request.to_dict()
    
    async def _chat_complete(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        timeout: float,
    ) -> Dict[str, Any]:
        import json as json_lib

        payload_json = json_lib.dumps(payload, ensure_ascii=False, indent=2)
        self.logger.debug(f"Chat request payload:\n{payload_json}")

        try:
            response = await asyncio.wait_for(
                self._client.post(
                    f"/{self.API_VERSION}/chat/completions",
                    json=payload,
                    headers=headers,
                ),
                timeout=timeout,
            )

            if response.status_code >= 400:
                self.logger.error(
                    "Chat response status=%d body: %s",
                    response.status_code,
                    response.text,
                )
                if response.status_code == 400:
                    self.logger.error("400 Bad Request - Invalid JSON syntax detected")
                    self.logger.error("Payload was:\n%s", payload_json)

            response.raise_for_status()

            result = response.json()
            message_content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})

            # Create response using the new data model
            chat_response = GigaChatChatResponse(
                response=message_content,
                tokens_used=usage.get("completion_tokens", 0),
                tokens_total=usage.get("total_tokens", 0),
                model=self.model,
                usage=usage
            )
            return chat_response.to_dict()

        except asyncio.TimeoutError:
            self.logger.error(f"Chat timeout after {timeout}s")
            raise TimeoutError(f"Chat exceeded {timeout} seconds")

    async def _chat_stream(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        timeout: float,
    ) -> AsyncIterator[str]:
        async with self._client.stream(
            "POST",
            f"/{self.API_VERSION}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        ) as response:
            if response.status_code >= 400:
                text = await response.aread()
                self.logger.error(
                    "Chat stream error body: %s", text.decode("utf-8", "ignore")
                )
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                else:
                    data_str = line
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}) or choices[0].get("message", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    self.logger.warning(f"Failed to parse stream line: {data_str}")

    async def get_file_info(self, file_id: str) -> Dict:
        await self._ensure_token()
        if not self._client:
            raise RuntimeError("GigaChat client not initialized")

        response = await asyncio.wait_for(
            self._client.get(
                f"/{self.API_VERSION}/files/{file_id}",
                headers=self._get_auth_headers(),
            ),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            self.logger.error("Get file info: %s", response.text)
        response.raise_for_status()

        file_info = response.json()

        # Create and return file info using the new data model
        gigachat_file_info = GigaChatFileInfo.from_api_response(file_info)
        return gigachat_file_info.to_dict()

    async def list_files(self) -> List[Dict]:
        await self._ensure_token()
        if not self._client:
            raise RuntimeError("GigaChat client not initialized")

        response = await asyncio.wait_for(
            self._client.get(
                f"/{self.API_VERSION}/files",
                headers=self._get_auth_headers(),
            ),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            self.logger.error("List files: %s", response.text)
        response.raise_for_status()

        result = response.json()
        files = result.get("data", [])
        self.logger.info(f"Retrieved {len(files)} files from storage")

        # Convert to new data model and return as dictionaries
        return [
            GigaChatFileInfo.from_api_response(f).to_dict()
            for f in files
        ]

    async def delete_file(self, file_id: str, timeout: Optional[float] = None) -> bool:
        await self._ensure_token()
        if not self._client:
            raise RuntimeError("GigaChat client not initialized")

        # Use provided timeout or default to self.timeout
        effective_timeout = timeout if timeout is not None else self.timeout

        response = await asyncio.wait_for(
            self._client.post(
                f"/{self.API_VERSION}/files/{file_id}/delete",
                headers=self._get_auth_headers(),
            ),
            timeout=effective_timeout,
        )
        if response.status_code >= 400:
            self.logger.error("Delete file: %s", response.text)
        response.raise_for_status()

        self.logger.info(f"File deleted: {file_id}")
        return True

    async def delete_files_concurrent(self, file_ids: List[str]) -> Dict:
        self.logger.info(f"Deleting {len(file_ids)} files concurrently")
        tasks = [self.delete_file(fid) for fid in file_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if isinstance(r, Exception))
        self.logger.info(
            f"Deleted {successful}/{len(file_ids)} files ({failed} failed)"
        )

        return {
            "total": len(file_ids),
            "successful": successful,
            "failed": failed,
        }

    async def health_check(self) -> GigaChatHealthCheckResponse:
        if not self._client:
            return False

        try:
            await self._ensure_token()
            response = await asyncio.wait_for(
                self._client.get(
                    f"/{self.API_VERSION}/models",
                    headers=self._get_auth_headers(),
                ),
                timeout=5.0,
            )
            if response.status_code >= 400:
                self.logger.error("Health check: %s", response.text)
            response.raise_for_status()

            # Parse response using the new data model
            result = response.json()
            models_data = result.get("data", [])

            # Create model info objects using the new data model
            models = [GigaChatModelInfo.from_api_response(model_data) for model_data in models_data]

            self._health_status = True
            self.logger.debug("Health check passed")
            return GigaChatHealthCheckResponse(status=self._health_status, models_available=models)
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            self._health_status = False
            return GigaChatHealthCheckResponse(status=self._health_status, error=str(e))

    def is_healthy(self) -> bool:
        return self._health_status

    async def batch_chat(
        self,
        payload: dict[str, Optional[List[str]]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> tuple[List[Dict]]:
        timeout = timeout or self.timeout
        tasks = [
            self.chat(
                prompt=prompt,
                file_ids=file_id,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                stream=False,
            )
            for prompt, file_id in payload.items()
        ]
        self.logger.info(f"Batch chat: {len(payload)} requests")
        return await asyncio.gather(*tasks, return_exceptions=False)
