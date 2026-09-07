from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum


class ConnectorState(str, Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    DEGRADED = "degraded"
    SHUTTING_DOWN = "shutting_down"
    CLOSED = "closed"


@dataclass(slots=True)
class ConnectorStatus:
    connector: str

    state: ConnectorState = ConnectorState.CREATED

    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    last_error: str | None = None