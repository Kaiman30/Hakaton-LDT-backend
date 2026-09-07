from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class EventType(str, Enum):
    """
    Типы инфраструктурных событий ML-Service Core.
    """

    # Connector lifecycle
    CONNECTOR_CREATED = "connector.created"
    CONNECTOR_INITIALIZED = "connector.initialized"
    CONNECTOR_SHUTDOWN = "connector.shutdown"

    # Connector state
    STATE_CHANGED = "connector.state_changed"
    HEALTH_CHANGED = "connector.health_changed"

    # Dependency Injection / Registry
    CONNECTOR_REGISTERED = "registry.connector_registered"
    CONNECTOR_RESOLVED = "registry.connector_resolved"

    # Runtime lifecycle
    RUNTIME_STARTED = "runtime.started"
    RUNTIME_STOPPED = "runtime.stopped"

    # Tracing
    TRACE_STARTED = "trace.started"
    TRACE_FINISHED = "trace.finished"

    # Internal infrastructure failures
    HANDLER_FAILED = "event.handler_failed"


@dataclass(slots=True, frozen=True)
class InfrastructureEvent:
    """
    Базовая модель инфраструктурного события.

    Все события ядра публикуются в таком формате.
    """

    event_type: EventType
    source: str

    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))