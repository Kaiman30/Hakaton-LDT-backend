"""
Connector and Interface Data Models.

Typed data structures for connector/interface registration and binding.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Type, TypeVar, Generic
from abc import ABC


# ============================================================================
# Type Variables for generic typing
# ============================================================================

T = TypeVar('T')


# ============================================================================
# Base Protocol Types (for type hints)
# ============================================================================

class ConnectorProtocol(Protocol):
    """Base protocol for all connectors"""
    name: str
    
    async def initialize(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def health_check(self) -> bool: ...
    def is_healthy(self) -> bool: ...


class InterfaceProtocol(Protocol):
    """Base protocol for all interfaces"""
    name: str
    worker: ConnectorProtocol
    
    async def initialize(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def health_check(self) -> bool: ...
    def is_healthy(self) -> bool: ...


# ============================================================================
# Registry Entry Models
# ============================================================================

@dataclass
class ConnectorRegistration:
    """
    Represents a registered connector.
    
    Attributes:
        name: Registered name (e.g., "GigaChat", "Kafka")
        connector_class: The connector class
        interface_name: Associated interface name (from @dependence_connector)
        observer_names: List of observer names (from @observe)
    """
    name: str
    connector_class: Type[ConnectorProtocol]
    interface_name: Optional[str] = None
    observer_names: tuple[str, ...] = field(default_factory=tuple)
    
    def __repr__(self) -> str:
        return f"ConnectorRegistration({self.name} -> {self.interface_name})"


@dataclass
class InterfaceRegistration:
    """
    Represents a registered interface.
    
    Attributes:
        name: Registered name (e.g., "LLM", "Queue")
        interface_class: The interface class
    """
    name: str
    interface_class: Type[InterfaceProtocol]
    
    def __repr__(self) -> str:
        return f"InterfaceRegistration({self.name})"


@dataclass
class DependenceBinding:
    """
    Represents a binding between interface and connector.
    This is what @dependence_connector creates.
    
    Attributes:
        interface_name: Name of the interface (e.g., "LLM", "Queue")
        connector_class: The connector class that implements this interface
    """
    interface_name: str
    connector_class: Type[ConnectorProtocol]
    
    def __repr__(self) -> str:
        return f"DependenceBinding({self.interface_name} <- {self.connector_class.__name__})"


# ============================================================================
# Runtime Binding Models (created by Container)
# ============================================================================

@dataclass
class InterfaceBinding:
    """
    Runtime binding of interface to connector.
    Created by ServiceContainer when it instantiates interfaces.
    
    Attributes:
        interface_name: Name of the interface (e.g., "LLM", "Queue")
        connector_name: Name of the connector (e.g., "GigaChat", "Kafka")
        interface_instance: The actual interface object
        connector_instance: The actual connector object (inside interface)
        observer_names: Observers attached to this binding
    """
    interface_name: str
    connector_name: str
    interface_instance: InterfaceProtocol
    connector_instance: Optional[ConnectorProtocol] = None
    observer_names: tuple[str, ...] = field(default_factory=tuple)
    
    def __post_init__(self):
        # Extract connector from interface if not provided
        if self.connector_instance is None and hasattr(self.interface_instance, '_worker'):
            self.connector_instance = self.interface_instance._worker
    
    def __repr__(self) -> str:
        return f"InterfaceBinding({self.interface_name} -> {self.connector_name})"


@dataclass
class ServiceBindings:
    """
    Container for all interface-connector bindings.
    Provides structured access to all registered bindings.
    
    Example usage:
        bindings = container.get_bindings()
        llm_binding = bindings.get("LLM")
        llm_interface = llm_binding.interface_instance
    """
    _bindings: Dict[str, InterfaceBinding]
    
    def get(self, interface_name: str) -> Optional[InterfaceBinding]:
        """Get binding by interface name"""
        return self._bindings.get(interface_name)
    
    def get_interface(self, interface_name: str) -> Optional[InterfaceProtocol]:
        """Get interface instance by name"""
        binding = self._bindings.get(interface_name)
        return binding.interface_instance if binding else None
    
    def items(self) -> Dict[str, InterfaceBinding]:
        """Get all bindings as dictionary"""
        return self._bindings
    
    def __getitem__(self, interface_name: str) -> InterfaceBinding:
        """Allow dict-like access: bindings["LLM"]"""
        return self._bindings[interface_name]
    
    def __contains__(self, interface_name: str) -> bool:
        """Allow 'in' check: "LLM" in bindings"""
        return interface_name in self._bindings
    
    def __len__(self) -> int:
        return len(self._bindings)
    
    def __iter__(self):
        return iter(self._bindings)
    
    def __repr__(self) -> str:
        return f"ServiceBindings({list(self._bindings.keys())})"


# ============================================================================
# Observer Configuration
# ============================================================================

@dataclass
class ObserverConfig:
    """
    Configuration for observers.
    
    Attributes:
        enable_logging: Enable logging observer
        enable_metrics: Enable metrics observer
        enable_tracing: Enable tracing observer
        custom_observers: List of custom observer classes
    """
    enable_logging: bool = True
    enable_metrics: bool = True
    enable_tracing: bool = False
    custom_observers: List[Any] = field(default_factory=list)
    
    def to_observer_names(self) -> tuple[str, ...]:
        """Convert to tuple of observer names"""
        names = []
        if self.enable_logging:
            names.append("logging")
        if self.enable_metrics:
            names.append("metrics")
        if self.enable_tracing:
            names.append("tracing")
        return tuple(names)
