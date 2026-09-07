from __future__ import annotations

import asyncio
from collections import defaultdict

from .exceptions import (
    EventHandlerAlreadyRegistered,
    EventHandlerNotRegistered,
)
from .handler import EventHandler
from .models import EventType, InfrastructureEvent


class EventRouter:
    """
    Реестр подписок и маршрутизатор событий.

    Не хранит события.
    Не исполняет очередь.
    Только знает, каким обработчикам доставить событие.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, set[EventHandler]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        async with self._lock:
            if handler in self._handlers[event_type]:
                raise EventHandlerAlreadyRegistered(
                    f"{handler} already subscribed to {event_type.value}"
                )

            self._handlers[event_type].add(handler)

    async def unsubscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        async with self._lock:
            if handler not in self._handlers[event_type]:
                raise EventHandlerNotRegistered(
                    f"{handler} is not subscribed to {event_type.value}"
                )

            self._handlers[event_type].remove(handler)

    async def dispatch(
        self,
        event: InfrastructureEvent,
    ) -> list[tuple[EventHandler, Exception]]:
        """
        Доставляет событие всем обработчикам.

        Возвращает список ошибок обработчиков.
        """

        handlers = tuple(self._handlers.get(event.event_type, ()))

        if not handlers:
            return []

        results = await asyncio.gather(
            *(handler.handle(event) for handler in handlers),
            return_exceptions=True,
        )

        errors: list[tuple[EventHandler, Exception]] = []

        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                errors.append((handler, result))

        return errors