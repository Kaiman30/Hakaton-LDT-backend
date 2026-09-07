# ports/outbound/ml/llm/llm.py
"""
LLM Interface - Strategy pattern implementation.
Uses DTOs from dto.py for type-safe communication.
"""

from typing import Optional, AsyncIterator, List

from ports.outbound.ml.llm.dto import (
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    TokenCountResponse,
    FileUploadResponse,
    FileInfoResponse,
    FilesListResponse,
    DeleteFilesResponse,
)
from ports.protocols import ILLMConnector
from core.base_class.base_interface import BaseInterface
from core.registry import InterfaceRegistry
from core.runtime.event_bus import RuntimeEventBus


@InterfaceRegistry.register("LLM")
class LLMInterface(BaseInterface[ILLMConnector], ILLMConnector):
    """
    High-level interface for LLM operations.
    Implements Strategy pattern with DTO-based communication.
    """

    def __init__(
        self,
        worker: ILLMConnector,
        name: Optional[str] = None,
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        super().__init__(worker, name, event_bus)

    @property
    def worker(self) -> ILLMConnector:
        return self._worker

    # ============ ILLMConnector Implementation ============

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Chat with observability."""
        return await self._execute_with_tracking(
            "chat",
            self._worker.chat,
            request,
            metadata={
                "messages_count": len(request.messages),
                "model": request.model,
                "temperature": request.temperature,
                "stream": request.stream,
                "has_tools": bool(request.tools),
            },
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Stream chat with observability."""
        async for chunk in self._execute_stream_with_tracking(
            "stream",
            self._worker.stream,
            request,
            metadata={
                "messages_count": len(request.messages),
                "model": request.model,
                "temperature": request.temperature,
                "has_tools": bool(request.tools),
            },
        ):
            yield chunk

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Get embeddings with observability."""
        return await self._execute_with_tracking(
            "embed",
            self._worker.embed,
            request,
            metadata={
                "input_type": "string" if isinstance(request.input, str) else "list",
                "model": request.model,
                "dimensions": request.dimensions,
            },
        )

    async def count_tokens(self, text: str) -> TokenCountResponse:
        """Count tokens with observability."""
        return await self._execute_with_tracking(
            "count_tokens",
            self._worker.count_tokens,
            text,
            metadata={
                "text_length": len(text),
                "text_preview": text[:100],
            },
        )

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        mime_type: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> FileUploadResponse:
        """Upload file with observability."""
        return await self._execute_with_tracking(
            "upload_file",
            self._worker.upload_file,
            file_data,
            filename,
            mime_type,
            timeout,
            metadata={
                "filename": filename,
                "mime_type": mime_type,
                "file_size": len(file_data),
                "timeout": timeout,
            },
        )

    async def get_file_info(self, file_id: str) -> FileInfoResponse:
        """Get file info with observability."""
        return await self._execute_with_tracking(
            "get_file_info",
            self._worker.get_file_info,
            file_id,
            metadata={"file_id": file_id},
        )

    async def list_files(self) -> FilesListResponse:
        """List files with observability."""
        return await self._execute_with_tracking(
            "list_files",
            self._worker.list_files,
            metadata={"operation": "list_all"},
        )

    async def delete_file(self, file_id: str) -> bool:
        """Delete file with observability."""
        return await self._execute_with_tracking(
            "delete_file",
            self._worker.delete_file,
            file_id,
            metadata={"file_id": file_id},
        )

    async def delete_files(self, file_ids: List[str]) -> DeleteFilesResponse:
        """Delete multiple files with observability."""
        return await self._execute_with_tracking(
            "delete_files",
            self._worker.delete_files,
            file_ids,
            metadata={"files_count": len(file_ids)},
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
            metadata={"check_type": "llm_connectivity"},
        )

    async def initialize(self) -> None:
        await self._worker.initialize()

    async def shutdown(self) -> None:
        await self._worker.shutdown()