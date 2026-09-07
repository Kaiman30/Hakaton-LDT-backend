# ports/outbound/storage/storage.py
"""
Storage Interface - Strategy pattern implementation.
Uses DTOs from dto.py for type-safe communication.
"""

from typing import Optional, AsyncIterator

from ports.outbound.storage.dto import (
    UploadRequest,
    UploadResponse,
    DownloadRequest,
    DownloadResponse,
    DeleteRequest,
    DeleteResponse,
    ListRequest,
    ListResponse,
)
from ports.protocols import IFileStorageConnector
from core.base_class.base_interface import BaseInterface
from core.registry import InterfaceRegistry
from core.runtime.event_bus import RuntimeEventBus


@InterfaceRegistry.register("Storage")
class StorageInterface(BaseInterface[IFileStorageConnector], IFileStorageConnector):
    """
    High-level interface for storage operations.
    Implements Strategy pattern with DTO-based communication.
    """

    def __init__(
        self,
        worker: IFileStorageConnector,
        name: Optional[str] = None,
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        super().__init__(worker, name, event_bus)

    @property
    def worker(self) -> IFileStorageConnector:
        return self._worker

    # ============ IFileStorageConnector Implementation ============

    async def upload(self, request: UploadRequest) -> UploadResponse:
        """Upload with observability."""
        return await self._execute_with_tracking(
            "upload",
            self._worker.upload,
            request,
            metadata={
                "path": request.path,
                "has_metadata": bool(request.metadata),
                "bucket": request.bucket,
                "content_type": request.content_type,
                "part_size": request.part_size,
            },
        )

    async def download(self, request: DownloadRequest) -> DownloadResponse:
        """Download with observability."""
        return await self._execute_with_tracking(
            "download",
            self._worker.download,
            request,
            metadata={
                "path": request.path,
                "has_offset": request.offset is not None,
                "has_length": request.length is not None,
                "bucket": request.bucket,
                "version_id": request.version_id,
            },
        )

    async def download_stream(self, request: DownloadRequest) -> AsyncIterator[bytes]:
        """Download stream with observability."""
        async for chunk in self._execute_stream_with_tracking(
            "download_stream",
            self._worker.download_stream,
            request,
            metadata={
                "path": request.path,
                "bucket": request.bucket,
                "version_id": request.version_id,
            },
        ):
            yield chunk

    async def delete(self, request: DeleteRequest) -> DeleteResponse:
        """Delete with observability."""
        return await self._execute_with_tracking(
            "delete",
            self._worker.delete,
            request,
            metadata={
                "paths_count": len(request.paths),
                "recursive": request.recursive,
                "bucket": request.bucket,
            },
        )

    async def list_objects(self, request: ListRequest) -> ListResponse:
        """List with observability."""
        return await self._execute_with_tracking(
            "list_objects",
            self._worker.list_objects,
            request,
            metadata={
                "path": request.path,
                "recursive": request.recursive,
                "max_items": request.max_items,
                "bucket": request.bucket,
                "prefix": request.prefix,
                "delimiter": request.delimiter,
            },
        )

    # ============ Protocol Required ============

    @property
    def name(self) -> str:
        return self._name

    @property
    def healthy(self) -> bool:
        return self._worker.healthy

    async def check_health(self) -> bool:
        return await self._execute_with_tracking(
            "check_health",
            self._worker.check_health,
            metadata={"check_type": "storage_connectivity"},
        )

    async def initialize(self) -> None:
        await self._worker.initialize()

    async def shutdown(self) -> None:
        await self._worker.shutdown()