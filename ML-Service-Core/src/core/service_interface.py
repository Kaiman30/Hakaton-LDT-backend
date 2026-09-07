"""
Service Interface - Abstract base class implementing the service protocol.

This class provides a foundation for all services in the application,
implementing common functionality and ensuring consistent behavior.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
import logging

from core.service_protocol import IService


class ServiceInterface(IService, ABC):
    """
    Abstract base class for all services in the application.
    
    This class implements the IService protocol and provides common
    functionality that all services should inherit.
    """
    
    def __init__(self, name: str):
        """
        Initialize the service interface.
        
        Args:
            name: The name of the service
        """
        self._name = name
        self._logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__qualname__}")
        self._is_running_flag = False
    
    @property
    def name(self) -> str:
        """
        Get the name of the service.
        
        Returns:
            The name of the service
        """
        return self._name
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the service and begin processing.
        
        This method should handle all initialization and start the main
        processing loop of the service. It should not return until the
        service is stopped or encounters a fatal error.
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the service gracefully.
        
        This method should handle cleanup and graceful shutdown of the service,
        ensuring all resources are released and all pending operations are completed.
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the service.
        
        Returns:
            A dictionary containing health status information
        """
        pass
    
    def is_running(self) -> bool:
        """
        Check if the service is currently running.
        
        Returns:
            True if the service is running, False otherwise
        """
        return self._is_running_flag
    
    def _set_running(self, running: bool) -> None:
        """
        Set the running state of the service.
        
        Args:
            running: True if the service is running, False otherwise
        """
        self._is_running_flag = running