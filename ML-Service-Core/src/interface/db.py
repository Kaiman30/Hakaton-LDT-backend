"""
Database Interface - Strategy pattern implementation for DB connectors.

Allows switching between different database providers (PostgreSQL, MySQL, etc.)
while maintaining the same API.
"""

from typing import Any, Dict, List, Optional, AsyncGenerator

from utils.observer import EventPublisher
from core.base_class.protocols import IDBConnector
from core.base_class.base_interface import BaseInterface
from core.registry import register_interface


@register_interface("DB")
class DBInterface(BaseInterface, IDBConnector):  # ← ДОБАВЛЯЕМ протокол!
    """
    High-level interface for database operations.

    Implements Strategy pattern - can switch between different DB providers
    (PostgreSQL, MySQL, etc.) transparently.
    """

    def __init__(
        self,
        worker: IDBConnector,
        name: Optional[str] = None,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        """
        Initialize DB interface.

        Args:
            worker: DB connector instance (e.g., PGConnector)
            name: Interface name (defaults to worker name)
            event_publisher: Optional event publisher for observability
        """
        super().__init__(worker, name, event_publisher)

    @property
    def worker(self) -> IDBConnector:
        """Get underlying DB connector"""
        return self._worker

    # ============ IDBConnector protocol implementation ============

    async def load(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return list of rows.

        Args:
            query: SQL SELECT query
            *args: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        return await self._execute_with_tracking(
            "load",
            self._worker.load,
            query,
            *args,
            metadata={
                "query": query[:100],
                "query_type": "select",
                "param_count": len(args),
            },
        )

    async def load_one(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """
        Execute SELECT query and return single row.

        Args:
            query: SQL SELECT query
            *args: Query parameters

        Returns:
            Single result row as dictionary or None
        """
        return await self._execute_with_tracking(
            "load_one",
            self._worker.load_one,
            query,
            *args,
            metadata={
                "query": query[:100],
                "query_type": "select_one",
                "param_count": len(args),
            },
        )

    async def load_scalar(self, query: str, *args: Any) -> Any:
        """
        Execute SELECT query and return single scalar value.

        Args:
            query: SQL SELECT query
            *args: Query parameters

        Returns:
            Single scalar value
        """
        return await self._execute_with_tracking(
            "load_scalar",
            self._worker.load_scalar,
            query,
            *args,
            metadata={
                "query": query[:100],
                "query_type": "scalar",
                "param_count": len(args),
            },
        )

    async def execute(self, query: str, *args: Any, **kwargs: Any) -> str:
        """
        Execute DML query (INSERT/UPDATE/DELETE).

        Args:
            query: SQL DML query
            *args: Query parameters
            **kwargs: Additional keyword arguments

        Returns:
            Command result
        """
        return await self._execute_with_tracking(
            "execute",
            self._worker.execute,
            query,
            *args,
            **kwargs,
            metadata={
                "query": query[:100],
                "query_type": "dml",
                "param_count": len(args),
            },
        )

    async def execute_many(self, query: str, args_list: List[tuple]) -> str:
        """
        Execute query multiple times with different parameters.

        Args:
            query: SQL query to execute
            args_list: List of parameter tuples

        Returns:
            Command result
        """
        return await self._execute_with_tracking(
            "execute_many",
            self._worker.execute_many,
            query,
            args_list,
            metadata={
                "query": query[:100],
                "query_type": "batch_dml",
                "batch_count": len(args_list),
            },
        )

    async def load_stream(
        self,
        query: str,
        *args: Any,
        chunk_size: int = 1000,
    ) -> AsyncGenerator[List[Dict[str, Any]], None]:
        """
        Stream large result sets in chunks.

        Args:
            query: SQL SELECT query
            *args: Query parameters
            chunk_size: Number of rows per chunk

        Yields:
            Chunks of result rows as dictionaries
        """
        # Получаем stream из worker'а
        stream = await self._worker.load_stream(query, *args, chunk_size=chunk_size)
        
        # Оборачиваем в трекинг
        async for chunk in stream:
            await self._publish_event_for_chunk(chunk)
            yield chunk

    async def _publish_event_for_chunk(self, chunk: List[Dict[str, Any]]) -> None:
        """Вспомогательный метод для отправки событий о чанках"""
        if self._event_publisher:
            from utils.observer import ConnectorEvent, EventType
            event = ConnectorEvent(
                event_type=EventType.OPERATION_PROGRESS,
                connector_name=self._worker.name,
                interface_name=self._name,
                operation_name="load_stream_chunk",
                success=True,
                metadata={
                    "chunk_size": len(chunk),
                    "rows_processed": len(chunk),
                },
            )
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._event_publisher.publish(event))
            except RuntimeError:
                pass

    async def load_concurrent(
        self,
        queries: List[tuple],
    ) -> List[List[Dict[str, Any]]]:
        """
        Execute multiple SELECT queries concurrently.

        Args:
            queries: List of (query, *args) tuples

        Returns:
            List of result lists (one per query)
        """
        return await self._execute_with_tracking(
            "load_concurrent",
            self._worker.load_concurrent,
            queries,
            metadata={
                "query_count": len(queries),
                "operation": "concurrent_load",
            },
        )

    async def load_with_thread_pool(
        self,
        queries: List[tuple],
    ) -> List[List[Dict[str, Any]]]:
        """
        Load data using thread pool executor.

        Args:
            queries: List of (query, *args) tuples

        Returns:
            List of result lists
        """
        return await self._execute_with_tracking(
            "load_with_thread_pool",
            self._worker.load_with_thread_pool,
            queries,
            metadata={
                "query_count": len(queries),
                "operation": "thread_pool_load",
            },
        )

    async def bulk_insert(
        self,
        table: str,
        columns: List[str],
        rows: List[tuple],
        batch_size: int = 1000,
    ) -> int:
        """
        Perform bulk insert with batching.

        Args:
            table: Target table name
            columns: Column names
            rows: List of row tuples to insert
            batch_size: Number of rows per batch

        Returns:
            Total number of inserted rows
        """
        return await self._execute_with_tracking(
            "bulk_insert",
            self._worker.bulk_insert,
            table,
            columns,
            rows,
            batch_size,
            metadata={
                "table": table,
                "columns_count": len(columns),
                "rows_count": len(rows),
                "batch_size": batch_size,
            },
        )

    async def load_to_buffer(
        self,
        query: str,
        *args: Any,
        format: str = "csv",
    ) -> Any:  # io.BytesIO
        """
        Load query results to in-memory buffer.

        Args:
            query: SQL SELECT query
            *args: Query parameters
            format: Output format ('csv' or 'json')

        Returns:
            BytesIO buffer with formatted data
        """
        return await self._execute_with_tracking(
            "load_to_buffer",
            self._worker.load_to_buffer,
            query,
            *args,
            format=format,
            metadata={
                "query": query[:100],
                "format": format,
                "operation": "load_to_buffer",
            },
        )

    async def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get connection pool statistics.

        Returns:
            Dictionary with pool statistics
        """
        return await self._execute_with_tracking(
            "get_pool_stats",
            self._worker.get_pool_stats,
            metadata={"info_type": "pool_stats"},
        )

    # ============ Convenience methods (not part of protocol) ============

    async def select(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """Alias for load - for backward compatibility"""
        return await self.load(query, *args)

    async def select_one(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Alias for load_one - for backward compatibility"""
        return await self.load_one(query, *args)

    # ============ Protocol required methods ============

    @property
    def name(self) -> str:
        """Get connector name - required by IDBConnector protocol"""
        return self._name

    async def health_check(self) -> bool:
        """Check database connectivity - required by protocol"""
        return await self._execute_with_tracking(
            "health_check",
            self._worker.health_check,
            metadata={"check_type": "db_connectivity"},
        )

    def is_healthy(self) -> bool:
        """Get cached health status - required by protocol"""
        return self._worker.is_healthy()