class EventBusError(Exception):
    """Базовое исключение Infrastructure Event Bus."""


class EventHandlerAlreadyRegistered(EventBusError):
    """Обработчик уже зарегистрирован для события."""


class EventHandlerNotRegistered(EventBusError):
    """Попытка удалить отсутствующий обработчик."""