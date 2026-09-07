"""
Service Container - manages interfaces with protocol-based access.

This is the high-level container that:
- Provides interfaces as protocols (ILLMConnector, IQueueConnector, etc.)
- Uses factories for interface creation
- Provides event publishing (Observer pattern)
- Handles lifecycle management
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Union

from config.config import Settings, get_settings
from core.base_class.protocols import (
    ILLMConnector,
    IQueueConnector, 
    IFileStorageConnector,
    IDBConnector,
    IHTTPConnector
)
from core.factories import ConnectorRegistryFactory
from core.registry import get_connector_class
from utils.logging import get_logger_from_config
from utils.observer import (
    EventPublisher,
    LoggingObserver,
    MetricsObserver,
    TracingObserver,
)


class ServiceContainer:
    """
    High-level service container that returns interfaces as protocols.

    Features:
    - Returns interfaces as protocols (type safety)
    - Event publishing for all operations
    - Centralized logging and metrics
    - Lifecycle management
    """

    def __init__(
        self,
        config: Optional[Settings] = None,
        enable_logging: bool = True,
        enable_metrics: bool = True,
        enable_tracing: bool = False,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        """
        Initialize service container.

        Args:
            config: Optional settings instance (uses get_settings() if None)
            enable_logging: Enable logging observer
            enable_metrics: Enable metrics observer
            enable_tracing: Enable tracing observer
            event_publisher: Custom event publisher (optional)
        """
        self.config: Settings = config or get_settings()
        self._executor: Optional[ThreadPoolExecutor] = None

        # Event publisher with observers
        self._event_publisher = event_publisher or EventPublisher()
        self._logger = get_logger_from_config(self.config)

        if enable_logging:
            self._event_publisher.subscribe(LoggingObserver(self._logger))

        if enable_metrics:
            self._metrics_observer = MetricsObserver()
            self._event_publisher.subscribe(self._metrics_observer)
        else:
            self._metrics_observer = None

        if enable_tracing:
            self._tracing_observer = TracingObserver()
            self._event_publisher.subscribe(self._tracing_observer)
        else:
            self._tracing_observer = None

        # Store interfaces as protocols
        self._interfaces: Dict[str, ProtocolType] = {}

        # Factory for creating interfaces
        self._factory: Optional[ConnectorRegistryFactory] = None

    @classmethod
    async def from_config(
        cls,
        config: Optional[Settings] = None,
        auto_initialize: bool = True,
        enable_logging: bool = True,
        enable_metrics: bool = True,
        enable_tracing: bool = False,
        event_publisher: Optional[EventPublisher] = None,
    ) -> "ServiceContainer":
        """
        Create and optionally initialize container from settings.

        Args:
            config: Optional settings instance
            auto_initialize: If True, initialize all interfaces immediately
            enable_logging: Enable logging observer
            enable_metrics: Enable metrics observer
            enable_tracing: Enable tracing observer
            event_publisher: Custom event publisher
        """
        instance = cls(
            config=config,
            enable_logging=enable_logging,
            enable_metrics=enable_metrics,
            enable_tracing=enable_tracing,
            event_publisher=event_publisher,
        )
        
        await instance.register_all()

        if auto_initialize:
            await instance.initialize_all()

        return instance

    async def register_all(self) -> None:
        """
        Register all interfaces dynamically from DEPENDENCE_REGISTRY.
        No hardcoded provider names - reads from registry!
        """
        from core.registry import get_all_dependences, CONNECTOR_REGISTRY

        self._executor = ThreadPoolExecutor(max_workers=20)
        self._factory = ConnectorRegistryFactory(self.config)

        # Get all registered dependences (interface_name -> connector_class)
        dependences = get_all_dependences()

        # Create interfaces for all registered dependences
        for interface_name, connector_class in dependences.items():
            try:
                # Find connector name from CONNECTOR_REGISTRY
                connector_name = None
                for name, cls in CONNECTOR_REGISTRY.items():
                    if cls == connector_class:
                        connector_name = name
                        break

                if connector_name is None:
                    self._logger.warning(
                        f"Connector class {connector_class.__name__} not found in CONNECTOR_REGISTRY"
                    )
                    continue

                # Create and register
                kwargs = {}
                if interface_name == "Storage":
                    kwargs["executor"] = self._executor

                interface = self._factory.create_and_register(
                    connector_name=connector_name,
                    interface_name=interface_name,
                    event_publisher=self._event_publisher,
                    **kwargs
                )
                self._interfaces[interface_name] = interface
                self._logger.info(
                    f"Registered {interface_name} interface with {connector_name} connector"
                )

            except Exception as e:
                self._logger.error(
                    f"Failed to create {interface_name} interface: {e}"
                )

        self._logger.info(
            "Registered %d interfaces: %s",
            len(self._interfaces),
            list(self._interfaces.keys()),
        )

    async def initialize_all(self) -> Dict[str, bool]:
        """
        Initialize all registered interfaces asynchronously.

        Returns:
            Dict mapping interface names to initialization success status
        """
        # Create initialization tasks for all interfaces
        init_tasks = {}
        for name, interface in self._interfaces.items():
            init_tasks[name] = asyncio.create_task(
                self._initialize_single_interface(interface, name)
            )

        # Wait for all initialization tasks to complete
        results = {}
        for name, task in init_tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                results[name] = False
                self._logger.error("Unexpected error initializing interface %s: %s", name, e)

        return results

    async def _initialize_single_interface(self, interface: ProtocolType, name: str) -> bool:
        """
        Initialize a single interface with timeout and error handling.

        Args:
            interface: The interface as protocol
            name: The name of the interface for logging

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            await interface.initialize()
            self._logger.info("Initialized interface: %s", name)
            return True
        except asyncio.TimeoutError:
            self._logger.error("Timeout initializing interface %s", name)
            return False
        except Exception as e:
            self._logger.error("Failed to initialize interface %s: %s", name, e)
            return False

    async def shutdown_all(self) -> None:
        """Shutdown all interfaces and cleanup resources"""
        for name, interface in self._interfaces.items():
            try:
                await interface.shutdown()
                self._logger.info("Shutdown interface: %s", name)
            except Exception as e:
                self._logger.error("Error shutting down interface %s: %s", name, e)

        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all interfaces.

        Returns:
            Dict mapping interface names to health status
        """
        results: Dict[str, bool] = {}

        for name, interface in self._interfaces.items():
            try:
                results[name] = await interface.health_check()
            except Exception:
                results[name] = False

        return results

    # ============ Protocol-based getters ============

    def get_llm(self, name: str = "LLM") -> ILLMConnector:
        """Get LLM interface as ILLMConnector protocol"""
        interface = self._interfaces.get(name)
        if interface is None:
            raise KeyError(f"LLM interface '{name}' not found")

        if not isinstance(interface, ILLMConnector):
            raise TypeError(f"Interface '{name}' does not implement ILLMConnector protocol")
        return interface

    def get_queue(self, name: str = "Queue") -> IQueueConnector:
        """Get Queue interface as IQueueConnector protocol"""
        interface = self._interfaces.get(name)
        if interface is None:
            raise KeyError(f"Queue interface '{name}' not found")

        if not isinstance(interface, IQueueConnector):
            raise TypeError(f"Interface '{name}' does not implement IQueueConnector protocol")
        return interface

    def get_storage(self, name: str = "Storage") -> IFileStorageConnector:
        """Get Storage interface as IFileStorageConnector protocol"""
        interface = self._interfaces.get(name)
        if interface is None:
            raise KeyError(f"Storage interface '{name}' not found")

        if not isinstance(interface, IFileStorageConnector):
            raise TypeError(f"Interface '{name}' does not implement IFileStorageConnector protocol")
        return interface

    def get_db(self, name: str = "DB") -> IDBConnector:
        """Get DB interface as IDBConnector protocol"""
        interface = self._interfaces.get(name)
        if interface is None:
            raise KeyError(f"DB interface '{name}' not found")

        if not isinstance(interface, IDBConnector):
            raise TypeError(f"Interface '{name}' does not implement IDBConnector protocol")
        return interface

    def get_http(self, name: str = "HTTP") -> IHTTPConnector:
        """Get HTTP interface as IHTTPConnector protocol"""
        interface = self._interfaces.get(name)
        if interface is None:
            raise KeyError(f"HTTP interface '{name}' not found")

        if not isinstance(interface, IHTTPConnector):
            raise TypeError(f"Interface '{name}' does not implement IHTTPConnector protocol")
        return interface

    def get_all(self) -> Dict[str, ProtocolType]:
        """Get all registered interfaces as protocols"""
        return dict(self._interfaces)

    # ============ Factory access ============

    def create_interface(self, interface_type: str, name: Optional[str] = None) -> ProtocolType:
        """Create a new interface dynamically"""
        if not self._factory:
            self._factory = ConnectorRegistryFactory(self.config)
        
        # Map interface type to factory method
        factory_methods = {
            "llm": self._factory.create_and_register_llm_connector,
            "queue": self._factory.create_and_register_queue_connector,
            "storage": self._factory.create_and_register_storage_connector,
            "db": self._factory.create_and_register_db_connector,
            "http": self._factory.create_and_register_http_connector,
        }
        
        if interface_type not in factory_methods:
            raise ValueError(f"Unknown interface type: {interface_type}")
        
        # Create interface
        if name:
            interface = factory_methods[interface_type](name)
        else:
            # Use default name based on type
            default_names = {
                "llm": "GigaChat",
                "queue": "Kafka",
                "storage": "Minio",
                "db": "Postgres",
                "http": "FastApi",
            }
            interface = factory_methods[interface_type](default_names[interface_type])
        
        # Register in container
        self._interfaces[name or default_names[interface_type]] = interface
        
        return interface

    # ============ Observer access ============

    @property
    def event_publisher(self) -> EventPublisher:
        """Get event publisher for custom observers"""
        return self._event_publisher

    def get_metrics(self) -> Optional[Dict[str, Dict[str, float]]]:
        """Get collected metrics (if metrics observer enabled)"""
        if self._metrics_observer:
            return self._metrics_observer.get_metrics()
        return None

    def get_traces(self, limit: int = 100) -> Optional[list]:
        """Get recent traces (if tracing observer enabled)"""
        if self._tracing_observer:
            return self._tracing_observer.get_traces(limit)
        return None

    def get_task_deduplication_queue(self):
        """Get task deduplication queue"""
        from core.task_deduplication_queue import TaskDeduplicationQueue
        return TaskDeduplicationQueue()


# Global container instance
_global_container: Optional[ServiceContainer] = None


async def get_container(
    config: Optional[Settings] = None,
    auto_initialize: bool = True,
    enable_logging: bool = True,
    enable_metrics: bool = True,
    enable_tracing: bool = False,
) -> ServiceContainer:
    """
    Get or create global service container instance.

    Args:
        config: Optional settings instance
        auto_initialize: If True, initialize interfaces
        enable_logging: Enable logging observer
        enable_metrics: Enable metrics observer
        enable_tracing: Enable tracing observer
    """
    global _global_container

    if _global_container is None:
        _global_container = await ServiceContainer.from_config(
            config=config,
            auto_initialize=auto_initialize,
            enable_logging=enable_logging,
            enable_metrics=enable_metrics,
            enable_tracing=enable_tracing,
        )

    return _global_container


async def reset_container() -> None:
    """Reset global container (useful for testing)"""
    global _global_container

    if _global_container is not None:
        await _global_container.shutdown_all()
        _global_container = None
        