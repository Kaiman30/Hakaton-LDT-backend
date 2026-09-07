"""
HTTP Interface - Strategy pattern implementation for HTTP connectors.

Allows switching between different HTTP frameworks (FastAPI, aiohttp, etc.)
while maintaining the same API.
"""

from typing import Any, Dict, Optional

from core.base_class.base_interface import BaseInterface
from core.base_class.protocols import IHTTPConnector
from models.http_model import HealthResponse, StatusResponse
from utils.observer import EventPublisher
from core.registry import register_interface


@register_interface("HTTP")
class HTTPInterface(BaseInterface, IHTTPConnector):
    """
    High-level interface for HTTP operations.

    Implements Strategy pattern - can switch between different HTTP frameworks
    (FastAPI, aiohttp, etc.) transparently.
    """

    def __init__(
        self,
        worker: IHTTPConnector,
        name: Optional[str] = None,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        """
        Initialize HTTP interface.

        Args:
            worker: HTTP connector instance (e.g., FastApiConnector)
            name: Interface name (defaults to worker name)
            event_publisher: Optional event publisher for observability
        """
        super().__init__(worker, name, event_publisher)

    @property
    def worker(self) -> IHTTPConnector:
        """Get underlying HTTP connector"""
        return self._worker

    # ============ IHTTPConnector protocol implementation ============

    def start(self) -> None:
        """
        Start HTTP server/service.
        
        Note: This method is synchronous as HTTP servers typically
        run in their own event loop or thread.
        """
        # Для трекинга синхронных методов создаем обертку
        import asyncio
        import time
        
        start_time = time.perf_counter()
        
        # Запускаем worker
        self._worker.start()
        
        # Публикуем событие в фоне
        if self._event_publisher:
            from utils.observer import ConnectorEvent, EventType
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            event = ConnectorEvent(
                event_type=EventType.OPERATION_COMPLETED,
                connector_name=self._worker.name,
                interface_name=self._name,
                operation_name="start",
                success=True,
                duration_ms=duration_ms,
                metadata={"operation": "http_server_start"},
            )
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._event_publisher.publish(event))
            except RuntimeError:
                pass

    async def health(self) -> Dict[str, Any]:
        """
        Get health status information.

        Returns:
            Health information dictionary
        """
        result = await self._execute_with_tracking(
            "health",
            self._worker.health,
            metadata={"check_type": "http_health"},
        )
        
        # Преобразуем HealthResponse в dict, если нужно
        if isinstance(result, HealthResponse):
            return result.dict()
        return result

    async def status(self) -> Dict[str, Any]:
        """
        Get current status information.

        Returns:
            Status information dictionary
        """
        result = await self._execute_with_tracking(
            "status",
            self._worker.status,
            metadata={"check_type": "http_status"},
        )
        
        # Преобразуем StatusResponse в dict, если нужно
        if isinstance(result, StatusResponse):
            return result.dict()
        return result

    @property
    def app(self) -> Any:
        """
        Get the web application instance.

        Returns:
            Web framework application (e.g., FastAPI app)
        """
        return self._worker.app

    # ============ Protocol required methods ============

    @property
    def name(self) -> str:
        """Get connector name - required by IHTTPConnector protocol"""
        return self._name

    async def health_check(self) -> bool:
        """Check HTTP connectivity - required by protocol"""
        # Используем health() метод для проверки
        try:
            result = await self.health()
            return result.get("status", "ok") == "ok"
        except Exception:
            return False

    def is_healthy(self) -> bool:
        """Get cached health status - required by protocol"""
        return self._worker.is_healthy()