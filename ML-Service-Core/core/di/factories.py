# core/di/factory.py
"""
Service Factory - Интеграция существующих фабрик с DI контейнером
"""

from contextlib import nullcontext
from typing import Any, Dict, Optional
import logging

from core.di.service_container import Container
from core.base_class.base_connector import BaseConnector
from core.base_class.base_protocol import BaseProtocol
from core.runtime.event_bus import get_event_bus

# Импортируем существующие фабрики
from core.di.factories import (
    ConnectorFactory,
    InterfaceFactory,
    ConnectorSpec,
    InterfaceSpec
)


class ServiceFactory:
    """
    Фабрика сервисов - обертка над существующими фабриками.
    Использует Container для регистрации.

    Соглашение об именах для сервиса ``name``:
    - коннектор лежит в контейнере под ``{name}_connector``;
    - интерфейс лежит под ``name``;
    - если у сервиса нет интерфейса, ``name`` - алиас на ``{name}_connector``,
      так что ``get(name)`` всегда возвращает основной объект сервиса.
    """

    def __init__(self, container: Container):
        self._container = container
        self._logger = logging.getLogger(__name__)

        # Используем существующие фабрики
        self._connector_factory = ConnectorFactory()
        self._interface_factory = InterfaceFactory()

    @staticmethod
    def _connector_key(name: str) -> str:
        return f"{name}_connector"

    # ==================== БАЗОВЫЕ МЕТОДЫ (обертки над существующими фабриками) ====================

    def create_connector(
        self,
        connector_name: str,
        **kwargs
    ) -> BaseConnector:
        """
        Создать коннектор через ConnectorFactory.

        Args:
            connector_name: Имя в ConnectorRegistry
            **kwargs: Параметры для from_config

        Returns:
            Коннектор
        """
        spec = ConnectorSpec(name=connector_name, options=kwargs)
        return self._connector_factory.create(spec)

    def create_interface(
        self,
        interface_name: str,
        connector: BaseConnector,
        **kwargs
    ) -> BaseProtocol:
        """
        Создать интерфейс через InterfaceFactory.

        Args:
            interface_name: Имя в InterfaceRegistry
            connector: Коннектор
            **kwargs: Параметры интерфейса (protocol_name выделяется отдельно)

        Returns:
            Интерфейс
        """
        protocol_name = kwargs.pop('protocol_name', None)

        # Добавляем event_bus если не передан
        if 'event_bus' not in kwargs:
            kwargs['event_bus'] = get_event_bus()

        spec = InterfaceSpec(
            interface_name=interface_name,
            protocol_name=protocol_name,
            options=kwargs
        )

        return self._interface_factory.create(connector, spec)

    # ==================== РЕГИСТРАЦИЯ В КОНТЕЙНЕРЕ ====================

    def register_connector(
        self,
        name: str,
        connector_name: str,
        **kwargs
    ) -> BaseConnector:
        """
        Создать и зарегистрировать коннектор.

        Args:
            name: Имя в контейнере (обычно {service}_connector)
            connector_name: Имя в ConnectorRegistry
            **kwargs: Параметры для from_config

        Returns:
            Коннектор
        """
        connector = self.create_connector(connector_name, **kwargs)
        self._container.register_instance(name, connector)
        self._logger.debug("Registered connector: %s -> %s", name, connector_name)
        return connector

    def register_interface(
        self,
        name: str,
        interface_name: str,
        connector: Optional[BaseConnector] = None,
        **kwargs
    ) -> BaseProtocol:
        """
        Создать и зарегистрировать интерфейс.

        Args:
            name: Имя в контейнере (обычно 'llm', 'storage', etc.)
            interface_name: Имя в InterfaceRegistry
            connector: Коннектор (если None, берется из контейнера)
            **kwargs: Параметры интерфейса

        Returns:
            Интерфейс

        Raises:
            ValueError: Если коннектор не передан и не найден в контейнере
        """
        # Если коннектор не передан - берем из контейнера
        if connector is None:
            connector_key = self._connector_key(name)
            if not self._container.has(connector_key):
                raise ValueError(
                    f"Connector '{connector_key}' for '{name}' not found in container"
                )
            connector = self._container.get(connector_key)

        # Добавляем name в kwargs если не передан
        kwargs.setdefault('name', name)

        # Создаем интерфейс
        interface = self.create_interface(interface_name, connector, **kwargs)

        self._container.register_instance(name, interface)
        self._logger.debug("Registered interface: %s -> %s", name, interface_name)
        return interface

    def register_service(
        self,
        name: str,
        connector_name: str,
        interface_name: str,
        connector_kwargs: Optional[Dict] = None,
        interface_kwargs: Optional[Dict] = None
    ) -> BaseProtocol:
        """
        Создать полный сервис (коннектор + интерфейс).

        Атомарно: если создание интерфейса упало, коннектор
        тоже не остаётся в контейнере.

        Args:
            name: Имя сервиса (будет использовано для получения)
            connector_name: Имя коннектора в ConnectorRegistry
            interface_name: Имя интерфейса в InterfaceRegistry
            connector_kwargs: Параметры для from_config
            interface_kwargs: Параметры интерфейса

        Returns:
            Созданный интерфейс

        Raises:
            ValueError: Если не указан connector_name или interface_name
        """
        if not connector_name:
            raise ValueError(f"Service '{name}': connector name is required")
        if not interface_name:
            raise ValueError(f"Service '{name}': interface name is required")

        connector_kwargs = connector_kwargs or {}
        interface_kwargs = interface_kwargs or {}

        with self._container.transaction():
            # Создаем и регистрируем коннектор
            connector = self.register_connector(
                self._connector_key(name),
                connector_name,
                **connector_kwargs
            )

            # Создаем и регистрируем интерфейс
            interface = self.register_interface(
                name,
                interface_name,
                connector=connector,
                **interface_kwargs
            )

        self._logger.info(
            "Registered service: %s (%s/%s)", name, interface_name, connector_name
        )
        return interface

    # ==================== МАССОВАЯ РЕГИСТРАЦИЯ ====================

    def _register_from_entry(self, name: str, cfg: Dict[str, Any]) -> BaseProtocol:
        """Зарегистрировать один сервис из записи конфига."""
        connector_name = cfg.get('connector')
        interface_name = cfg.get('interface')

        if not connector_name:
            raise ValueError(f"Service '{name}': 'connector' is required in config")

        # Нет интерфейса - регистрируем только коннектор,
        # а name делаем алиасом, чтобы get(name) работал единообразно
        if not interface_name:
            connector_key = self._connector_key(name)
            connector = self.register_connector(
                connector_key,
                connector_name,
                **cfg.get('connector_kwargs', {})
            )
            self._container.register_alias(name, connector_key)
            self._logger.info("Registered only connector: %s", name)
            return connector

        # Полный сервис
        return self.register_service(
            name=name,
            connector_name=connector_name,
            interface_name=interface_name,
            connector_kwargs=cfg.get('connector_kwargs', {}),
            interface_kwargs=cfg.get('interface_kwargs', {})
        )

    def register_services_from_config(
        self,
        services_config: Dict[str, Dict[str, Any]],
        atomic: bool = True
    ) -> Dict[str, BaseProtocol]:
        """
        Зарегистрировать все сервисы из конфига.

        Args:
            services_config: Конфиг сервисов
            atomic: True - при ошибке откатить все регистрации этого вызова;
                    False - оставить то, что успело зарегистрироваться

        Returns:
            Dict созданных интерфейсов (для сервисов без интерфейса - коннекторов)

        Raises:
            ValueError: Некорректная запись конфига
            Exception: Любая ошибка создания сервиса (пробрасывается после отката)
        """
        result: Dict[str, BaseProtocol] = {}

        scope = self._container.transaction() if atomic else nullcontext()
        with scope:
            for name, cfg in services_config.items():
                try:
                    result[name] = self._register_from_entry(name, cfg)
                except Exception as e:
                    self._logger.error("Failed to register '%s': %s", name, e)
                    raise

        return result