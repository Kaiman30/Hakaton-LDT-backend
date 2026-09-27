# core/di/service_container.py
"""
Dependency Injection Container
Простой потокобезопасный реестр зависимостей без бизнес-логики.
Поддерживает управление жизненным циклом (Lifecycle) зарегистрированных компонентов.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Set, Type, TypeVar

from core.base_class.lifecycle import Lifecycle

T = TypeVar("T")

_MISSING = object()


class Container:
    """
    DI контейнер - хранит и возвращает зависимости.
    Управляет инициализацией и остановкой Lifecycle-совместимых объектов.
    """

    def __init__(self) -> None:
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._transient: Set[str] = set()
        self._aliases: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._logger = logging.getLogger(__name__)

    # ==================== ВНУТРЕННИЕ ХЕЛПЕРЫ ====================

    def _unregister(self, name: str) -> None:
        """Убрать имя из всех реестров. Вызывать только под self._lock."""
        self._instances.pop(name, None)
        self._factories.pop(name, None)
        self._transient.discard(name)
        self._aliases.pop(name, None)

    def _resolve(self, name: str) -> str:
        """Пройти цепочку алиасов до реального имени сервиса."""
        seen: Set[str] = set()
        while name in self._aliases:
            if name in seen:
                raise RuntimeError(f"Alias cycle detected at '{name}'")
            seen.add(name)
            name = self._aliases[name]
        return name

    # ==================== УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ ====================

    async def start_all(self) -> None:
        """
        Инициализировать все созданные экземпляры,
        реализующие протокол Lifecycle.
        """
        with self._lock:
            instances = list(self._instances.values())

        for instance in instances:
            if isinstance(instance, Lifecycle):
                try:
                    self._logger.info("Initializing service: %s", getattr(instance, "name", type(instance).__name__))
                    await instance.initialize()
                except Exception as e:
                    self._logger.error("Failed to initialize service %s: %s", instance, e)
                    raise

    async def stop_all(self) -> None:
        """
        Корректно завершить работу всех экземпляров,
        реализующих протокол Lifecycle.
        """
        with self._lock:
            instances = list(self._instances.values())

        for instance in reversed(instances):
            if isinstance(instance, Lifecycle):
                try:
                    self._logger.info("Shutting down service: %s", getattr(instance, "name", type(instance).__name__))
                    await instance.shutdown()
                except Exception as e:
                    self._logger.error("Error during shutdown of service %s: %s", instance, e)

    async def check_all_health(self) -> Dict[str, bool]:
        """
        Проверить работоспособность всех Lifecycle-сервисов.

        Returns:
            Словарь вида {'имя_сервиса': status_bool}
        """
        statuses: Dict[str, bool] = {}
        with self._lock:
            items = list(self._instances.items())

        for name, instance in items:
            if isinstance(instance, Lifecycle):
                try:
                    statuses[name] = await instance.check_health()
                except Exception as e:
                    self._logger.warning("Healthcheck failed for '%s': %s", name, e)
                    statuses[name] = False
        return statuses

    # ==================== РЕГИСТРАЦИЯ ====================

    def register_instance(self, name: str, instance: Any) -> None:
        """Зарегистрировать готовый инстанс."""
        with self._lock:
            self._unregister(name)
            self._instances[name] = instance
        self._logger.debug(
            "Registered instance: %s -> %s", name, type(instance).__name__
        )

    def register_factory(
        self,
        name: str,
        factory: Callable[[], Any],
        *,
        singleton: bool = True,
    ) -> None:
        """Зарегистрировать фабрику для ленивого создания."""
        with self._lock:
            self._unregister(name)
            self._factories[name] = factory
            if not singleton:
                self._transient.add(name)
        self._logger.debug(
            "Registered factory: %s (%s)",
            name,
            "singleton" if singleton else "transient",
        )

    def register_alias(self, alias: str, target: str) -> None:
        """Зарегистрировать алиас для сервиса."""
        with self._lock:
            current = target
            while True:
                if current == alias:
                    raise ValueError(
                        f"Alias '{alias}' -> '{target}' would create a cycle"
                    )
                nxt = self._aliases.get(current)
                if nxt is None:
                    break
                current = nxt

            self._unregister(alias)
            self._aliases[alias] = target
        self._logger.debug("Registered alias: %s -> %s", alias, target)

    # ==================== ПОЛУЧЕНИЕ ====================

    def get(self, name: str) -> Any:
        """Получить сервис по имени."""
        instance = self._instances.get(self._resolve(name), _MISSING)
        if instance is not _MISSING:
            return instance

        with self._lock:
            actual_name = self._resolve(name)
            if actual_name in self._instances:
                return self._instances[actual_name]

            factory = self._factories.get(actual_name)
            if factory is None:
                raise KeyError(f"Service '{name}' not found in container")

            self._logger.debug("Creating instance via factory: %s", actual_name)

            if actual_name not in self._transient:
                instance = factory()
                self._instances[actual_name] = instance
                return instance

        return factory()

    def get_typed(self, name: str, expected_type: Type[T]) -> T:
        """Получить сервис с проверкой типа."""
        instance = self.get(name)
        expected_name = getattr(expected_type, "__name__", repr(expected_type))

        try:
            matches = isinstance(instance, expected_type)
        except TypeError as e:
            raise TypeError(
                f"Cannot check service '{name}' against {expected_name}: {e}. "
                f"For Protocol types use @runtime_checkable."
            ) from e

        if not matches:
            raise TypeError(
                f"Service '{name}' is {type(instance).__name__}, "
                f"expected {expected_name}"
            )
        return instance

    # ==================== УТИЛИТЫ ====================

    def has(self, name: str) -> bool:
        """Проверить наличие сервиса."""
        with self._lock:
            actual_name = self._resolve(name)
            return actual_name in self._instances or actual_name in self._factories

    def remove(self, name: str) -> None:
        """Удалить сервис или алиас."""
        with self._lock:
            if name in self._aliases:
                del self._aliases[name]
                return

            self._unregister(name)

            dead = {name}
            while True:
                dangling = [a for a, t in self._aliases.items() if t in dead]
                if not dangling:
                    break
                for alias in dangling:
                    del self._aliases[alias]
                    dead.add(alias)

    def clear(self) -> None:
        """Очистить все сервисы и алиасы."""
        with self._lock:
            self._instances.clear()
            self._factories.clear()
            self._transient.clear()
            self._aliases.clear()

    def list_services(self) -> Dict[str, str]:
        """Список зарегистрированных сервисов."""
        with self._lock:
            result: Dict[str, str] = {
                name: type(inst).__name__ for name, inst in self._instances.items()
            }
            for name in self._factories:
                if name not in result:
                    result[name] = (
                        "Factory (transient)"
                        if name in self._transient
                        else "Factory (not instantiated)"
                    )
            return result

    def list_aliases(self) -> Dict[str, str]:
        """Список алиасов."""
        with self._lock:
            return dict(self._aliases)

    @contextmanager
    def transaction(self) -> Iterator["Container"]:
        """Атомарный транзакционный блок регистрации."""
        with self._lock:
            snapshot = (
                dict(self._instances),
                dict(self._factories),
                set(self._transient),
                dict(self._aliases),
            )
            try:
                yield self
            except BaseException:
                self._instances.clear()
                self._instances.update(snapshot[0])
                self._factories.clear()
                self._factories.update(snapshot[1])
                self._transient.clear()
                self._transient.update(snapshot[2])
                self._aliases.clear()
                self._aliases.update(snapshot[3])
                self._logger.debug("Container transaction rolled back")
                raise