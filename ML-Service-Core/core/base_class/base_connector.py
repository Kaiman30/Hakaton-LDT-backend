"""
Base connector helper class.
Provides common state management (name, health status) for real adapter implementations.
"""

from __future__ import annotations

import abc
from typing import Any


class BaseConnector(abc.ABC):
    """
    Optional helper base class for concrete connectors.
    Implements common name and health state management.
    """

    def __init__(self, name: str) -> None:
        self._name: str = name
        self._healthy: bool = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def healthy(self) -> bool:
        """Fast cached health indicator."""
        return self._healthy

    def _set_health(self, value: bool) -> None:
        self._healthy = value

    @classmethod
    def from_config(cls, config: Any, **kwargs: Any) -> BaseConnector:
        raise NotImplementedError(f"{cls.__name__} must implement from_config()")

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Allocate resources (connection pools, client sessions, threads)."""

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Cleanly release all resources."""

    @abc.abstractmethod
    async def check_health(self) -> bool:
        """Perform a real remote health check and update cached state."""