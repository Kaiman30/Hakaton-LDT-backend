# ports/protocols.py
"""
Protocol-based type definitions for all connectors.
Each protocol uses DTOs from corresponding ports.
"""

from typing import Protocol, runtime_checkable, AsyncIterator, Optional, List, Dict, Any

from core.base_class.base_protocol import BaseProtocol
from core.registry import ProtocolRegistry

# Inbound DTOs
from ports.inbound.broker.dto import (
    PublishRequest,
    PublishResponse,
    BatchPublishRequest,
    BatchPublishResponse,
    SubscribeRequest,
    ConsumeRequest,
    ConsumeResponse,
    CommitRequest,
    CommitResponse,
)
from ports.inbound.network.dto import HttpRequest, HttpResponse

# Outbound DTOs
from ports.outbound.db.dto import (
    QueryRequest,
    QueryResponse,
    ExecuteRequest,
    ExecuteResponse,
    TransactionRequest,
    TransactionResponse,
)
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


# ============================================================================
# BASE PROTOCOL (унифицирован)
# ============================================================================

@runtime_checkable
class BaseProtocolWithHealth(BaseProtocol):
    """
    Base protocol with unified lifecycle and health methods.
    """
    
    @property
    def name(self) -> str:
        """Connector name identifier."""
        ...
    
    async def initialize(self) -> None:
        """Initialize connector resources."""
        ...
    
    async def shutdown(self) -> None:
        """Cleanup connector resources."""
        ...
    
    async def check_health(self) -> bool:
        """
        Perform real remote health check.
        Renamed from health_check() for consistency.
        """
        ...
    
    @property
    def healthy(self) -> bool:
        """
        Get cached health status.
        Renamed from is_healthy() for consistency.
        """
        ...


# ============================================================================
# OUTBOUND PROTOCOLS (исходящие порты)
# ============================================================================

@ProtocolRegistry.register("ILLMConnector")
@runtime_checkable
class ILLMConnector(BaseProtocolWithHealth):
    """
    Protocol for LLM connectors.
    All methods use DTOs for type-safe communication.
    """

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion."""
        ...

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Stream chat completion."""
        ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Get embeddings for text(s)."""
        ...

    async def count_tokens(self, text: str) -> TokenCountResponse:
        """Count tokens in text."""
        ...

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        mime_type: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> FileUploadResponse:
        """Upload a file."""
        ...

    async def get_file_info(self, file_id: str) -> FileInfoResponse:
        """Get file information."""
        ...

    async def list_files(self) -> FilesListResponse:
        """List all uploaded files."""
        ...

    async def delete_file(self, file_id: str) -> bool:
        """Delete a file."""
        ...

    async def delete_files(self, file_ids: List[str]) -> DeleteFilesResponse:
        """Delete multiple files."""
        ...


@ProtocolRegistry.register("IQueueConnector")
@runtime_checkable
class IQueueConnector(BaseProtocolWithHealth):
    """
    Protocol for queue/broker connectors.
    All methods use DTOs for type-safe communication.
    """

    async def publish(self, request: PublishRequest) -> PublishResponse:
        """Publish a single message."""
        ...

    async def batch_publish(self, request: BatchPublishRequest) -> BatchPublishResponse:
        """Publish multiple messages."""
        ...

    async def subscribe(self, request: SubscribeRequest) -> None:
        """Subscribe to topics."""
        ...

    async def consume(self, request: ConsumeRequest) -> ConsumeResponse:
        """Consume messages from queue."""
        ...

    async def commit(self, request: CommitRequest) -> CommitResponse:
        """Commit consumed messages."""
        ...


@ProtocolRegistry.register("IFileStorageConnector")
@runtime_checkable
class IFileStorageConnector(BaseProtocolWithHealth):
    """
    Protocol for file/blob storage connectors.
    All methods use DTOs for type-safe communication.
    """

    async def upload(self, request: UploadRequest) -> UploadResponse:
        """Upload a file."""
        ...

    async def download(self, request: DownloadRequest) -> DownloadResponse:
        """Download a file."""
        ...

    async def download_stream(self, request: DownloadRequest) -> AsyncIterator[bytes]:
        """Download a file as stream."""
        ...

    async def delete(self, request: DeleteRequest) -> DeleteResponse:
        """Delete files."""
        ...

    async def list_objects(self, request: ListRequest) -> ListResponse:
        """List objects in storage."""
        ...


@ProtocolRegistry.register("IDBConnector")
@runtime_checkable
class IDBConnector(BaseProtocolWithHealth):
    """
    Protocol for database connectors.
    All methods use DTOs for type-safe communication.
    """

    async def query(self, request: QueryRequest) -> QueryResponse:
        """Execute a SELECT query."""
        ...

    async def query_stream(self, request: QueryRequest) -> AsyncIterator[List[Dict[str, Any]]]:
        """Execute a SELECT query and stream results."""
        ...

    async def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        """Execute a DML query (INSERT/UPDATE/DELETE)."""
        ...

    async def transaction(self, request: TransactionRequest) -> TransactionResponse:
        """Execute a transaction."""
        ...


@ProtocolRegistry.register("IHTTPConnector")
@runtime_checkable
class IHTTPConnector(BaseProtocolWithHealth):
    """
    Protocol for HTTP connectors.
    All methods use DTOs for type-safe communication.
    """

    async def request(self, request: HttpRequest) -> HttpResponse:
        """Execute an HTTP request."""
        ...

    async def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> HttpResponse:
        """Execute GET request."""
        ...

    async def post(self, url: str, data: Optional[Dict[str, Any]] = None) -> HttpResponse:
        """Execute POST request."""
        ...

    async def put(self, url: str, data: Optional[Dict[str, Any]] = None) -> HttpResponse:
        """Execute PUT request."""
        ...

    async def delete(self, url: str) -> HttpResponse:
        """Execute DELETE request."""
        ...