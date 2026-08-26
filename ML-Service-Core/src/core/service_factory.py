"""
Service Factory - Factory for creating and managing services.

This module provides a centralized way to register, create, and manage
different types of services in the application.
"""

from typing import Dict, Type, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from core.service_protocol import IService
from config.config import Settings


class ServiceFactory:
    """
    Factory for creating and managing services.
    
    This class provides methods to register service classes and create
    instances of services based on their registered names.
    """
    
    def __init__(self):
        self._service_classes: Dict[str, Type[IService]] = {}
        self._service_instances: Dict[str, IService] = {}
    
    def register_service(self, name: str, service_class: Type[IService]) -> None:
        """
        Register a service class with the factory.
        
        Args:
            name: The name to register the service class under
            service_class: The service class to register
        """
        self._service_classes[name] = service_class
    
    def create_service(self, name: str, *args, **kwargs) -> Optional[IService]:
        """
        Create an instance of a registered service.
        
        Args:
            name: The name of the service to create
            *args: Positional arguments to pass to the service constructor
            **kwargs: Keyword arguments to pass to the service constructor
            
        Returns:
            An instance of the service or None if the service is not registered
        """
        if name not in self._service_classes:
            return None
        
        service_class = self._service_classes[name]
        service_instance = service_class(*args, **kwargs)
        self._service_instances[name] = service_instance
        return service_instance
    
    def get_service(self, name: str) -> Optional[IService]:
        """
        Get an existing instance of a service.
        
        Args:
            name: The name of the service to retrieve
            
        Returns:
            The service instance or None if it doesn't exist
        """
        return self._service_instances.get(name)
    
    def get_all_services(self) -> Dict[str, IService]:
        """
        Get all created service instances.
        
        Returns:
            A dictionary mapping service names to instances
        """
        return self._service_instances.copy()
    
    def create_and_register_default_services(self, config: Settings) -> Dict[str, IService]:
        """
        Create and register default services based on configuration.
        
        Args:
            config: The application configuration
            
        Returns:
            A dictionary of created services
        """
        services = {}
        
        # Example: Create LLM service if enabled in config
        if getattr(config, 'llm_service_enabled', True):
            llm_service = self.create_service('llm', config=config)
            if llm_service:
                services['llm'] = llm_service
        
        return services


# Global service factory instance
SERVICE_FACTORY = ServiceFactory()


def register_service(name: str):
    """
    Decorator to register a service class with the global service factory.
    
    Args:
        name: The name to register the service class under
    """
    def decorator(service_class: Type[IService]):
        SERVICE_FACTORY.register_service(name, service_class)
        return service_class
    return decorator


def get_service(name: str) -> Optional[IService]:
    """
    Get a service instance from the global service factory.
    
    Args:
        name: The name of the service to retrieve
        
    Returns:
        The service instance or None if it doesn't exist
    """
    return SERVICE_FACTORY.get_service(name)


def create_service(name: str, *args, **kwargs) -> Optional[IService]:
    """
    Create a service instance using the global service factory.
    
    Args:
        name: The name of the service to create
        *args: Positional arguments to pass to the service constructor
        **kwargs: Keyword arguments to pass to the service constructor
        
    Returns:
        An instance of the service or None if the service is not registered
    """
    return SERVICE_FACTORY.create_service(name, *args, **kwargs)