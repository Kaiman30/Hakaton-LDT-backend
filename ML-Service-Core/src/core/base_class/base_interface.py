"""
Base interface classes implementing Strategy pattern.

Interfaces provide abstraction over workers (connectors) and allow
switching between different implementations transparently.
"""
from __future__ import annotations

from abc import ABC
from typing import Any, Callable, Awaitable, Optional
import time

from core.base_class.base_connectors import BaseConnector
from utils.observer import (
    UnifiedPublisher,
    ConnectorEvent,
    EventType,
)


class BaseInterface(ABC):
    """
    Base class for all interfaces.
    
    Implements Strategy pattern - can switch between different worker implementations.
    Provides event publishing for observability.
    """

    def __init__(
        self,
        worker: BaseConnector,
        name: Optional[str] = None,
        publisher: Optional[UnifiedPublisher] = None,
    ):
        """
        Initialize interface with worker.

        Args:
            worker: Connector instance (worker) to use
            name: Interface name (defaults to worker name)
            publisher: Optional event publisher for observability
        """
        self._worker = worker
        self._name = name or worker.name
        self._publisher = publisher

    @property
    def name(self) -> str:
        """Interface name"""
        return self._name

    @property
    def worker(self) -> BaseConnector:
        """Get underlying worker"""
        return self._worker

    def switch_worker(self, new_worker: BaseConnector) -> None:
        """
        Switch to different worker implementation (Strategy pattern).

        Args:
            new_worker: New connector to use
        """
        old_name = self._worker.name
        self._worker = new_worker
        if self._publisher:
            self._publisher.emit_sync(ConnectorEvent(
                event_type=EventType.OPERATION_COMPLETED,
                source=f"{self._name}.switch_worker",
                action="switch_worker",
                metadata={"old_worker": old_name, "new_worker": new_worker.name},
            ))

    async def _publish_event(
        self,
        event_type: EventType,
        operation_name: str,
        success: bool = True,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Publish event through unified publisher."""
        if not self._publisher:
            return

        self._publisher.emit_sync(ConnectorEvent(
            event_type=event_type,
            source=f"{self._name}.{operation_name}",
            action=operation_name,
            success=success,
            error=error,
            duration_ms=duration_ms,
            metadata=metadata or {},
        ))

    async def _execute_with_tracking(
        self,
        operation_name: str,
        operation: Callable[..., Awaitable[Any]],
        *args: Any,
        metadata: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute async operation with event tracking.

        Args:
            operation_name: Name of operation for logging
            operation: Async callable to execute
            *args: Arguments for operation
            metadata: Optional metadata to include in event
            **kwargs: Keyword arguments for operation

        Returns:
            Result of operation
        """
        start_time = time.perf_counter()

        await self._publish_event(EventType.OPERATION_STARTED, operation_name)

        try:
            result = await operation(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000

            await self._publish_event(
                EventType.OPERATION_COMPLETED,
                operation_name,
                success=True,
                duration_ms=duration_ms,
                metadata=metadata or {},
            )

            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            await self._publish_event(
                EventType.OPERATION_FAILED,
                operation_name,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

            raise

    # Lifecycle methods (delegated to worker)

    async def initialize(self) -> None:
        """Initialize underlying worker"""
        await self._execute_with_tracking("initialize", self._worker.initialize)

    async def shutdown(self) -> None:
        """Shutdown underlying worker"""
        await self._execute_with_tracking("shutdown", self._worker.shutdown)

    async def health_check(self) -> bool:
        """Check worker health"""
        try:
            result = await self._execute_with_tracking(
                "health_check", self._worker.health_check
            )
            return result
        except Exception:
            return False

    def is_healthy(self) -> bool:
        """Get cached health status"""
        return self._worker.is_healthy()
