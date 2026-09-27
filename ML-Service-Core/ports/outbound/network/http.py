# ports/outbound/http/http.py
"""
HTTP Interface - Strategy pattern implementation.
Uses DTOs from dto.py for type-safe communication.
"""

from typing import Optional, AsyncIterator, Dict, Any

from ports.outbound.network.dto import HTTPRequest, HTTPResponse
from ports.protocols import IHTTPConnector
from core.base_class.base_interface import BaseInterface
from core.registry import InterfaceRegistry
from core.runtime.event_bus import RuntimeEventBus


@InterfaceRegistry.register("HTTP")
class HTTPInterface(BaseInterface[IHTTPConnector], IHTTPConnector):
    """
    High-level interface for HTTP client operations.
    Implements Strategy pattern with DTO-based communication.
    """

    def __init__(
        self,
        worker: IHTTPConnector,
        name: Optional[str] = None,
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        super().__init__(worker, name, event_bus)

    @property
    def worker(self) -> IHTTPConnector:
        return self._worker

    # ============ IHTTPConnector Implementation ============

    async def send(self, request: HTTPRequest) -> HTTPResponse:
        """Send HTTP request with observability."""
        return await self._execute_with_tracking(
            "send",
            self._worker.send,
            request,
            metadata={
                "method": request.method,
                "url": request.url,
                "has_params": bool(request.params),
                "has_json": request.json_data is not None,
                "timeout": request.timeout,
            },
        )

    async def stream(self, request: HTTPRequest) -> AsyncIterator[bytes]:
        """Stream response body bytes with observability."""
        async for chunk in self._execute_stream_with_tracking(
            "stream",
            self._worker.stream,
            request,
            metadata={
                "method": request.method,
                "url": request.url,
                "timeout": request.timeout,
            },
        ):
            yield chunk

    # Вспомогательные удобные обертки (Shortcuts)

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> HTTPResponse:
        """Shortcut for GET request."""
        req = HTTPRequest(url=url, method="GET", params=params, headers=headers, timeout=timeout)
        return await self.send(req)

    async def post(
        self,
        url: str,
        json_data: Optional[Any] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> HTTPResponse:
        """Shortcut for POST request."""
        req = HTTPRequest(
            url=url,
            method="POST",
            json_data=json_data,
            data=data,
            headers=headers,
            timeout=timeout,
        )
        return await self.send(req)

    # ============ Protocol Required ============

    @property
    def name(self) -> str:
        return self._name

    @property
    def healthy(self) -> bool:
        return self._worker.healthy

    async def check_health(self) -> bool:
        return await self._execute_with_tracking(
            "check_health",
            self._worker.check_health,
            metadata={"check_type": "http_connectivity"},
        )

    async def initialize(self) -> None:
        await self._worker.initialize()

    async def shutdown(self) -> None:
        await self._worker.shutdown()