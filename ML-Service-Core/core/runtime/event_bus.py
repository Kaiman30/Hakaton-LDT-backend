# core/runtime/event_bus.py
"""
Lightweight asynchronous event bus for runtime observability and internal messaging.
Replaces heavy observer hierarchies with a clean pub-sub mechanism.
Free of configuration dependencies; uses injected or standard loggers.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set


class EventType(str, Enum):
    """Standard event types for observability."""
    OPERATION_STARTED = "operation.started"
    OPERATION_COMPLETED = "operation.completed"
    OPERATION_FAILED = "operation.failed"
    CONNECTOR_INITIALIZED = "connector.initialized"
    CONNECTOR_SHUTDOWN = "connector.shutdown"
    WORKER_SWITCHED = "worker.switched"
    HEALTH_CHECK = "health.check"
    
    # Custom events can be any string, these are just standards


EventCallback = Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None] | None]


class RuntimeEventBus:
    """Asynchronous event bus with middleware support."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        middlewares: Optional[List[Callable]] = None
    ) -> None:
        self._subscribers: Dict[str, Set[EventCallback]] = {}
        self._global_subscribers: Set[EventCallback] = set()
        self._logger = logger or logging.getLogger(__name__)
        self._middlewares = middlewares or []

    def use(self, middleware: Callable) -> None:
        """Add a middleware to the event bus."""
        self._middlewares.append(middleware)

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = set()
        self._subscribers[event_type].add(callback)

    def subscribe_all(self, callback: EventCallback) -> None:
        """Subscribe to all events."""
        self._global_subscribers.add(callback)

    def unsubscribe(self, event_type: str, callback: EventCallback) -> None:
        """Unsubscribe from event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type].discard(callback)

    async def publish(self, event_type: str, payload: Dict[str, Any] | None = None) -> None:
        """
        Publish an event asynchronously.
        All subscribers run in parallel, errors are isolated.
        """
        data = payload or {}
        handlers: List[EventCallback] = list(self._global_subscribers)
        
        if event_type in self._subscribers:
            handlers.extend(self._subscribers[event_type])

        if not handlers:
            return

        # Build middleware chain
        async def _deliver_to_handlers():
            tasks = []
            for handler in handlers:
                try:
                    if inspect.iscoroutinefunction(handler):
                        tasks.append(handler(event_type, data))
                    else:
                        handler(event_type, data)
                except Exception as e:
                    self._logger.error(f"Error scheduling event handler for '{event_type}': {e}")

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        self._logger.error(f"Error in event handler for '{event_type}': {res}")

        # Apply middlewares in reverse order
        async def _publish_with_middleware():
            # If no middlewares, deliver directly
            if not self._middlewares:
                await _deliver_to_handlers()
                return
            
            # Build middleware chain
            async def _next(index: int = 0):
                if index >= len(self._middlewares):
                    await _deliver_to_handlers()
                else:
                    await self._middlewares[index](event_type, data, lambda: _next(index + 1))
            
            await _next()

        await _publish_with_middleware()


# Global singleton
_global_event_bus: Optional[RuntimeEventBus] = None


def get_event_bus(
    logger: Optional[logging.Logger] = None,
    middlewares: Optional[List[Callable]] = None
) -> RuntimeEventBus:
    """Get global event bus instance."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = RuntimeEventBus(logger=logger, middlewares=middlewares)
    return _global_event_bus


# Convenience function to reset event bus (useful in tests)
def reset_event_bus() -> None:
    """Reset global event bus (primarily for testing)."""
    global _global_event_bus
    _global_event_bus = None