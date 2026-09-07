"""
Storage Interface - Strategy pattern implementation for file storage connectors.

Allows switching between different storage providers (MinIO, S3, Azure Blob, etc.)
while maintaining the same API.
"""

from typing import Any, AsyncGenerator, Optional, Union

from utils.observer import EventPublisher
from core.base_class.protocols import IFileStorageConnector
from core.base_class.base_interface import BaseInterface
from core.registry import register_interface


@register_interface("Storage")
class StorageInterface(BaseInterface, IFileStorageConnector):  # ← ДОБАВЛЯЕМ протокол!
    """
    High-level interface for file storage operations.

    Implements Strategy pattern - can switch between different storage providers
    (MinIO, S3, Azure Blob, etc.) transparently.
    """

    def __init__(
        self,
        worker: IFileStorageConnector,
        name: Optional[str] = None,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        """
        Initialize Storage interface.

        Args:
            worker: Storage connector instance (e.g., MinIOConnector)
            name: Interface name (defaults to worker name)
            event_publisher: Optional event publisher for observability
        """
        super().__init__(worker, name, event_publisher)

    @property
    def worker(self) -> IFileStorageConnector:
        """Get underlying storage connector"""
        return self._worker

    # ============ IFileStorageConnector protocol implementation ============

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
    ) -> Union[bytes, AsyncGenerator[bytes, None]]:
        """
        Download file (bytes or AsyncGenerator).

        Args:
            object_name: Name of object to download
            timeout: Download timeout
            use_streaming: If True, returns AsyncGenerator; if False, returns bytes
            chunk_size: Size of chunks for streaming
            max_retries: Number of retry attempts
            retry_delay: Delay between retries
            **kwargs: Additional arguments

        Returns:
            File content as bytes or AsyncGenerator
        """
        result = await self._execute_with_tracking(
            "download",
            self._worker.download,
            object_name,
            timeout=timeout,
            use_streaming=use_streaming,
            chunk_size=chunk_size,
            max_retries=max_retries,
            retry_delay=retry_delay,
            **kwargs,
            metadata={
                "object_name": object_name,
                "use_streaming": use_streaming,
                "has_timeout": timeout is not None,
            },
        )
        return result

    async def upload(
        self,
        object_name: str,
        data: bytes,
        *,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> None:
        """
        Upload bytes to storage.

        Args:
            object_name: Name of object to create
            data: File content as bytes
            timeout: Upload timeout
            **kwargs: Additional arguments
        """
        await self._execute_with_tracking(
            "upload",
            self._worker.upload,
            object_name,
            data,
            timeout=timeout,
            **kwargs,
            metadata={
                "object_name": object_name,
                "data_size": len(data),
                "timeout": timeout,
            },
        )

    # ============ Convenience methods (not part of protocol) ============

    async def get_file(self, file_path: str) -> bytes:
        """Alias for download_bytes - used by documents_service"""
        return await self.download_bytes(object_name=file_path)

    async def download_bytes(
        self,
        object_name: str,
        *,
        timeout: Optional[float] = 30.0,
        **kwargs: Any,
    ) -> bytes:
        """
        Download file as bytes (convenience method).

        Args:
            object_name: Name of object to download
            timeout: Download timeout
            **kwargs: Additional arguments

        Returns:
            File content as bytes
        """
        result = await self.download(
            object_name,
            timeout=timeout,
            use_streaming=False,
            **kwargs,
        )
        return result  # type: ignore  # use_streaming=False гарантирует bytes

    async def download_stream(
        self,
        object_name: str,
        *,
        timeout: Optional[float] = 30.0,
        **kwargs: Any,
    ) -> AsyncGenerator[bytes, None]:
        """
        Download file as stream (convenience method).

        Args:
            object_name: Name of object to download
            timeout: Download timeout
            **kwargs: Additional arguments

        Yields:
            Chunks of file content as bytes
        """
        result = await self.download(
            object_name,
            timeout=timeout,
            use_streaming=True,
            **kwargs,
        )
        return result  # type: ignore  # use_streaming=True гарантирует AsyncGenerator

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        *,
        timeout: Optional[float] = 30.0,
        **kwargs: Any,
    ) -> str:
        """
        Upload file with automatic object naming (convenience method).

        Args:
            file_data: File content as bytes
            filename: Original filename
            timeout: Upload timeout
            **kwargs: Additional arguments

        Returns:
            Object name in storage
        """
        object_name = f"documents/{filename}"
        await self.upload(
            object_name=object_name,
            data=file_data,
            timeout=timeout or 30.0,
            **kwargs,
        )
        return object_name

    # ============ Protocol required methods ============

    @property
    def name(self) -> str:
        """Get connector name - required by IFileStorageConnector protocol"""
        return self._name

    async def health_check(self) -> bool:
        """Check storage connectivity - required by protocol"""
        return await self._execute_with_tracking(
            "health_check",
            self._worker.health_check,
            metadata={"check_type": "storage_connectivity"},
        )

    def is_healthy(self) -> bool:
        """Get cached health status - required by protocol"""
        return self._worker.is_healthy()
    