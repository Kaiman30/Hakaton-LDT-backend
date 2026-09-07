"""
Factories for creating connectors and interfaces with proper protocol typing.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol

from config.config import Settings, get_settings
from connectors.gigachat_connector import GigaChatConnector
from connectors.http_connector import FastApiConnector
from connectors.kafka_connector import KafkaConnector
from connectors.minio_connector import MinIOConnector
from connectors.pg_connector import PGConnector
from core.base_class.protocols import (
    ILLMConnector,
    IQueueConnector,
    IFileStorageConnector,
    IDBConnector,
    IHTTPConnector
)
from core.base_class.base_connectors import BaseConnector
from core.registry import register_connector, register_interface, get_connector_class, get_interface_class
from interface.db import DBInterface
from interface.http import HTTPInterface
from interface.llm import LLMInterface
from interface.iqueue import QueueInterface
from interface.storage import StorageInterface
from utils.logging import get_logger_from_config
from utils.observer import EventPublisher


class ConnectorFactory:
    """
    Minimal factory for creating connectors by name from registry.
    No validation, no hardcoded names - just creates from config.
    """

    def __init__(self, config: Settings):
        self.config: Settings = config

    def create_connector(self, name: str, **kwargs) -> BaseConnector:
        """
        Create connector by name from registry.

        Args:
            name: Registered connector name (e.g., "GigaChat", "Kafka")
            **kwargs: Additional args passed to from_config()
        """
        connector_class = get_connector_class(name)
        return connector_class.from_config(self.config, **kwargs)


class InterfaceFactory:
    """
    Minimal factory for creating interfaces.
    Takes a connector and wraps it with an interface.
    """

    def __init__(self, config: Settings):
        self.config: Settings = config

    def create_interface(
        self,
        connector: BaseConnector,
        interface_name: str,
        event_publisher: Optional[EventPublisher] = None
    ) -> Any:
        """
        Create interface by wrapping a connector.

        Args:
            connector: The connector to wrap
            interface_name: Registered interface name (e.g., "LLM", "Queue")
            event_publisher: Optional event publisher for observability
        """
        interface_class = get_interface_class(interface_name)
        return interface_class(
            worker=connector,
            name=interface_name,
            event_publisher=event_publisher
        )


class ConnectorRegistryFactory:
    """
    Factory for creating and registering connectors/interfaces.
    Minimal wrapper around ConnectorFactory and InterfaceFactory.
    """

    def __init__(self, config: Settings):
        self.config: Settings = config
        self._connectors: Dict[str, Any] = {}
        self._interfaces: Dict[str, Any] = {}
        self.connector_factory = ConnectorFactory(config)
        self.interface_factory = InterfaceFactory(config)

    def create_and_register(
        self,
        connector_name: str,
        interface_name: str,
        event_publisher: Optional[EventPublisher] = None,
        **kwargs
    ) -> Any:
        """
        Create connector and interface, register both.

        Args:
            connector_name: Registered connector name (e.g., "GigaChat")
            interface_name: Interface name to use (e.g., "LLM")
            event_publisher: Optional event publisher
            **kwargs: Additional args for connector.from_config()

        Returns:
            Created interface
        """
        # Create connector
        connector = self.connector_factory.create_connector(connector_name, **kwargs)
        self._connectors[connector_name] = connector

        # Create interface
        interface = self.interface_factory.create_interface(
            connector=connector,
            interface_name=interface_name,
            event_publisher=event_publisher
        )
        self._interfaces[interface_name] = interface

        return interface

    def get_interface(self, name: str) -> Optional[Any]:
        """Get registered interface by name"""
        return self._interfaces.get(name)

    def get_connector(self, name: str) -> Optional[Any]:
        """Get registered connector by name"""
        return self._connectors.get(name)
    