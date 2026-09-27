# core/runtime/service_runtime.py
"""
ServiceRuntime - рантайм ОДНОГО сервиса.

Отвечает за:
- состояние сервиса (конечный автомат с проверкой переходов);
- вызов хуков жизненного цикла сервиса (initialize / shutdown / check_health);
- API для общения с шиной: все события рантайма публикуются с source=<имя сервиса>.

Не знает про DI-контейнер, фабрики и конфиги: получает готовый объект сервиса.
Несколько сервисов объединяются в Pipeline (core/runtime/pipeline.py).

Пример:
    bus = get_event_bus()
    iface = factory.register_service(
        "llm", "openai", "llm_interface",
        interface_kwargs={"event_bus": bus.scoped("llm")},  # события интерфейса тоже с source="llm"
    )
    runtime = ServiceRuntime("llm", iface, bus)
    await runtime.start()
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, Optional, Tuple, Union

from core.runtime.event_bus import (
    EventCallback,
    EventType,
    Payload,
    RuntimeEventBus,
    ScopedEventBus,
    get_event_bus,
)


class ServiceState(str, Enum):
    """Состояние сервиса."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# Допустимые переходы. Всё, чего здесь нет, - ошибка программиста.
_TRANSITIONS: Dict[ServiceState, FrozenSet[ServiceState]] = {
    ServiceState.UNINITIALIZED: frozenset({ServiceState.INITIALIZING}),
    ServiceState.INITIALIZING: frozenset({ServiceState.RUNNING, ServiceState.ERROR}),
    ServiceState.RUNNING: frozenset({ServiceState.DEGRADED, ServiceState.STOPPING}),
    ServiceState.DEGRADED: frozenset({ServiceState.RUNNING, ServiceState.STOPPING}),
    ServiceState.STOPPING: frozenset({ServiceState.STOPPED, ServiceState.ERROR}),
    ServiceState.STOPPED: frozenset({ServiceState.INITIALIZING}),          # перезапуск
    ServiceState.ERROR: frozenset({ServiceState.INITIALIZING,              # повторная попытка
                                   ServiceState.STOPPING}),                # очистка ресурсов
}

_HEALTH_HOOKS = ("check_health", "health_check")


class InvalidTransitionError(RuntimeError):
    """Недопустимый переход между состояниями сервиса."""


