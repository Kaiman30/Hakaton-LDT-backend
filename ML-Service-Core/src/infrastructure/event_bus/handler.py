from __future__ import annotations

from typing import Protocol

from .models import InfrastructureEvent


class EventHandler(Protocol):
    """
    Контракт обработчика инфраструктурных событий.
    """

    async def handle(self, event: InfrastructureEvent) -> None:
        """
        Реакция обработчика на событие.
        """
        ...