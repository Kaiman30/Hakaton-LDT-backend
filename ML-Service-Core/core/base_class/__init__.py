"""
Core base classes for connectors.

Provides:
- Base connector abstractions
- Protocol-based type definitions
- Registry and DI container
- Config-driven factories
"""

from __future__ import annotations

# Observer pattern
from utils.observer import (
    ConnectorEvent,
    EventObserver,
    EventPublisher,
    EventType,
    LoggingObserver,
    MetricsObserver,
    TracingObserver,
)

# Base connector classes
from .base_connectors import (
    BaseConnector,
    DBConnector,
    FileStorageConnector,
    LLMConnector,
    QueueConnector,
)

# Protocol-based type definitions
from .protocols import (
    IDBConnector,
    IFileStorageConnector,
    ILLMConnector,
    IQueueConnector,
)

__all__ = [
    # Base classes
    "BaseConnector",
    "LLMConnector",
    "QueueConnector",
    "FileStorageConnector",
    "DBConnector",
    # Protocols
    "ILLMConnector",
    "IQueueConnector",
    "IFileStorageConnector",
    "IDBConnector",
    # Registry
    "ConnectorType",
    "ConnectorRegistry",
    "DIContainer",
    # Observer pattern
    "EventPublisher",
    "EventObserver",
    "ConnectorEvent",
    "EventType",
    "LoggingObserver",
    "MetricsObserver",
    "TracingObserver",
]
