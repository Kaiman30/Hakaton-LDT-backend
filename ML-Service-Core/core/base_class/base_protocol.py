from typing import Dict, Type, Protocol, runtime_checkable


class BaseProtocol(Protocol):
    """Базовый маркер для всех протоколов в системе"""
    __slots__ = ()
