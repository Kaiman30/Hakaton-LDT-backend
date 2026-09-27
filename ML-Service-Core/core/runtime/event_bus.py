# core/runtime/event_bus.py
"""
Asynchronous pub-sub event bus for runtime observability and internal messaging.

Principles:
- The bus itself logs EVERY published event (even if nobody is subscribed),
  so it is the single observation point of the runtime.
- Handlers are isolated: a failing or hanging handler can neither break the
  publisher nor other handlers.
- An event may carry a ``source`` (usually a service name). Subscribers can filter
  by it, so metrics for a single object are a one-liner:
      bus.subscribe_all(collect, source="llm")
- Middlewares wrap delivery (metrics, tracing, filtering) and are fail-open:
  a crashing middleware never swallows an event.
- Free of configuration dependencies; uses injected or standard loggers.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Union


class EventType(str, Enum):
    """Standard event types for observability."""
    OPERATION_STARTED = "operation.started"
    OPERATION_COMPLETED = "operation.completed"
    OPERATION_FAILED = "operation.failed"
    CONNECTOR_INITIALIZED = "connector.initialized"
    CONNECTOR_SHUTDOWN = "connector.shutdown"
    WORKER_SWITCHED = "worker.switched"
    HEALTH_CHECK = "health.check"

    # Lifecycle events of the runtime layer
    SERVICE_STATE_CHANGED = "service.state_changed"
    PIPELINE_STATE_CHANGED = "pipeline.state_changed"

    # Custom events can be any string, these are just standards


Payload = Dict[str, Any]
EventCallback = Callable[[str, Payload], Union[Awaitable[None], None]]
Middleware = Callable[
    [str, Payload, Callable[[], Awaitable[None]]],
    Union[Awaitable[None], None],
]

_MAX_LOGGED_PAYLOAD = 300


def _event_key(event_type: Union[str, Enum]) -> str:
    """Normalize Enum / str event types to a plain str (stable for dict keys and logs)."""
    return event_type.value if isinstance(event_type, Enum) else str(event_type)


def _short(data: Payload) -> str:
    text = repr(data)
    if len(text) <= _MAX_LOGGED_PAYLOAD:
        return text
    return text[:_MAX_LOGGED_PAYLOAD] + "...(truncated)"


@dataclass(frozen=True)
class _Subscription:
    callback: EventCallback
    source: Optional[str] = None  # None = events from any source

    def matches(self, source: Optional[str]) -> bool:
        return self.source is None or self.source == source


class RuntimeEventBus:
    """Asynchronous event bus with middleware support."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        middlewares: Optional[Sequence[Middleware]] = None,
        *,
        log_level: int = logging.DEBUG,
        handler_timeout: Optional[float] = 5.0,
    ) -> None:
        """
        Args:
            logger: Logger for event log and bus errors
            middlewares: Initial middlewares (copied, the caller's list is not shared)
            log_level: Level at which every event is logged
                       (events ending with '.failed' are logged as WARNING)
            handler_timeout: Max seconds an async handler may run; None = no limit.
                             Sync handlers cannot be interrupted and must be fast.
        """
        self._subscribers: Dict[str, List[_Subscription]] = {}
        self._global_subscribers: List[_Subscription] = []
        self._logger = logger or logging.getLogger(__name__)
        self._middlewares: List[Middleware] = list(middlewares or [])
        self._log_level = log_level
        self._handler_timeout = handler_timeout

    # ==================== SUB`s ====================

    def use(self, middleware: Middleware) -> None:
        """Add a middleware to the event bus."""
        self._middlewares.append(middleware)

    def remove_middleware(self, middleware: Middleware) -> None:
        """Remove a previously added middleware (e.g. to detach metrics)."""
        if middleware in self._middlewares:
            self._middlewares.remove(middleware)

    def subscribe(
        self,
        event_type: Union[str, Enum],
        callback: EventCallback,
        *,
        source: Optional[str] = None,
    ) -> None:
        """Subscribe to a specific event type (optionally only from one source)."""
        subs = self._subscribers.setdefault(_event_key(event_type), [])
        sub = _Subscription(callback, source)
        if sub not in subs:
            subs.append(sub)

    def subscribe_all(
        self,
        callback: EventCallback,
        *,
        source: Optional[str] = None,
    ) -> None:
        """Subscribe to all events (optionally only from one source)."""
        sub = _Subscription(callback, source)
        if sub not in self._global_subscribers:
            self._global_subscribers.append(sub)

    def unsubscribe(
        self,
        event_type: Union[str, Enum],
        callback: EventCallback,
        *,
        source: Optional[str] = None,
    ) -> None:
        """Unsubscribe from an event type. source=None removes the callback for any source."""
        key = _event_key(event_type)
        subs = self._subscribers.get(key)
        if subs is not None:
            self._subscribers[key] = self._without(subs, callback, source)

    def unsubscribe_all(
        self,
        callback: EventCallback,
        *,
        source: Optional[str] = None,
    ) -> None:
        """Remove a subscribe_all() subscription."""
        self._global_subscribers = self._without(self._global_subscribers, callback, source)

    @staticmethod
    def _without(
        subs: List[_Subscription], callback: EventCallback, source: Optional[str]
    ) -> List[_Subscription]:
        return [
            s for s in subs
            if not (s.callback == callback and (source is None or s.source == source))
        ]

    def scoped(self, source: str) -> "ScopedEventBus":
        """A view of this bus that stamps every event with ``source``."""
        return ScopedEventBus(self, source)

    # ==================== ПУБЛИКАЦИЯ ====================

    async def publish(
        self,
        event_type: Union[str, Enum],
        payload: Optional[Payload] = None,
        *,
        source: Optional[str] = None,
    ) -> None:
        """
        Publish an event.

        The event is logged first, then passes through middlewares, then is delivered
        to all matching handlers concurrently. Handler and middleware errors are
        logged and never propagate to the publisher.

        Args:
            event_type: EventType member or any string
            payload: Event data (copied; 'source' is a reserved key)
            source: Who publishes the event (stored in payload['source'])
        """
        key = _event_key(event_type)
        data: Payload = dict(payload) if payload else {}
        if source is not None:
            data["source"] = source

        self._log_event(key, data)
        await self._dispatch(key, data, tuple(self._middlewares), 0)

    def _log_event(self, key: str, data: Payload) -> None:
        level = logging.WARNING if key.endswith(".failed") else self._log_level
        if self._logger.isEnabledFor(level):
            self._logger.log(
                level, "event=%s source=%s payload=%s", key, data.get("source"), _short(data)
            )

    async def _dispatch(
        self, key: str, data: Payload, middlewares: Sequence[Middleware], index: int
    ) -> None:
        """Run middleware chain (in registration order), then deliver."""
        if index >= len(middlewares):
            await self._deliver(key, data)
            return

        middleware = middlewares[index]
        called_next = False

        async def call_next() -> None:
            nonlocal called_next
            called_next = True
            await self._dispatch(key, data, middlewares, index + 1)

        try:
            result = middleware(key, data, call_next)
            if inspect.isawaitable(result):
                await result
        except Exception:
            self._logger.exception("Middleware %r failed for event '%s'", middleware, key)
            # Fail-open: if the middleware died before passing the event on, do it for it
            if not called_next:
                await call_next()

    async def _deliver(self, key: str, data: Payload) -> None:
        source = data.get("source")
        handlers = [s.callback for s in self._global_subscribers if s.matches(source)]
        handlers += [s.callback for s in self._subscribers.get(key, ()) if s.matches(source)]

        if not handlers:
            return

        # Each handler gets its own shallow copy so one cannot corrupt data for another
        await asyncio.gather(
            *(self._call_handler(h, key, dict(data)) for h in handlers)
        )

    async def _call_handler(self, handler: EventCallback, key: str, data: Payload) -> None:
        """Call a sync or async handler; never raises (except cancellation)."""
        try:
            result = handler(key, data)
            if inspect.isawaitable(result):
                if self._handler_timeout is None:
                    await result
                else:
                    await asyncio.wait_for(result, self._handler_timeout)
        except asyncio.TimeoutError:
            self._logger.error(
                "Event handler %r timed out (%ss) on '%s'", handler, self._handler_timeout, key
            )
        except Exception:
            self._logger.exception("Error in event handler %r for event '%s'", handler, key)


