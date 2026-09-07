"""
Module for managing registries of connectors and interfaces.
Provides decorators for easy registration of new implementations.
"""

from typing import Dict, Type, Any

# Global registries
CONNECTOR_REGISTRY: Dict[str, Type[Any]] = {}
INTERFACE_REGISTRY: Dict[str, Type[Any]] = {}
DEPENDENCE_REGISTRY: Dict[str, Type[Any]] = {}
PROTOCOL_REGISTRY: Dict[str, Type[Any]] = {}


def register_protocol(name: str):
    """
    Decorator to register a protocol class in the global registry.

    Args:
        name: The name to register the protocol class under
    """
    def decorator(cls):
        PROTOCOL_REGISTRY[name] = cls
        return cls
    return decorator


def dependence_connector(interface_name: str):
    """
    Decorator to register a connector's dependence on an interface.
    This creates a mapping: interface_name -> connector_class

    Args:
        interface_name: The name of the interface this connector implements
                       (e.g., "LLM", "Queue", "Storage")
    """
    def decorator(cls):
        DEPENDENCE_REGISTRY[interface_name] = cls
        return cls
    return decorator


def observe(*observer_names: str):
    """
    Decorator to mark connector with observer names.
    Container will read this and attach appropriate observers.
    
    Args:
        *observer_names: Names of observers to attach
                        (e.g., "logging", "metrics", "tracing")
    """
    def decorator(cls):
        cls._observer_names = observer_names
        return cls
    return decorator


def register_connector(name: str):
    """
    Decorator to register a connector class in the global registry.

    Args:
        name: The name to register the connector class under
    """
    def decorator(cls):
        CONNECTOR_REGISTRY[name] = cls
        return cls
    return decorator


def register_interface(name: str):
    """
    Decorator to register an interface class in the global registry.

    Args:
        name: The name to register the interface class under
    """
    def decorator(cls):
        INTERFACE_REGISTRY[name] = cls
        return cls
    return decorator


def get_connector_class(name: str) -> Type[Any]:
    """
    Retrieve a connector class by name from the registry.

    Args:
        name: The name of the connector class to retrieve

    Returns:
        The connector class associated with the name

    Raises:
        KeyError: If no connector class is registered under the name
    """
    if name not in CONNECTOR_REGISTRY:
        raise KeyError(f"No connector class registered under name '{name}'")
    return CONNECTOR_REGISTRY[name]


def get_interface_class(name: str) -> Type[Any]:
    """
    Retrieve an interface class by name from the registry.

    Args:
        name: The name of the interface class to retrieve

    Returns:
        The interface class associated with the name

    Raises:
        KeyError: If no interface class is registered under the name
    """
    if name not in INTERFACE_REGISTRY:
        raise KeyError(f"No interface class registered under name '{name}'")
    return INTERFACE_REGISTRY[name]


def get_dependence_class(interface_name: str) -> Type[Any]:
    """
    Retrieve a connector class by interface name from the dependence registry.
    This tells us which connector to use for a given interface.

    Args:
        interface_name: The name of the interface (e.g., "LLM", "Queue")

    Returns:
        The connector class associated with the interface

    Raises:
        KeyError: If no connector is registered for the interface
    """
    if interface_name not in DEPENDENCE_REGISTRY:
        raise KeyError(f"No connector registered for interface '{interface_name}'")
    return DEPENDENCE_REGISTRY[interface_name]


def get_all_connectors() -> Dict[str, Type[Any]]:
    """
    Get all registered connector classes.

    Returns:
        A dictionary mapping names to connector classes
    """
    return CONNECTOR_REGISTRY.copy()


def get_all_interfaces() -> Dict[str, Type[Any]]:
    """
    Get all registered interface classes.

    Returns:
        A dictionary mapping names to interface classes
    """
    return INTERFACE_REGISTRY.copy()


def get_protocol_class(name: str) -> Type[Any]:
    """
    Retrieve a protocol class by name from the registry.

    Args:
        name: The name of the protocol class to retrieve

    Returns:
        The protocol class associated with the name

    Raises:
        KeyError: If no protocol class is registered under the name
    """
    if name not in PROTOCOL_REGISTRY:
        raise KeyError(f"No protocol class registered under name '{name}'")
    return PROTOCOL_REGISTRY[name]


def get_all_protocols() -> Dict[str, Type[Any]]:
    """
    Get all registered protocol classes.

    Returns:
        A dictionary mapping names to protocol classes
    """
    return PROTOCOL_REGISTRY.copy()


def get_all_dependences() -> Dict[str, Type[Any]]:
    """
    Get all registered dependences (interface -> connector mapping).

    Returns:
        A dictionary mapping interface names to connector classes
    """
    return DEPENDENCE_REGISTRY.copy()
