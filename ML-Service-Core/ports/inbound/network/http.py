# ports/inbound/network/http.py
"""
HTTP Interface - Strategy pattern implementation.
Uses DTOs from dto.py for type-safe communication.
"""

from typing import Optional, Dict, Any

from ports.inbound.network.dto import HttpRequest, HttpResponse
from ports.protocols import IHTTPConnector
from core.base_class.base_interface import BaseInterface
from core.registry import InterfaceRegistry
from core.runtime.event_bus import RuntimeEventBus


@InterfaceRegistry.register("HTTP")
class HTTPInterface(BaseInterface[IHTTPConnector], IHTTPConnector):
    """
    High-level interface for HTTP operations.
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

    @property
    def app(self) -> Any:
        """Get underlying web application."""
        return self._worker.app

    # ============ IHTTPConnector Implementation ============

    async def request(self, request: HttpRequest) -> HttpResponse:
        """Execute HTTP request with observability."""
        return await self._execute_with_tracking(
            "request",
            self._worker.request,
            request,
            metadata={
                "url": request.url,
                "method": request.method.value,
                "has_data": request.data is not None,
                "has_json": request.json is not None,
                "has_files": bool(request.files),
                "timeout": request.timeout,
                "verify_ssl": request.verify_ssl,
            },
        )

    async def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> HttpResponse:
        """GET request with observability."""
        return await self._execute_with_tracking(
            "get",
            self._worker.get,
            url,
            params,
            metadata={
                "url": url,
                "has_params": bool(params),
                "params_count": len(params) if params else 0,
                "method": "GET",
            },
        )

    async def post(self, url: str, data: Optional[Dict[str, Any]] = None) -> HttpResponse:
        """POST request with observability."""
        return await self._execute_with_tracking(
            "post",
            self._worker.post,
            url,
            data,
            metadata={
                "url": url,
                "has_data": bool(data),
                "data_size": len(str(data)) if data else 0,
                "method": "POST",
            },
        )

    async def put(self, url: str, data: Optional[Dict[str, Any]] = None) -> HttpResponse:
        """PUT request with observability."""
        return await self._execute_with_tracking(
            "put",
            self._worker.put,
            url,
            data,
            metadata={
                "url": url,
                "has_data": bool(data),
                "data_size": len(str(data)) if data else 0,
                "method": "PUT",
            },
        )

    async def delete(self, url: str) -> HttpResponse:
        """DELETE request with observability."""
        return await self._execute_with_tracking(
            "delete",
            self._worker.delete,
            url,
            metadata={
                "url": url,
                "method": "DELETE",
            },
        )

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