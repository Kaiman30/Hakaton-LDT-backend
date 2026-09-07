from typing import Protocol

from .models import ConnectorStatus


class StateRepository(Protocol):

    def save(self, status: ConnectorStatus):
        ...

    def get(self, connector: str) -> ConnectorStatus | None:
        ...

    def snapshot(self) -> dict[str, ConnectorStatus]:
        ...

    def timeline(self, connector: str) -> list[ConnectorStatus]:
        ...