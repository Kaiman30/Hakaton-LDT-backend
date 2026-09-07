# core/di/container.py
"""
Dependency Injection Container
Простой реестр зависимостей без лишней логики
"""

from typing import Any, Dict, Callable, Optional, Type, TypeVar, Union
import logging

T = TypeVar('T')


class Container:
    """
    DI контейнер - просто хранит и возвращает зависимости.
    Никакой бизнес-логики, только регистрация и получение.
    """
    
    def __init__(self) -> None:
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._aliases: Dict[str, str] = {}
        self._logger = logging.getLogger(__name__)
    
    # ==================== РЕГИСТРАЦИЯ ====================
    
    def register_instance(self, name: str, instance: Any) -> None:
        """
        Зарегистрировать готовый инстанс.
        
        Args:
            name: Имя сервиса
            instance: Готовый объект
        """
        self._instances[name] = instance
        self._logger.debug(f"Registered instance: {name} -> {type(instance).__name__}")
    
    def register_factory(self, name: str, factory: Callable[[], Any]) -> None:
        """
        Зарегистрировать фабрику для ленивого создания.
        
        Args:
            name: Имя сервиса
            factory: Функция, возвращающая инстанс
        """
        self._factories[name] = factory
        self._logger.debug(f"Registered factory: {name}")
    
    def register_alias(self, alias: str, target: str) -> None:
        """
        Зарегистрировать алиас для сервиса.
        
        Args:
            alias: Псевдоним
            target: Реальное имя сервиса
        """
        self._aliases[alias] = target
        self._logger.debug(f"Registered alias: {alias} -> {target}")
    
    def register_from_registry(
        self,
        name: str,
        registry_type: str,
        registry_name: str,
        **kwargs
    ) -> Any:
        """
        Создать и зарегистрировать объект из реестра.
        
        Args:
            name: Имя сервиса в контейнере
            registry_type: 'connector' или 'interface'
            registry_name: Имя в реестре
            **kwargs: Параметры конструктора
            
        Returns:
            Созданный объект
        """
        from core.registry.registry import ConnectorRegistry, InterfaceRegistry
        
        if registry_type == "connector":
            cls = ConnectorRegistry.get(registry_name)
        elif registry_type == "interface":
            cls = InterfaceRegistry.get(registry_name)
        else:
            raise ValueError(f"Unknown registry type: {registry_type}")
        
        instance = cls(**kwargs)
        self.register_instance(name, instance)
        return instance
    
    # ==================== ПОЛУЧЕНИЕ ====================
    
    def get(self, name: str) -> Any:
        """
        Получить сервис по имени.
        
        Args:
            name: Имя сервиса
            
        Returns:
            Инстанс сервиса
            
        Raises:
            KeyError: Если сервис не найден
        """
        # Проверяем алиас
        actual_name = self._aliases.get(name, name)
        
        # Проверяем готовый инстанс
        if actual_name in self._instances:
            return self._instances[actual_name]
        
        # Проверяем фабрику
        if actual_name in self._factories:
            self._logger.debug(f"Creating instance via factory: {actual_name}")
            instance = self._factories[actual_name]()
            self._instances[actual_name] = instance
            return instance
        
        raise KeyError(f"Service '{name}' not found in container")
    
    def get_typed(self, name: str, expected_type: Type[T]) -> T:
        """
        Получить сервис с проверкой типа.
        
        Args:
            name: Имя сервиса
            expected_type: Ожидаемый тип
            
        Returns:
            Инстанс сервиса
            
        Raises:
            TypeError: Если тип не совпадает
        """
        instance = self.get(name)
        if not isinstance(instance, expected_type):
            raise TypeError(
                f"Service '{name}' is {type(instance).__name__}, "
                f"expected {expected_type.__name__}"
            )
        return instance
    
    # ==================== УДОБНЫЕ ГЕТТЕРЫ ====================
    
    def get_llm(self, name: str = "llm") -> Any:
        """Получить LLM интерфейс."""
        return self.get(name)
    
    def get_queue(self, name: str = "queue") -> Any:
        """Получить Queue интерфейс."""
        return self.get(name)
    
    def get_storage(self, name: str = "storage") -> Any:
        """Получить Storage интерфейс."""
        return self.get(name)
    
    def get_db(self, name: str = "db") -> Any:
        """Получить DB интерфейс."""
        return self.get(name)
    
    def get_http(self, name: str = "http") -> Any:
        """Получить HTTP интерфейс."""
        return self.get(name)
    
    def get_connector(self, name: str) -> Any:
        """Получить коннектор по имени."""
        return self.get(name)
    
    def get_interface(self, name: str) -> Any:
        """Получить интерфейс по имени."""
        return self.get(name)
    
    # ==================== УТИЛИТЫ ====================
    
    def has(self, name: str) -> bool:
        """Проверить наличие сервиса."""
        actual_name = self._aliases.get(name, name)
        return (
            actual_name in self._instances or 
            actual_name in self._factories
        )
    
    def remove(self, name: str) -> None:
        """Удалить сервис."""
        actual_name = self._aliases.get(name, name)
        self._instances.pop(actual_name, None)
        self._factories.pop(actual_name, None)
        self._aliases.pop(name, None)
    
    def clear(self) -> None:
        """Очистить все сервисы."""
        self._instances.clear()
        self._factories.clear()
        self._aliases.clear()
    
    def list_services(self) -> Dict[str, str]:
        """Список всех сервисов."""
        result = {}
        for name, inst in self._instances.items():
            result[name] = type(inst).__name__
        for name in self._factories:
            if name not in result:
                result[name] = "Factory (not instantiated)"
        for alias, target in self._aliases.items():
            result[f"{alias} -> {target}"] = "Alias"
        return result