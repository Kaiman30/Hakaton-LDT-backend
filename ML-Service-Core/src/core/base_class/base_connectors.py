
"""
Base connector abstractions for core services:
- LLM connectors
- Queue/broker connectors
- File storage connectors
- Database connectors
- HTTP connectors

These classes define a minimal, consistent lifecycle and health-check API.
Concrete implementations live in `connectors/` and should subclass the
appropriate base.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional, AsyncIterator


class BaseConnector(abc.ABC):
    """Common lifecycle and health-check contract for all connectors."""

    def __init__(self, name: str):
        self._name = name
        self._healthy: bool = False

    @property
    def name(self) -> str:
        return self._name

    @classmethod
    def from_config(cls, config: Any, **kwargs) -> "BaseConnector":
        """
        Create connector instance from config.
        Subclasses MUST override this method.
        """
        raise NotImplementedError(f"{cls.__name__} must implement from_config()")

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Allocate resources (connection pools, clients, threads, etc.)."""

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Cleanly release all resources."""

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Perform a real remote-health check if possible."""

    def is_healthy(self) -> bool:
        """Fast, cached health indicator."""
        return self._healthy

    def _set_health(self, value: bool) -> None:
        self._healthy = value


class LLMConnector(BaseConnector, abc.ABC):
    """Base abstraction for LLM providers."""

    @abc.abstractmethod
    async def chat(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Non-streaming chat. Returns response dict."""

    @abc.abstractmethod
    async def chat_stream(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """Streaming chat. Yields text chunks."""

    @abc.abstractmethod
    async def upload_file(
        self,
        file_data: Any,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """Upload a single file and return provider-specific file identifier."""

    @abc.abstractmethod
    async def upload_files_concurrent(
        self,
        files: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> List[str]:
        """Upload multiple files concurrently and return their identifiers."""


class QueueConnector(BaseConnector, abc.ABC):
    """Base abstraction for message brokers / queues."""

    @abc.abstractmethod
    async def publish(
        self,
        topic: str,
        datagram_id: str,
        data: Dict[str, Any],
        *,
        key: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Publish a single message."""

    @abc.abstractmethod
    async def batch_publish(
        self,
        topic: str,
        messages: List[Any],
        **kwargs: Any,
    ) -> None:
        """Publish a batch of messages."""

    @abc.abstractmethod
    async def subscribe(
        self,
        topics: List[str],
        group_id: str,
        **kwargs: Any,
    ) -> None:
        """Subscribe consumer to topics and start delivering messages."""

    @abc.abstractmethod
    async def consume(self) -> Any:
        """Receive next message from the queue (blocking until available)."""


class FileStorageConnector(BaseConnector, abc.ABC):
    """Base abstraction for file/blob storage."""

    @abc.abstractmethod
    async def download(
        self,
        object_name: str,
        *,
        timeout: Optional[float] = None,
        use_streaming: bool = False,
        **kwargs: Any,
    ) -> Any:
        """
        Unified download API.
        Returns bytes or AsyncIterator[bytes] depending on `use_streaming`.
        """

    @abc.abstractmethod
    async def upload(
        self,
        object_name: str,
        data: bytes,
        *,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> None:
        """Upload bytes to storage."""


class DBConnector(BaseConnector, abc.ABC):
    """Base abstraction for databases."""

    @abc.abstractmethod
    async def load(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """Execute SELECT and return list of rows."""

    @abc.abstractmethod
    async def load_one(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Execute SELECT and return a single row."""

    @abc.abstractmethod
    async def execute(self, query: str, *args: Any) -> Any:
        """Execute DML (INSERT/UPDATE/DELETE)."""

    @abc.abstractmethod
    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Check DB connectivity."""


class HTTPConnector(BaseConnector, abc.ABC):
    """Base abstraction for HTTP services."""

    @property
    @abc.abstractmethod
    def app(self) -> Any:
        """Get the web application instance (e.g., FastAPI app)."""

    @abc.abstractmethod
    async def start(self, ip: str, port: int) -> None:
        """Start HTTP service."""

    @abc.abstractmethod
    async def health(self) -> Dict[str, Any]:
        """Get health status information."""

    @abc.abstractmethod
    async def status(self, status: Any) -> Dict[str, Any]:
        """Get current operation status."""
