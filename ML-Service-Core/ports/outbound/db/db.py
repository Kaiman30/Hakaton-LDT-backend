# ports/outbound/db/db.py
"""
Database Interface - Strategy pattern implementation.
Uses DTOs from dto.py for type-safe communication.
"""

from typing import Optional, List, Dict, Any, AsyncIterator

from ports.outbound.db.dto import (
    QueryRequest,
    QueryResponse,
    ExecuteRequest,
    ExecuteResponse,
    TransactionRequest,
    TransactionResponse,
)
from ports.protocols import IDBConnector
from core.base_class.base_interface import BaseInterface
from core.registry import InterfaceRegistry
from core.runtime.event_bus import RuntimeEventBus


@InterfaceRegistry.register("DB")
class DBInterface(BaseInterface[IDBConnector], IDBConnector):
    """
    High-level interface for database operations.
    Implements Strategy pattern with DTO-based communication.
    """

    def __init__(
        self,
        worker: IDBConnector,
        name: Optional[str] = None,
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        super().__init__(worker, name, event_bus)

    @property
    def worker(self) -> IDBConnector:
        return self._worker

    # ============ IDBConnector Implementation ============

    async def query(self, request: QueryRequest) -> QueryResponse:
        """Execute SELECT with observability."""
        return await self._execute_with_tracking(
            "query",
            self._worker.query,
            request,
            metadata={
                "sql_preview": request.sql[:100],
                "has_params": bool(request.params),
                "fetch_size": request.fetch_size,
                "timeout": request.timeout,
            },
        )

    async def query_stream(self, request: QueryRequest) -> AsyncIterator[List[Dict[str, Any]]]:
        """Stream query results with observability."""
        async for chunk in self._execute_stream_with_tracking(
            "query_stream",
            self._worker.query_stream,
            request,
            metadata={
                "sql_preview": request.sql[:100],
                "chunk_size": request.fetch_size or 1000,
                "has_params": bool(request.params),
                "timeout": request.timeout,
            },
        ):
            yield chunk

    async def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        """Execute DML with observability."""
        return await self._execute_with_tracking(
            "execute",
            self._worker.execute,
            request,
            metadata={
                "sql_preview": request.sql[:100],
                "has_params": bool(request.params),
                "timeout": request.timeout,
            },
        )

    async def transaction(self, request: TransactionRequest) -> TransactionResponse:
        """Execute transaction with observability."""
        return await self._execute_with_tracking(
            "transaction",
            self._worker.transaction,
            request,
            metadata={
                "operations_count": len(request.operations),
                "isolation_level": request.isolation_level,
                "timeout": request.timeout,
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
            metadata={"check_type": "db_connectivity"},
        )

    async def initialize(self) -> None:
        await self._worker.initialize()

    async def shutdown(self) -> None:
        await self._worker.shutdown()