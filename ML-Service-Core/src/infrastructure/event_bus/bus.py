from __future__ import annotations

import asyncio

from .handler import EventHandler
from .models import EventType, InfrastructureEvent
from .event_router import EventRouter
from .worker import EventWorker


class InfrastructureEventBus:
    """
    Централизованная шина инфраструктурных событий.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[InfrastructureEvent] = asyncio.Queue()

        self._router = EventRouter()
        self._worker = EventWorker(self._router)

        self._running = False
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())

    async def shutdown(self, timeout: float = 15.0) -> None:
        self._running = False

        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            return("Queue join timeout, forcing shutdown")

        if self._task:
            self._task.cancel()

            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def publish(self, event: InfrastructureEvent) -> None:
        """Публикация нового события в очередь."""
        await self._queue.put(event)

    async def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        await self._router.subscribe(event_type, handler)

    async def unsubscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        await self._router.unsubscribe(event_type, handler)

    @property
    def pending_events(self) -> int:
        return self._queue.qsize()

    # ------------------------------------------------------------------ #
    # Internal event loop
    # ------------------------------------------------------------------ #

    async def _run(self) -> None:
        while self._running:
            event = await self._queue.get()

            try:
                errors = await self._worker.process(event)

                for handler, error in errors:
                    await self.publish(
                        InfrastructureEvent(
                            event_type=EventType.HANDLER_FAILED,
                            source=handler.__class__.__name__,
                            payload={
                                "failed_event": event.event_type.value,
                                "error": str(error),
                            },
                        )
                    )

            finally:
                self._queue.task_done()