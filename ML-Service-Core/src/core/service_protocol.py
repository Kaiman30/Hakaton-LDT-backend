"""
Service Protocol - Defines the contract for all services in the application.

This protocol establishes a consistent interface for all services,
enabling uniform handling and orchestration across the application.
"""

from __future__ import annotations
from typing import Protocol, runtime_checkable, Any, Optional
from abc import abstractmethod


@runtime_checkable
class IService(Protocol):
    """
    Protocol defining the contract for all services in the application.
    
    All concrete services should implement this protocol to ensure
    consistent behavior and interface across the application.
    """
    
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
    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on the service.
        
        Returns:
            A dictionary containing health status information
        """
        pass
    
    @abstractmethod
    def is_running(self) -> bool:
        """
        Check if the service is currently running.
        
        Returns:
            True if the service is running, False otherwise
        """
        pass