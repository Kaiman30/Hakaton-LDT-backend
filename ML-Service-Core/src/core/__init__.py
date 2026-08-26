"""
Core module exports - Centralized imports for core functionality.

This module provides convenient access to core components of the application.
"""

# Export core protocols
from .service_protocol import IService
from .service_interface import ServiceInterface
from .base_service import BaseService

# Export service factory and manager
from .service_factory import (
    ServiceFactory,
    register_service,
    get_service,
    create_service,
    SERVICE_FACTORY
)
from .service_manager import (
    ServiceManager,
    initialize_service_manager,
    get_service_manager
)

# Export service container
from .service_container import ServiceContainer

# Export factories
from .factories import (
    ConnectorFactory,
    InterfaceFactory,
    ConnectorRegistryFactory,
)

# Export registry
from .registry import (
    register_connector,
    register_interface,
    get_connector_class,
    get_interface_class,
    CONNECTOR_REGISTRY,
    INTERFACE_REGISTRY
)

__all__ = [
    # Protocols and interfaces
    'IService',
    'ServiceInterface', 
    'BaseService',
    
    # Service factory and management
    'ServiceFactory',
    'register_service',
    'get_service',
    'create_service',
    'SERVICE_FACTORY',
    'ServiceManager',
    'initialize_service_manager',
    'get_service_manager',
    
    # Service container
    'ServiceContainer',
    
    # Factories
    'ConnectorFactory',
    'InterfaceFactory',
    'ConnectorRegistryFactory',
    
    # Registry
    'register_connector',
    'register_interface',
    'get_connector_class',
    'get_interface_class',
    'CONNECTOR_REGISTRY',
    'INTERFACE_REGISTRY',
]