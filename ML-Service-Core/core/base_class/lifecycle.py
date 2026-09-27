# core/base_class/lifecycle.py
"""
Протокол жизненного цикла для всех компонентов приложения.
Используется контейнером зависимостей и менеджерами ресурсов.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Lifecycle(Protocol):
    """
    Унифицированный интерфейс жизненного цикла.
    Любой класс, реализующий данные методы, автоматически
    распознается контейнером как управляемый ресурс.
    """

    @property
    def name(self) -> str:
        """Идентификатор компонента."""
        ...

    async def initialize(self) -> None:
        """Инициализация ресурсов (соединения, сессии, пулы)."""
        ...

    async def shutdown(self) -> None:
        """Безопасное освобождение ресурсов при завершении работы."""
        ...

    async def check_health(self) -> bool:
        """Выполнить активную проверку работоспособности (ping/healthcheck)."""
        ...

    @property
    def healthy(self) -> bool:
        """Получить текущий/кэшированный статус здоровья."""
        ...