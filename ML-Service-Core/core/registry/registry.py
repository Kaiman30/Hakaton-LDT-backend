"""
Module for managing registries of connectors and interfaces.
Provides decorators for easy registration of new implementations.
"""

from typing import Dict, Type
from core.base_class.base_connector import BaseConnector
from core.base_class.base_interface import BaseInterface
from core.base_class.base_protocol import BaseProtocol
from .base_registry import BaseRegistry


class ConnectorRegistry(BaseRegistry[BaseConnector]):
    """Реестр коннекторов. Метод get() автоматически возвращает Type[BaseConnector]."""
    _REGISTRY: Dict[str, Type[BaseConnector]] = None


class InterfaceRegistry(BaseRegistry[BaseInterface]):
    """Реестр интерфейсов. Метод get() автоматически возвращает Type[BaseInterface]."""
    _REGISTRY: Dict[str, Type[BaseInterface]] = None


class ProtocolRegistry(BaseRegistry[BaseProtocol]):
    """Реестр протоколов. Метод get() автоматически возвращает Type[BaseProtocol]."""
    _REGISTRY: Dict[str, Type[BaseProtocol]] = None
