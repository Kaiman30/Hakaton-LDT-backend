"""
Protocol-based type definitions for connectors.
These provide structural typing (duck typing) without inheritance overhead.
Useful for type checking and IDE support while keeping flexibility.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Protocol, AsyncIterator, Union, runtime_checkable
from datetime import datetime
from core.registry import register_protocol


@register_protocol("ILLMConnector")
@runtime_checkable
class ILLMConnector(Protocol):
    """Protocol for LLM connectors - structural typing"""

    @property
    def name(self) -> str:
        """Connector name identifier"""
        ...

    async def initialize(self) -> None:
        """Initialize connector resources"""
        ...

    async def shutdown(self) -> None:
        """Cleanup connector resources"""
        ...

    async def health_check(self) -> bool:
        """Check connector health"""
        ...

    def is_healthy(self) -> bool:
        """Get cached health status"""
        ...

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
        ...

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
        ...

    async def upload_file(
        self,
        file_data: Any,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """Upload file and return file_id"""
        ...

    async def upload_files_concurrent(
        self,
        files: List[Dict[str, Any]],
        timeout: Optional[float] = None,
    ) -> List[str]:
        """Upload multiple files concurrently"""
        ...

    async def delete_file(
        self,
        file_id: str,
        timeout: Optional[float] = None,
    ) -> bool:
        """Delete file from LLM service"""
        ...

    async def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """Get file information"""
        ...

    async def list_files(self) -> List[Dict[str, Any]]:
        """List uploaded files"""
        ...

    async def delete_files_concurrent(self, file_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple files concurrently"""
        ...

    async def batch_chat(
        self,
        payload: Dict[str, Optional[List[str]]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> tuple[List[Dict[str, Any]]]:
        """Batch chat processing"""
        ...


@register_protocol("IQueueConnector")
@runtime_checkable
class IQueueConnector(Protocol):
    """Protocol for queue/broker connectors"""

    @property
    def name(self) -> str:
        """Connector name identifier"""
        ...

    async def initialize(self) -> None:
        """Initialize connector resources"""
        ...

    async def shutdown(self) -> None:
        """Cleanup connector resources"""
        ...

    async def health_check(self) -> bool:
        """Check connector health"""
        ...

    def is_healthy(self) -> bool:
        """Get cached health status"""
        ...

    async def publish(
        self,
        topic: str,
        datagram_id: str,
        data: Dict[str, Any],
        *,
        key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        format_type: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Publish single message"""
        ...

    async def batch_publish(
        self,
        topic: str,
        messages: List[tuple],
        default_format: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Publish batch of messages"""
        ...

    async def subscribe(
        self,
        topics: List[str],
        group_id: str,
        *,
        format_type: Optional[str] = None,
        auto_offset_reset: str = "earliest",
        **kwargs: Any,
    ) -> None:
        """Subscribe to topics"""
        ...

    async def consume(self) -> Dict[str, Any]:
        """Consume next message - returns dict with \'payload\' and metadata"""
        ...

    async def commit(self, message: Dict[str, Any], **kwargs: Any) -> None:
        """Commit specific message"""
        ...


@register_protocol("IFileStorageConnector")
@runtime_checkable
class IFileStorageConnector(Protocol):
    """Protocol for file/blob storage connectors"""

    @property
    def name(self) -> str:
        """Connector name identifier"""
        ...

    async def initialize(self) -> None:
        """Initialize connector resources"""
        ...

    async def shutdown(self) -> None:
        """Cleanup connector resources"""
        ...

    async def health_check(self) -> bool:
        """Check connector health"""
        ...

    def is_healthy(self) -> bool:
        """Get cached health status"""
        ...

    async def download(
        self,
        object_name: str,
        *,
        timeout: Optional[float] = None,
        use_streaming: bool = False,
        chunk_size: int = 65536 * 4,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        **kwargs: Any,
    ) -> Union[bytes, AsyncIterator[bytes]]:
        """
        Download file.
        Returns bytes if use_streaming=False, AsyncIterator if use_streaming=True.
        """
        ...

    async def upload(
        self,
        object_name: str,
        data: bytes,
        *,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> None:
        """Upload bytes to storage"""
        ...


@register_protocol("IDBConnector")
@runtime_checkable
class IDBConnector(Protocol):
    """Protocol for database connectors"""

    @property
    def name(self) -> str:
        """Connector name identifier"""
        ...

    async def initialize(self) -> None:
        """Initialize connector resources"""
        ...

    async def shutdown(self) -> None:
        """Cleanup connector resources"""
        ...

    async def health_check(self) -> bool:
        """Check connector health"""
        ...

    def is_healthy(self) -> bool:
        """Get cached health status"""
        ...

    async def load(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """Execute SELECT and return list of rows"""
        ...

    async def load_one(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Execute SELECT and return single row"""
        ...

    async def execute(self, query: str, *args: Any) -> Any:
        """Execute DML (INSERT/UPDATE/DELETE)"""
        ...

    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        ...


@register_protocol("IHTTPConnector")
@runtime_checkable
class IHTTPConnector(Protocol):
    """Protocol for HTTP connectors"""

    @property
    def app(self) -> Any:
        """Get the web application instance"""
        ...

    @property
    def name(self) -> str:
        """Connector name identifier"""
        ...

    async def initialize(self) -> None:
        """Initialize connector resources"""
        ...

    async def shutdown(self) -> None:
        """Cleanup connector resources"""
        ...

    async def health_check(self) -> bool:
        """Check connector health"""
        ...

    def is_healthy(self) -> bool:
        """Get cached health status"""
        ...

    async def start(self, ip: str, port: int) -> None:
        """Start HTTP service"""
        ...

    async def health(self) -> Dict[str, Any]:
        """Get health status information"""
        ...

    async def status(self, status: Any) -> Dict[str, Any]:
        """Get current status information"""
        ...
