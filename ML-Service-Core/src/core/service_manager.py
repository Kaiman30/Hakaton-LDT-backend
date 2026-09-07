"""
Service Manager - Orchestrates multiple services in the application.

This module provides a centralized way to manage the lifecycle of multiple services.
"""

import asyncio
import sys
from typing import Dict, List, Optional, Union

from core.service_protocol import IService
from core.service_factory import SERVICE_FACTORY, create_service
from config.config import Settings


class ServiceManager:
    """
    Manages the lifecycle of multiple services in the application.
    """
    
    def __init__(self, config: Settings):
        """
        Initialize the service manager.
        
        Args:
            config: The application configuration
        """
        self.config = config
        self.services: Dict[str, IService] = {}
        self._shutdown_event = asyncio.Event()
    
    def add_service(self, name: str, service: IService) -> None:
        """
        Add a service to be managed.
        
        Args:
            name: The name of the service
            service: The service instance to manage
        """
        self.services[name] = service
    
    def add_service_by_type(self, name: str, service_type: str, *args, **kwargs) -> bool:
        """
        Create and add a service by its registered type.
        
        Args:
            name: The name to register the service under
            service_type: The registered type of the service to create
            *args: Positional arguments to pass to the service constructor
            **kwargs: Keyword arguments to pass to the service constructor
            
        Returns:
            True if the service was created and added successfully, False otherwise
        """
        service = create_service(service_type, *args, **kwargs)
        if service is None:
            return False
        
        self.add_service(name, service)
        return True
    
    async def start_all(self) -> None:
        """Start all managed services."""
        start_tasks = []
        
        for name, service in self.services.items():
            try:
                task = asyncio.create_task(service.start())
                start_tasks.append((name, task))
            except Exception as e:
                print(f"Failed to start service {name}: {e}")
        
        # Wait for all services to start
        for name, task in start_tasks:
            try:
                await task
            except Exception as e:
                print(f"Service {name} failed during startup: {e}")
    
    async def stop_all(self) -> None:
        """Stop all managed services."""
        stop_tasks = []
        
        for name, service in self.services.items():
            try:
                task = asyncio.create_task(service.stop())
                stop_tasks.append((name, task))
            except Exception as e:
                print(f"Failed to initiate stop for service {name}: {e}")
        
        # Wait for all services to stop
        for name, task in stop_tasks:
            try:
                await task
            except Exception as e:
                print(f"Service {name} failed during shutdown: {e}")
    
    async def health_check_all(self) -> Dict[str, dict]:
        """
        Perform health checks on all managed services.
        
        Returns:
            A dictionary mapping service names to their health check results
        """
        health_results = {}
        
        for name, service in self.services.items():
            try:
                health = await service.health_check()
                health_results[name] = health
            except Exception as e:
                health_results[name] = {"status": "error", "error": str(e)}
        
        return health_results
    
    def get_service(self, name: str) -> Optional[IService]:
        """
        Get a managed service by name.
        
        Args:
            name: The name of the service to retrieve
            
        Returns:
            The service instance or None if not found
        """
        return self.services.get(name)
    
    def get_services(self) -> Dict[str, IService]:
        """
        Get all managed services.
        
        Returns:
            A dictionary mapping service names to instances
        """
        return self.services.copy()


# Global service manager instance
SERVICE_MANAGER: Optional[ServiceManager] = None


def get_service_manager() -> Optional[ServiceManager]:
    """
    Get the global service manager instance.
    
    Returns:
        The service manager instance or None if not initialized
    """
    return SERVICE_MANAGER


def initialize_service_manager(config: Settings) -> ServiceManager:
    """
    Initialize the global service manager instance.
    
    Args:
        config: The application configuration
        
    Returns:
        The initialized service manager
    """
    global SERVICE_MANAGER
    SERVICE_MANAGER = ServiceManager(config)
    return SERVICE_MANAGER