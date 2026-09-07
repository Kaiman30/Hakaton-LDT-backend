# core/base_class/base_interface.py
"""
Base interface classes implementing Strategy pattern.
Provides automatic operation tracking, timing, and event publishing via RuntimeEventBus.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, AsyncIterator, TypeVar, Generic

from core.base_class.base_protocol import BaseProtocol
from core.runtime.event_bus import RuntimeEventBus, EventType, get_event_bus

# Type variable for worker protocol - must be a subclass of BaseProtocol
T = TypeVar('T', bound=BaseProtocol)


class BaseInterface(ABC, Generic[T]):
    """
    Base class for all interfaces.
    
    Implements Strategy pattern - can switch between different worker implementations.
    Provides automatic operation tracking and event publishing for observability.
    
    Generic parameter T defines the worker protocol type.
    """

    def __init__(
        self,
        worker: T,
        name: Optional[str] = None,
        event_bus: Optional[RuntimeEventBus] = None,
    ):
        """
        Initialize interface with worker.

        Args:
            worker: Connector instance (worker) implementing BaseProtocol
            name: Interface name (defaults to worker name)
            event_bus: Optional runtime event bus for observability
        """
        self._worker: T = worker
        self._name: str = name or getattr(worker, "name", "unknown")
        self._event_bus: RuntimeEventBus = event_bus or get_event_bus()

    @property
    def name(self) -> str:
        """Interface name."""
        return self._name

    @property
    def worker(self) -> T:
        """Get underlying worker."""
        return self._worker

    def switch_worker(self, new_worker: T) -> None:
        """
        Switch to different worker implementation (Strategy pattern).

        Args:
            new_worker: New connector to use
        """
        old_name = getattr(self._worker, "name", "unknown")
        self._worker = new_worker
        new_name = getattr(new_worker, "name", "unknown")

        # Publish switch event
        payload = {
            "interface_name": self._name,
            "old_worker": old_name,
            "new_worker": new_name,
        }
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    self._event_bus.publish(EventType.WORKER_SWITCHED, payload)
                )
        except RuntimeError:
            pass

    async def _publish_connector_event(
        self,
        event_type: EventType,
        operation_name: str,
        success: bool = True,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Publish structured connector event to RuntimeEventBus.
        
        Args:
            event_type: Type of event (started, completed, failed)
            operation_name: Name of the operation
            success: Whether operation succeeded
            error: Error message if failed
            duration_ms: Operation duration in milliseconds
            metadata: Additional metadata
        """
        payload = {
            "connector_name": getattr(self._worker, "name", "unknown"),
            "interface_name": self._name,
            "operation_name": operation_name,
            "success": success,
            "error": error,
            "duration_ms": duration_ms,
            "metadata": metadata or {},
        }
        await self._event_bus.publish(event_type, payload)

    async def _execute_with_tracking(
        self,
        operation_name: str,
        operation: Any,
        *args: Any,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute async operation with automatic event tracking and execution timing.
        
        Args:
            operation_name: Name of operation for tracking
            operation: Async callable to execute
            *args: Positional arguments for operation
            metadata: Additional metadata for events
            **kwargs: Keyword arguments for operation
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: Propagates any exception from operation
        """
        start_time = time.perf_counter()

        # Publish started event
        await self._publish_connector_event(
            EventType.OPERATION_STARTED,
            operation_name,
            metadata=metadata,
        )

        try:
            result = await operation(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Publish completed event
            await self._publish_connector_event(
                EventType.OPERATION_COMPLETED,
                operation_name,
                success=True,
                duration_ms=duration_ms,
                metadata=metadata,
            )

            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Publish failed event
            await self._publish_connector_event(
                EventType.OPERATION_FAILED,
                operation_name,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
                metadata=metadata,
            )

            raise

    async def _execute_stream_with_tracking(
        self,
        operation_name: str,
        stream_operation: Any,
        *args: Any,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator:
        """
        Execute async streaming operation with automatic event tracking.
        Yields chunks and tracks completion/failure.
        
        Args:
            operation_name: Name of operation for tracking
            stream_operation: Async callable returning AsyncIterator
            *args: Positional arguments for operation
            metadata: Additional metadata for events
            **kwargs: Keyword arguments for operation
            
        Yields:
            Chunks from the stream
            
        Raises:
            Exception: Propagates any exception from operation
        """
        start_time = time.perf_counter()
        chunk_count = 0
        success = True
        error = None

        # Publish started event
        await self._publish_connector_event(
            EventType.OPERATION_STARTED,
            operation_name,
            metadata=metadata,
        )

        try:
            stream = await stream_operation(*args, **kwargs)
            async for chunk in stream:
                chunk_count += 1
                yield chunk

        except Exception as e:
            success = False
            error = str(e)
            raise

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Publish completion/failure event
            event_type = EventType.OPERATION_COMPLETED if success else EventType.OPERATION_FAILED
            await self._publish_connector_event(
                event_type,
                operation_name,
                success=success,
                error=error,
                duration_ms=duration_ms,
                metadata={
                    **(metadata or {}),
                    "chunk_count": chunk_count,
                },
            )

    # ============ Lifecycle Methods (унифицированные имена) ============

    async def initialize(self) -> None:
        """Initialize underlying worker."""
        await self._execute_with_tracking("initialize", self._worker.initialize)

    async def shutdown(self) -> None:
        """Shutdown underlying worker."""
        await self._execute_with_tracking("shutdown", self._worker.shutdown)

    @property
    def healthy(self) -> bool:
        """Get cached health status."""
        return self._worker.healthy

    async def check_health(self) -> bool:
        """Check worker health."""
        try:
            result = await self._execute_with_tracking(
                "check_health", self._worker.check_health
            )
            return result
        except Exception:
            return False