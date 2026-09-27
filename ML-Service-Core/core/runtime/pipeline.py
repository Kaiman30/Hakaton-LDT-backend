# core/runtime/pipeline.py
"""
Pipeline - упорядоченная группа ServiceRuntime.

Один сервис - один ServiceRuntime; Pipeline лишь координирует несколько:
- запуск строго в заданном порядке (порядок = порядок зависимостей);
- откат при неудачном запуске;
- остановка в обратном порядке;
- агрегированное здоровье и состояние.

Состояниями отдельных сервисов Pipeline не управляет - только вызывает их start/stop.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from core.runtime.event_bus import EventType, RuntimeEventBus, ScopedEventBus, get_event_bus
from core.runtime.app_state import ServiceRuntime


class PipelineState(str, Enum):
    """Состояние пайплайна."""
    UNINITIALIZED = "uninitialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class Pipeline:
    """Упорядоченная группа сервисов со скоординированным жизненным циклом."""

    def __init__(
        self,
        name: str,
        runtimes: Sequence[ServiceRuntime],
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        """
        Args:
            name: Имя пайплайна (source его событий)
            runtimes: Рантаймы в порядке запуска (зависимости - раньше зависимых)
            event_bus: Шина; по умолчанию глобальная
        """
        if not name:
            raise ValueError("Pipeline requires a non-empty name")

        names = [rt.name for rt in runtimes]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"Duplicate service names in pipeline '{name}': {duplicates}")

        self._name = name
        self._runtimes: List[ServiceRuntime] = list(runtimes)
        self._events: ScopedEventBus = (event_bus or get_event_bus()).scoped(name)
        self._logger = logging.getLogger(f"{__name__}.{name}")

        self._state = PipelineState.UNINITIALIZED
        self._last_error: Optional[str] = None
        self._lock: Optional[asyncio.Lock] = None  # лениво, см. ServiceRuntime

    # ==================== СВОЙСТВА ====================

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> PipelineState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state is PipelineState.RUNNING

    @property
    def runtimes(self) -> List[ServiceRuntime]:
        return list(self._runtimes)

    def get_runtime(self, name: str) -> Optional[ServiceRuntime]:
        return next((rt for rt in self._runtimes if rt.name == name), None)

    # ==================== ЖИЗНЕННЫЙ ЦИКЛ ====================

    async def start(self, timeout: Optional[float] = 30.0) -> bool:
        """
        Запустить сервисы по очереди в заданном порядке.

        Если сервис не поднялся, уже запущенные (и сам упавший, он мог занять ресурсы)
        останавливаются в обратном порядке, пайплайн уходит в ERROR. После этого
        start() можно вызвать снова.

        Args:
            timeout: Таймаут запуска КАЖДОГО сервиса

        Returns:
            True, если все сервисы подняты
        """
        async with self._get_lock():
            if self._state is PipelineState.RUNNING:
                return True

            await self._set_state(PipelineState.STARTING)
            attempted: List[ServiceRuntime] = []

            try:
                for runtime in self._runtimes:
                    attempted.append(runtime)
                    if not await runtime.start(timeout):
                        await self._rollback(attempted)
                        await self._set_state(
                            PipelineState.ERROR,
                            f"service '{runtime.name}' failed to start: {runtime.last_error}",
                        )
                        return False
            except asyncio.CancelledError:
                # Отмену не глотаем, но и запущенные сервисы не бросаем
                await asyncio.shield(self._rollback(attempted))
                await self._set_state(PipelineState.ERROR, "cancelled during start")
                raise

            await self._set_state(PipelineState.RUNNING)
            return True

    async def stop(self, timeout: Optional[float] = 10.0) -> bool:
        """
        Остановить сервисы в обратном порядке запуска.

        Сбой одного сервиса не мешает остановке остальных.

        Returns:
            True, если все сервисы остановлены
        """
        async with self._get_lock():
            if self._state in (PipelineState.UNINITIALIZED, PipelineState.STOPPED):
                return True

            await self._set_state(PipelineState.STOPPING)
            ok = await self._stop_all(self._runtimes, timeout)

            if ok:
                await self._set_state(PipelineState.STOPPED)
            else:
                await self._set_state(PipelineState.ERROR, "some services failed to stop")
            return ok

    async def check_health(self, timeout: Optional[float] = 5.0) -> Dict[str, bool]:
        """Проверить здоровье всех сервисов параллельно (ServiceRuntime.check_health не бросает)."""
        results = await asyncio.gather(
            *(rt.check_health(timeout) for rt in self._runtimes)
        )
        return {rt.name: healthy for rt, healthy in zip(self._runtimes, results)}

    # ==================== СОСТОЯНИЕ ====================

    def get_state(self) -> Dict[str, Any]:
        """Снимок состояния пайплайна и всех его сервисов."""
        return {
            "name": self._name,
            "state": self._state.value,
            "last_error": self._last_error,
            "services": {rt.name: rt.get_state() for rt in self._runtimes},
        }

    # ==================== ВНУТРЕННЕЕ ====================

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _stop_all(
        self, runtimes: Sequence[ServiceRuntime], timeout: Optional[float]
    ) -> bool:
        all_ok = True
        for runtime in reversed(runtimes):
            if not await runtime.stop(timeout):
                all_ok = False
        return all_ok

    async def _rollback(
        self, attempted: Sequence[ServiceRuntime], timeout: Optional[float] = 10.0
    ) -> None:
        # Таймаут обязателен: зависший shutdown не должен подвешивать откат
        self._logger.warning(
            "Rolling back pipeline %s: stopping %s",
            self._name, [rt.name for rt in reversed(attempted)],
        )
        await self._stop_all(attempted, timeout)

    async def _set_state(self, new: PipelineState, error: Optional[str] = None) -> None:
        old = self._state
        self._state = new
        self._last_error = error

        if new is PipelineState.ERROR:
            self._logger.error("%s: %s -> %s (%s)", self._name, old.value, new.value, error)
        else:
            self._logger.info("%s: %s -> %s", self._name, old.value, new.value)

        await self._events.publish(
            EventType.PIPELINE_STATE_CHANGED,
            {"pipeline": self._name, "from": old.value, "to": new.value, "error": error},
        )