from typing import Any, Dict, Generic, Type, TypeVar, Callable, cast

T = TypeVar("T")  # Тип хранимых объектов
R = TypeVar("R")  # Тип декорируемого класса

class BaseRegistry(Generic[T]):
    _REGISTRY: Dict[str, Type[T]] = None
    
    @classmethod
    def _get_registry(cls) -> Dict[str, Type[T]]:
        if cls._REGISTRY is None or "_REGISTRY" not in cls.__dict__:
            cls._REGISTRY = {}
        return cls._REGISTRY
    
    @classmethod
    def register(cls, name: str):
        """
        Декоратор для регистрации компонентов.
        Использует отдельный TypeVar R для сохранения точного типа.
        """
        def decorator(subclass: R) -> R:
            registry = cls._get_registry()
            if name in registry:
                raise ValueError(
                    f"Компонент с именем '{name}' уже зарегистрирован в {cls.__name__}."
                )
            # Приводим к Type[T] для хранения
            registry[name] = cast(Type[T], subclass)
            return subclass
        
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Type[T]:
        registry = cls._get_registry()
        if name not in registry:
            raise KeyError(
                f"Компонент '{name}' не найден в {cls.__name__}. "
                f"Доступные: {list(registry.keys())}"
            )
        return registry[name]