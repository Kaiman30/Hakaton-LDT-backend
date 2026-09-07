"""
Base Service - Implementation of the service interface with common functionality.

This class provides a foundation for all services in the application,
implementing common functionality like logging, error handling, and lifecycle management.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from core.service_interface import ServiceInterface
from core.service_container import ServiceContainer
from config.config import Settings, get_settings


class BaseService(ServiceInterface):
    """
    Base class for all services in the application.
    
    This class provides common functionality like service container management,
    logging, configuration handling, and standardized lifecycle management.
    """
    
    def __init__(self, name: str, config: Optional[Settings] = None):
        """
        Initialize the base service.
        
        Args:
            name: The name of the service
            config: Optional configuration object, will use default if not provided
        """
        super().__init__(name)
        self._config = config or get_settings()
        self._container: Optional[ServiceContainer] = None
        self._shutdown_event = asyncio.Event()
        
    @property
    def config(self) -> Settings:
        """
        Get the configuration for this service.
        
        Returns:
            The configuration object
        """
        return self._config
    
    @property
    def container(self) -> Optional[ServiceContainer]:
        """
        Get the service container for this service.
        
        Returns:
            The service container instance or None if not initialized
        """
        return self._container
    
    async def initialize_container(self, auto_initialize: bool = True) -> None:
        """
        Initialize the service container for this service.
        
        Args:
            auto_initialize: Whether to automatically initialize all interfaces
        """
        self._container = await ServiceContainer.from_config(
            config=self._config,
            auto_initialize=auto_initialize,
            enable_logging=True,
            enable_metrics=True,
            enable_tracing=False,
        )
        
    async def start(self) -> None:
        """
        Start the service and begin processing.
        
        This method should be overridden by subclasses to implement
        specific service functionality.
        """
        self._logger.info(f"Starting service: {self.name}")
        self._set_running(True)
        
        try:
            # Initialize container if not already done
            if self._container is None:
                await self.initialize_container()
            
            # Subclasses should implement their specific startup logic
            await self._startup_impl()
            
        except Exception as e:
            self._logger.error(f"Error starting service {self.name}: {e}", exc_info=True)
            raise
        finally:
            self._set_running(False)
    
    async def stop(self) -> None:
        """
        Stop the service gracefully.
        
        This method handles cleanup and graceful shutdown of the service,
        ensuring all resources are released and all pending operations are completed.
        """
        self._logger.info(f"Stopping service: {self.name}")
        
        # Set shutdown event to signal all tasks to stop
        self._shutdown_event.set()
        
        try:
            # Subclasses should implement their specific shutdown logic
            await self._shutdown_impl()
            
            # Shutdown container if initialized
            if self._container:
                await self._container.shutdown_all()
                
        except Exception as e:
            self._logger.error(f"Error stopping service {self.name}: {e}", exc_info=True)
            raise
        finally:
            self._set_running(False)
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the service.
        
        Returns:
            A dictionary containing health status information
        """
        health_info = {
            "service": self.name,
            "status": "running" if self.is_running() else "stopped",
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Add container health if available
        if self._container:
            try:
                container_health = await self._container.health_check_all()
                health_info["container_health"] = container_health
            except Exception as e:
                health_info["container_health"] = {"error": str(e)}
        
        return health_info
    
    async def _startup_impl(self) -> None:
        """
        Implementation method for service-specific startup logic.
        
        This method should be overridden by subclasses to implement
        specific service functionality during startup.
        """
        # Default implementation does nothing - to be overridden by subclasses
        pass
    
    async def _shutdown_impl(self) -> None:
        """
        Implementation method for service-specific shutdown logic.
        
        This method should be overridden by subclasses to implement
        specific service functionality during shutdown.
        """
        # Default implementation does nothing - to be overridden by subclasses
        pass
    
    def get_shutdown_event(self) -> asyncio.Event:
        """
        Get the shutdown event for this service.
        
        Returns:
            The asyncio.Event that signals shutdown
        """
        return self._shutdown_event