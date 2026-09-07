# core/runtime/app_state_machine.py
"""
AppStateMachine - рантайм приложения.
Управляет состояниями сервисов через EventBus.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Dict, List

from core.di.service_container import Container
from core.di.factories import ServiceFactory
from core.runtime.event_bus import get_event_bus, EventType


class AppState(str, Enum):
    """Состояние приложения."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class ServiceState(str, Enum):
    """Состояние сервиса."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class AppStateMachine:
    """
    AppStateMachine - рантайм приложения.
    
    Отвечает за:
    - Загрузку и валидацию конфигов
    - Прокидывание конфигов в DI
    - Управление состояниями сервисов
    - Публикацию событий в EventBus (observability)
    """
    
    def __init__(self, container: Container):
        self._container = container
        self._factory = ServiceFactory(container)
        self._event_bus = get_event_bus()
        self._logger = logging.getLogger(__name__)
        
        # Состояние приложения
        self._app_state = AppState.UNINITIALIZED
        self._services: Dict[str, Any] = {}  # name -> service (interface or custom)
        self._service_states: Dict[str, ServiceState] = {}
        self._service_health: Dict[str, bool] = {}
        self._start_time: Optional[datetime] = None
        self._stop_time: Optional[datetime] = None
    
    # ==================== КОНФИГИ ====================
    
    def load_config(self, config_path: str, schema: type) -> dict:
        """
        Загрузить и валидировать конфиг.
        
        Args:
            config_path: Путь к конфигу
            schema: Pydantic схема для валидации
            
        Returns:
            Валидированный конфиг
        """
        # Загрузка из файла (.env, .json, .yaml)
        raw_config = self._load_from_file(config_path)
        
        # Валидация через Pydantic
        validated = schema(**raw_config)
        
        # Сохраняем в контейнер
        config_name = schema.__name__.replace("Config", "").lower()
        self._container.register(f"{config_name}_config", validated)
        
        self._logger.info(f"Loaded config: {config_name}")
        return validated
    
    def _load_from_file(self, path: str) -> dict:
        """Загрузка конфига из файла."""
        # Реализация загрузки из .env, .json, .yaml
        if path.endswith('.json'):
            import json
            with open(path) as f:
                return json.load(f)
        elif path.endswith('.env'):
            # Загрузка .env через python-dotenv
            from dotenv import dotenv_values
            return dotenv_values(path)
        else:
            raise ValueError(f"Unsupported config format: {path}")
    
    # ==================== РЕГИСТРАЦИЯ СЕРВИСОВ ====================
    
    def register_service(
        self,
        name: str,
        connector_name: str,
        interface_name: str,
        connector_kwargs: dict = None,
        interface_kwargs: dict = None
    ) -> None:
        """
        Зарегистрировать сервис (коннектор + интерфейс из SDK).
        """
        connector_kwargs = connector_kwargs or {}
        interface_kwargs = interface_kwargs or {}
        
        # Добавляем event_bus для observability
        if 'event_bus' not in interface_kwargs:
            interface_kwargs['event_bus'] = self._event_bus
        
        # Создаем через фабрику
        interface = self._factory.register_service(
            name=name,
            connector_name=connector_name,
            interface_name=interface_name,
            connector_kwargs=connector_kwargs,
            interface_kwargs=interface_kwargs
        )
        
        self._services[name] = interface
        self._service_states[name] = ServiceState.UNINITIALIZED
        self._service_health[name] = False
        
        self._logger.info(f"Registered service: {name} ({interface_name}/{connector_name})")
    
    def register_custom_service(self, name: str, service_instance: Any) -> None:
        """
        Зарегистрировать кастомный сервис разработчика.
        
        Args:
            name: Имя сервиса
            service_instance: Инстанс сервиса
        """
        self._container.register(name, service_instance)
        self._services[name] = service_instance
        self._service_states[name] = ServiceState.UNINITIALIZED
        self._service_health[name] = False
        
        self._logger.info(f"Registered custom service: {name}")
    
    # ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================
    
    async def initialize(self, timeout: float = 30.0) -> bool:
        """
        Инициализировать все сервисы.
        """
        if self._app_state != AppState.UNINITIALIZED:
            return False
        
        self._app_state = AppState.INITIALIZING
        self._start_time = datetime.now()
        
        await self._event_bus.publish(
            EventType.CONNECTOR_INITIALIZED,
            {"app_state": "initializing"}
        )
        
        results = {}
        tasks = {}
        
        for name, service in self._services.items():
            self._service_states[name] = ServiceState.INITIALIZING
            tasks[name] = asyncio.create_task(
                self._initialize_one(name, service, timeout)
            )
        
        for name, task in tasks.items():
            try:
                success = await task
                results[name] = success
                self._service_states[name] = (
                    ServiceState.RUNNING if success else ServiceState.ERROR
                )
                self._service_health[name] = success
            except Exception as e:
                self._logger.error(f"Error initializing {name}: {e}")
                results[name] = False
                self._service_states[name] = ServiceState.ERROR
        
        success = all(results.values())
        self._app_state = AppState.RUNNING if success else AppState.ERROR
        
        await self._event_bus.publish(
            EventType.CONNECTOR_INITIALIZED,
            {"app_state": self._app_state.value, "results": results}
        )
        
        return success
    
    async def _initialize_one(self, name: str, service: Any, timeout: float) -> bool:
        """Инициализировать один сервис."""
        try:
            if hasattr(service, 'initialize'):
                await asyncio.wait_for(service.initialize(), timeout=timeout)
            self._logger.info(f"Initialized: {name}")
            return True
        except asyncio.TimeoutError:
            self._logger.error(f"Timeout initializing {name}")
            return False
        except Exception as e:
            self._logger.error(f"Error initializing {name}: {e}")
            return False
    
    async def start(self, timeout: float = 30.0) -> bool:
        """
        Запустить все сервисы.
        """
        if self._app_state == AppState.RUNNING:
            return True
        
        if self._app_state == AppState.UNINITIALIZED:
            if not await self.initialize(timeout):
                return False
        
        self._app_state = AppState.RUNNING
        
        await self._event_bus.publish(
            EventType.CONNECTOR_INITIALIZED,
            {"app_state": "running"}
        )
        
        self._logger.info("Application started")
        return True
    
    async def stop(self, timeout: float = 10.0) -> bool:
        """
        Остановить все сервисы.
        """
        if self._app_state in (AppState.STOPPED, AppState.UNINITIALIZED):
            return True
        
        self._app_state = AppState.STOPPING
        self._stop_time = datetime.now()
        
        await self._event_bus.publish(
            EventType.CONNECTOR_SHUTDOWN,
            {"app_state": "stopping"}
        )
        
        results = {}
        for name, service in self._services.items():
            self._service_states[name] = ServiceState.STOPPING
            try:
                if hasattr(service, 'shutdown'):
                    await asyncio.wait_for(service.shutdown(), timeout=timeout)
                self._service_states[name] = ServiceState.STOPPED
                results[name] = True
                self._logger.info(f"Stopped: {name}")
            except asyncio.TimeoutError:
                self._logger.error(f"Timeout stopping {name}")
                results[name] = False
                self._service_states[name] = ServiceState.ERROR
            except Exception as e:
                self._logger.error(f"Error stopping {name}: {e}")
                results[name] = False
                self._service_states[name] = ServiceState.ERROR
        
        self._app_state = AppState.STOPPED
        
        await self._event_bus.publish(
            EventType.CONNECTOR_SHUTDOWN,
            {"app_state": "stopped", "results": results}
        )
        
        return all(results.values())
    
    async def health_check(self) -> Dict[str, bool]:
        """
        Проверить здоровье всех сервисов.
        """
        results = {}
        
        for name, service in self._services.items():
            try:
                if hasattr(service, 'check_health'):
                    healthy = await service.check_health()
                elif hasattr(service, 'health_check'):
                    healthy = await service.health_check()
                else:
                    healthy = True
                
                results[name] = healthy
                self._service_health[name] = healthy
                
                if not healthy:
                    self._logger.warning(f"Service {name} is unhealthy")
                
            except Exception as e:
                self._logger.error(f"Health check failed for {name}: {e}")
                results[name] = False
                self._service_health[name] = False
        
        return results
    
    # ==================== ПОЛУЧЕНИЕ СЕРВИСОВ ====================
    
    def get_service(self, name: str) -> Optional[Any]:
        """Получить сервис по имени."""
        return self._services.get(name)
    
    def get_llm(self, name: str = "llm") -> Optional[Any]:
        return self._services.get(name)
    
    def get_storage(self, name: str = "storage") -> Optional[Any]:
        return self._services.get(name)
    
    def get_queue(self, name: str = "queue") -> Optional[Any]:
        return self._services.get(name)
    
    def get_db(self, name: str = "db") -> Optional[Any]:
        return self._services.get(name)
    
    def get_http(self, name: str = "http") -> Optional[Any]:
        return self._services.get(name)
    
    def list_services(self) -> List[str]:
        return list(self._services.keys())
    
    # ==================== СОСТОЯНИЕ ====================
    
    def get_state(self) -> Dict[str, Any]:
        """Получить состояние приложения."""
        return {
            "app_state": self._app_state.value,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "stop_time": self._stop_time.isoformat() if self._stop_time else None,
            "uptime": (datetime.now() - self._start_time).total_seconds() if self._start_time else 0,
            "services": self.get_services_state()
        }
    
    def get_services_state(self) -> Dict[str, Dict[str, Any]]:
        """Получить состояние всех сервисов."""
        return {
            name: {
                "state": self._service_states.get(name, ServiceState.UNINITIALIZED).value,
                "healthy": self._service_health.get(name, False)
            }
            for name in self._services.keys()
        }
    
    def get_service_state(self, name: str) -> Optional[Dict[str, Any]]:
        """Получить состояние конкретного сервиса."""
        if name not in self._services:
            return None
        
        return {
            "state": self._service_states.get(name, ServiceState.UNINITIALIZED).value,
            "healthy": self._service_health.get(name, False)
        }
    
    @property
    def is_running(self) -> bool:
        return self._app_state == AppState.RUNNING