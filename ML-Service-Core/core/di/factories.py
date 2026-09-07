# core/di/factory.py
"""
Service Factory - Интеграция существующих фабрик с DI контейнером
"""

from typing import Any, Dict, Optional, List
import logging

from core.di.service_container import Container
from core.base_class.base_connector import BaseConnector
from core.base_class.base_interface import BaseInterface
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
    """
    
    def __init__(self, container: Container):
        self._container = container
        self._logger = logging.getLogger(__name__)
        
        # Используем существующие фабрики
        self._connector_factory = ConnectorFactory()
        self._interface_factory = InterfaceFactory()
    
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
            **kwargs: Параметры интерфейса
            
        Returns:
            Интерфейс
        """
        # Добавляем event_bus если не передан
        if 'event_bus' not in kwargs:
            kwargs['event_bus'] = get_event_bus()
        
        spec = InterfaceSpec(
            interface_name=interface_name,
            protocol_name=kwargs.pop('protocol_name', None),
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
        self._logger.debug(f"Registered connector: {name} -> {connector_name}")
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
        """
        # Если коннектор не передан - берем из контейнера
        if connector is None:
            connector = self._container.get(f"{name}_connector")
            if connector is None:
                raise ValueError(f"Connector for '{name}' not found in container")
        
        # Добавляем name в kwargs если не передан
        if 'name' not in kwargs:
            kwargs['name'] = name
        
        # Создаем интерфейс
        interface = self.create_interface(interface_name, connector, **kwargs)
        
        self._container.register_instance(name, interface)
        self._logger.debug(f"Registered interface: {name} -> {interface_name}")
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
        
        Args:
            name: Имя сервиса (будет использовано для получения)
            connector_name: Имя коннектора в ConnectorRegistry
            interface_name: Имя интерфейса в InterfaceRegistry
            connector_kwargs: Параметры для from_config
            interface_kwargs: Параметры интерфейса
            
        Returns:
            Созданный интерфейс
        """
        connector_kwargs = connector_kwargs or {}
        interface_kwargs = interface_kwargs or {}
        
        # Создаем и регистрируем коннектор
        connector = self.register_connector(
            f"{name}_connector",
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
        
        self._logger.info(f"Registered service: {name} ({interface_name}/{connector_name})")
        return interface
    
    # ==================== МАССОВАЯ РЕГИСТРАЦИЯ ====================
    
    def register_services_from_config(
        self,
        services_config: Dict[str, Dict[str, Any]]
    ) -> Dict[str, BaseProtocol]:
        """
        Зарегистрировать все сервисы из конфига.
        
        Args:
            services_config: Конфиг сервисов
            
        Returns:
            Dict созданных интерфейсов
        """
        result = {}
        
        for name, cfg in services_config.items():
            try:
                connector_name = cfg.get('connector')
                interface_name = cfg.get('interface')
                
                # Если нет интерфейса - регистрируем только коннектор
                if not interface_name:
                    if connector_name:
                        connector = self.register_connector(
                            name,
                            connector_name,
                            **cfg.get('connector_kwargs', {})
                        )
                        result[name] = connector
                        self._logger.info(f"Registered only connector: {name}")
                    continue
                
                # Полный сервис
                interface = self.register_service(
                    name=name,
                    connector_name=connector_name,
                    interface_name=interface_name,
                    connector_kwargs=cfg.get('connector_kwargs', {}),
                    interface_kwargs=cfg.get('interface_kwargs', {})
                )
                
                result[name] = interface
                self._logger.info(f"Registered service: {name}")
                
            except Exception as e:
                self._logger.error(f"Failed to register '{name}': {e}")
                raise
        
        return result