class ServiceRuntime:
    """Рантайм одного сервиса: состояние + жизненный цикл + API к шине."""

    def __init__(
        self,
        name: str,
        service: Any,
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        """
        Args:
            name: Имя сервиса (используется как source событий)
            service: Готовый объект сервиса. Необязательные хуки (sync или async):
                     initialize(), shutdown(), check_health() / health_check()
            event_bus: Шина; по умолчанию глобальная
        """
        if not name:
            raise ValueError("ServiceRuntime requires a non-empty name")

        self._name = name
        self._service = service
        self._bus = event_bus or get_event_bus()
        self._events: ScopedEventBus = self._bus.scoped(name)
        self._logger = logging.getLogger(f"{__name__}.{name}")

        self._state = ServiceState.UNINITIALIZED
        self._last_error: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._t_started: Optional[float] = None  # monotonic
        self._t_stopped: Optional[float] = None  # monotonic

        # Lock создаётся лениво: на Python < 3.10 asyncio.Lock привязывается к циклу
        # в момент создания, а рантайм могут создать до asyncio.run().
        self._lock: Optional[asyncio.Lock] = None

    # ==================== СВОЙСТВА ====================

    @property
    def name(self) -> str:
        return self._name

    @property
    def service(self) -> Any:
        return self._service

    @property
    def state(self) -> ServiceState:
        return self._state

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def is_running(self) -> bool:
        """Сервис поднят (RUNNING или DEGRADED)."""
        return self._state in (ServiceState.RUNNING, ServiceState.DEGRADED)

    @property
    def is_healthy(self) -> bool:
        """Сервис поднят и последняя проверка здоровья успешна."""
        return self._state is ServiceState.RUNNING

    @property
    def events(self) -> ScopedEventBus:
        """Шина, привязанная к этому сервису (source=name)."""
        return self._events

    # ==================== API ШИНЫ ====================

    async def publish(self, event_type: Union[str, Enum], payload: Optional[Payload] = None) -> None:
        """Опубликовать событие от имени этого сервиса."""
        await self._events.publish(event_type, payload)

    def subscribe(self, event_type: Union[str, Enum], callback: EventCallback) -> None:
        """Подписаться на события ТОЛЬКО этого сервиса."""
        self._events.subscribe(event_type, callback)

    def unsubscribe(self, event_type: Union[str, Enum], callback: EventCallback) -> None:
        self._events.unsubscribe(event_type, callback)

    # ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

    async def start(self, timeout: Optional[float] = 30.0) -> bool:
        """
        Поднять сервис (хук initialize()).

        Идемпотентно: если сервис уже поднят - True. Из ERROR и STOPPED
        можно запустить повторно. Параллельные вызовы сериализуются.

        Returns:
            True, если сервис в RUNNING/DEGRADED
        """
        async with self._get_lock():
            if self.is_running:
                return True

            await self._transition(ServiceState.INITIALIZING)
            try:
                ok, _, error = await self._call_hook("initialize", timeout)
            except asyncio.CancelledError:
                await self._transition(ServiceState.ERROR, "cancelled during initialize")
                raise

            if ok:
                await self._transition(ServiceState.RUNNING)
            else:
                await self._transition(ServiceState.ERROR, error)
            return ok

    async def stop(self, timeout: Optional[float] = 10.0) -> bool:
        """
        Остановить сервис (хук shutdown()).

        Идемпотентно: для UNINITIALIZED/STOPPED - True. Из ERROR вызывается
        для очистки ресурсов после неудачного запуска.

        Returns:
            True, если сервис остановлен
        """
        async with self._get_lock():
            if self._state in (ServiceState.UNINITIALIZED, ServiceState.STOPPED):
                return True

            await self._transition(ServiceState.STOPPING)
            try:
                ok, _, error = await self._call_hook("shutdown", timeout)
            except asyncio.CancelledError:
                await self._transition(ServiceState.ERROR, "cancelled during shutdown")
                raise

            if ok:
                await self._transition(ServiceState.STOPPED)
            else:
                await self._transition(ServiceState.ERROR, error)
            return ok

    async def check_health(self, timeout: Optional[float] = 5.0) -> bool:
        """
        Проверить здоровье сервиса (вызов метода check_health()).

        Для незапущенного сервиса возвращает False без публикации событий.
        Состояние RUNNING <-> DEGRADED переключается по результату.
        """
        if not self.is_running:
            return False

        error: Optional[str] = None
        hook = getattr(self._service, "check_health", None)

        if not callable(hook):
            healthy = True
        else:
            ok, result, error = await self._call_hook("check_health", timeout)
            healthy = ok and bool(result)
            if ok and not healthy:
                error = "check_health() reported unhealthy"

        if self._state is ServiceState.RUNNING and not healthy:
            await self._transition(ServiceState.DEGRADED, error)
        elif self._state is ServiceState.DEGRADED and healthy:
            await self._transition(ServiceState.RUNNING)

        if not healthy:
            self._logger.warning("Service %s is unhealthy: %s", self._name, error)

        await self._events.publish(
            EventType.HEALTH_CHECK,
            {"service": self._name, "healthy": healthy, "error": error},
        )
        return healthy

    # ==================== СОСТОЯНИЕ ====================

    def get_state(self) -> Dict[str, Any]:
        """Снимок состояния сервиса."""
        if self._t_started is None:
            uptime = 0.0
        else:
            end = self._t_stopped if self._t_stopped is not None else time.monotonic()
            uptime = end - self._t_started

        return {
            "name": self._name,
            "state": self._state.value,
            "healthy": self.is_healthy,
            "last_error": self._last_error,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
            "uptime": uptime,
        }

    # ==================== ВНУТРЕННЕЕ ====================

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _set_state(self, new: ServiceState, error: Optional[str] = None) -> None:
        """Синхронно сменить состояние с проверкой перехода и обновить метки времени."""
        old = self._state
        if new not in _TRANSITIONS[old]:
            raise InvalidTransitionError(
                f"Service '{self._name}': {old.value} -> {new.value} is not allowed"
            )

        now = datetime.now(timezone.utc)
        self._state = new
        self._last_error = error  # причина текущего состояния; None очищает

        if new is ServiceState.INITIALIZING:
            self._started_at = self._stopped_at = None
            self._t_started = self._t_stopped = None
        elif new is ServiceState.RUNNING and old is ServiceState.INITIALIZING:
            # RUNNING <-> DEGRADED аптайм не сбрасывает
            self._started_at = now
            self._t_started = time.monotonic()
        elif new is ServiceState.STOPPING:
            self._stopped_at = now
            self._t_stopped = time.monotonic()

    async def _transition(self, new: ServiceState, error: Optional[str] = None) -> None:
        """Сменить состояние и опубликовать событие. Состояние меняется до публикации."""
        old = self._state
        self._set_state(new, error)

        if new is ServiceState.ERROR:
            self._logger.error("%s: %s -> %s (%s)", self._name, old.value, new.value, error)
        else:
            self._logger.info("%s: %s -> %s", self._name, old.value, new.value)

        await self._events.publish(
            EventType.SERVICE_STATE_CHANGED,
            {
                "service": self._name,
                "from": old.value,
                "to": new.value,
                "error": self._last_error,
            },
        )

    async def _call_hook(
        self, hook_name: str, timeout: Optional[float]
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Вызвать хук сервиса (sync или async) с таймаутом.

        Returns:
            (успех, результат хука, текст ошибки). Отсутствующий хук - успех.
            Исключение наружу не выходит (кроме CancelledError).
        """
        hook: Optional[Callable[[], Any]] = getattr(self._service, hook_name, None)
        if not callable(hook):
            return True, None, None

        try:
            result = hook()
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout)
            return True, result, None
        except asyncio.TimeoutError:
            message = f"{hook_name}() timed out after {timeout}s"
            self._logger.error("%s: %s", self._name, message)
            return False, None, message
        except Exception as e:
            self._logger.exception("%s: %s() failed", self._name, hook_name)
            return False, None, f"{type(e).__name__}: {e}"