class ScopedEventBus:
    """
    A bus view bound to one source (usually a service name).

    - publish() stamps events with the source;
    - subscribe() receives only events of this source.
    """

    def __init__(self, bus: RuntimeEventBus, source: str) -> None:
        self._bus = bus
        self._source = source

    @property
    def source(self) -> str:
        return self._source

    async def publish(
        self, event_type: Union[str, Enum], payload: Optional[Payload] = None
    ) -> None:
        await self._bus.publish(event_type, payload, source=self._source)

    def subscribe(self, event_type: Union[str, Enum], callback: EventCallback) -> None:
        self._bus.subscribe(event_type, callback, source=self._source)

    def subscribe_all(self, callback: EventCallback) -> None:
        self._bus.subscribe_all(callback, source=self._source)

    def unsubscribe(self, event_type: Union[str, Enum], callback: EventCallback) -> None:
        self._bus.unsubscribe(event_type, callback, source=self._source)

    def unsubscribe_all(self, callback: EventCallback) -> None:
        self._bus.unsubscribe_all(callback, source=self._source)


# Global singleton
_global_event_bus: Optional[RuntimeEventBus] = None


def get_event_bus(
    logger: Optional[logging.Logger] = None,
    middlewares: Optional[Sequence[Middleware]] = None,
) -> RuntimeEventBus:
    """
    Get global event bus instance.

    Arguments are used only when the bus is created; later they are ignored
    with a warning (use bus.use() to add middlewares afterwards).
    """
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = RuntimeEventBus(logger=logger, middlewares=middlewares)
    elif logger is not None or middlewares is not None:
        logging.getLogger(__name__).warning(
            "get_event_bus(): bus already exists, logger/middlewares arguments are ignored"
        )
    return _global_event_bus


# Convenience function to reset event bus (useful in tests)
def reset_event_bus() -> None:
    """Reset global event bus (primarily for testing)."""
    global _global_event_bus
    _global_event_bus = None