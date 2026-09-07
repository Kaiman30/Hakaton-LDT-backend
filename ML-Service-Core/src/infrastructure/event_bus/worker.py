from __future__ import annotations

import asyncio

from .handler import EventHandler
from .models import InfrastructureEvent
from .event_router import EventRouter


class EventWorker:
    """
    Асинхронный consumer очереди Infrastructure Event Bus.

    Не знает о EventBus и не публикует новые события.
    Его единственная задача — передать событие в EventRouter.
    """

    def __init__(
        self,
        router: EventRouter,
    ) -> None:
        self._router = router

    async def process(
        self,
        event: InfrastructureEvent,
    ) -> list[tuple[EventHandler, Exception]]:
        """
        Обработать одно событие и вернуть ошибки обработчиков.
        """
        return await self._router.dispatch(event)