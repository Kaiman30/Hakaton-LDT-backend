# connectors/fastapi_connector.py
import asyncio
from typing import Awaitable, Optional, Callable, Any
from fastapi import FastAPI
import logging
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from core.base_class.base_connector import HTTPConnector
from models.http_model import HealthResponse, StatusResponse


@register_connector("FastApi")
@dependence_connector("HTTP")
class FastApiConnector(HTTPConnector):
    """
    Универсальный HTTP-коннектор, реализующий полный интерфейс коннектора.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        get_logger: Optional[Callable[[], logging.Logger]] = None,
        health_callback: Optional[Callable[[], Awaitable[dict]]] = None,
        status_callback: Optional[Callable[[], Awaitable[dict]]] = None,
    ):
        super().__init__("FastApi")  # Call parent constructor with name
        self.host = host
        self.port = port
        self._logger = get_logger() if get_logger else logging.getLogger(__name__)
        self._health_callback = health_callback
        self._status_callback = status_callback
        self._app: Optional[FastAPI] = None
        self._start_time: Optional[float] = None
        self._is_initialized = False
        self._healthy = False

    @classmethod
    def from_config(
        cls,
        config: Any,
        health_callback: Optional[Callable[[], Awaitable[dict]]] = None,
        status_callback: Optional[Callable[[], Awaitable[dict]]] = None,
        **kwargs
    ) -> "FastApiConnector":
        """
        Create FastApiConnector from config.

        Args:
            config: Settings object with config.http
            health_callback: Optional callback for health check
            status_callback: Optional callback for status
            **kwargs: Additional arguments (ignored for compatibility)

        Returns:
            Configured FastApiConnector instance
        """
        return cls(
            host=config.http.host,
            port=config.http.port,
            get_logger=lambda: logging.getLogger(__name__),
            health_callback=health_callback,
            status_callback=status_callback,
        )

    @property
    def app(self) -> FastAPI:
        if self._app is None:
            raise RuntimeError("Call initialize() first")
        return self._app

    # === Методы интерфейса коннектора ===
    
    async def initialize(self) -> None:
        """Инициализация коннектора (вызывается ServiceContainer)."""
        if self._is_initialized:
            return

        self._app = FastAPI(title="Service Monitor")

        @self._app.get("/health")
        async def health_route():
            return await self.health()

        @self._app.get("/status")
        async def status_route():
            return await self.status()

        self._start_time = asyncio.get_event_loop().time()
        self._is_initialized = True
        self._healthy = True
        self._logger.info(f"FastApiConnector initialized on {self.host}:{self.port}")

    async def shutdown(self) -> None:
        """Завершение работы коннектора."""
        self._is_initialized = False
        self._healthy = False
        self._logger.info("FastApiConnector shutdown completed")

    async def health_check(self) -> bool:
        """Проверка здоровья коннектора."""
        return self._healthy and self._is_initialized

    def is_healthy(self) -> bool:
        """Кэшированный статус здоровья."""
        return self._healthy

    # === Методы IHTTPProtocol ===
    
    def start(self) -> None:
        """Совместимость с IHTTPProtocol - просто вызывает initialize."""
        # В асинхронном контексте лучше использовать initialize()
        # Но для совместимости можно оставить пустым или вызвать sync версию
        pass

    async def health(self) -> HealthResponse:
        uptime = None
        if self._start_time is not None:
            uptime = round(asyncio.get_event_loop().time() - self._start_time, 2)
        
        status = "ok"
        if self._health_callback:
            try:
                health_data = await self._health_callback()
                status = health_data.get("status", "ok")
            except Exception as e:
                self._logger.warning(f"Health callback failed: {e}")
                status = "degraded"
        
        return HealthResponse(status=status, uptime_seconds=uptime)

    async def status(self) -> StatusResponse:
        details = {"mode": "embedded"}
        if self._status_callback:
            try:
                status_data = await self._status_callback()
                details.update(status_data)
            except Exception as e:
                self._logger.warning(f"Status callback failed: {e}")
                details["error"] = str(e)
        
        return StatusResponse(
            current_operation="running" if self._is_initialized else "stopped",
            active_tasks=len(asyncio.all_tasks()),
            details=details
        )
        