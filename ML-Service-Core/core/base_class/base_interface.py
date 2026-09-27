from __future__ import annotations

import asyncio
import time
from abc import ABC
from typing import Any, Optional, Dict, AsyncIterator, TypeVar, Generic

from core.base_class.base_protocol import BaseProtocol
from core.runtime.event_bus import RuntimeEventBus, EventType, get_event_bus

T = TypeVar('T', bound=BaseProtocol)

class BaseInterface(ABC, Generic[T]):
    """
    Base class for all interfaces (Strategy + Decorator pattern for observability).
    """

    def __init__(
        self,
        worker: T,
        name: Optional[str] = None,
        event_bus: Optional[RuntimeEventBus] = None,
    ):
        self._worker: T = worker
        self._name: str = name or getattr(worker, "name", "unknown")
        self._event_bus: RuntimeEventBus = event_bus or get_event_bus()
        self._background_tasks: set[asyncio.Task] = set()  # Защита от Garbage Collection

    @property
    def name(self) -> str:
        return self._name

    @property
    def worker(self) -> T:
        return self._worker

    def switch_worker(self, new_worker: T) -> None:
        """Switch to different worker implementation (Strategy pattern)."""
        old_name = getattr(self._worker, "name", "unknown")
        self._worker = new_worker
        new_name = getattr(new_worker, "name", "unknown")

        payload = {
            "interface_name": self._name,
            "old_worker": old_name,
            "new_worker": new_name,
        }
        
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._event_bus.publish(EventType.WORKER_SWITCHED, payload)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            # Вызывается вне асинхронного контекста (например, при старте приложения)
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
        start_time = time.perf_counter()
        await self._publish_connector_event(
            EventType.OPERATION_STARTED, operation_name, metadata=metadata
        )

        try:
            result = await operation(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000

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
        start_time = time.perf_counter()
        chunk_count = 0
        success = True
        error = None

        await self._publish_connector_event(
            EventType.OPERATION_STARTED, operation_name, metadata=metadata
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
            event_type = EventType.OPERATION_COMPLETED if success else EventType.OPERATION_FAILED
            await self._publish_connector_event(
                event_type,
                operation_name,
                success=success,
                error=error,
                duration_ms=duration_ms,
                metadata={**(metadata or {}), "chunk_count": chunk_count},
            )
    
    # ============ Lifecycle Methods ============

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
            return await self._execute_with_tracking(
                "check_health", self._worker.check_health
            )
        except Exception:
            return False