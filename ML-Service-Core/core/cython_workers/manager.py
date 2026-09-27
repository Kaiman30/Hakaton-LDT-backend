# cython_workers/manager.py
import logging
from typing import Callable, Optional, Dict, Any
from cython_workers.func_spec.base_specs import IDataParserSpec

logger = logging.getLogger(__name__)

# Резервная реализация на чистом Python (на случай если С-модуль не собрался)
def _python_fallback_parser(raw_bytes: bytes) -> dict:
    # Медленная, но гарантированно работающая логика
    return {"status": 0, "parsed": True, "engine": "python_fallback"}


class CythonWorkerManager:
    """
    Единый менеджер для загрузки, управления и предоставления
    высокопроизводительных C/Cython воркеров.
    """

    def __init__(self) -> None:
        self._has_c_extensions: bool = False
        self._parse_func: Callable[[bytes], dict] = _python_fallback_parser
        self._load_modules()

    def _load_modules(self) -> None:
        """Динамическая загрузка скомпилированных C/Cython расширений."""
        try:
            # Пытаемся импортировать скомпилированный .pyx/.so модуль
            from cython_workers.Cython.parser import c_fast_parse
            self._parse_func = c_fast_parse
            self._has_c_extensions = True
            logger.info("⚡ Cython C-расширения успешно загружены.")
        except ImportError as e:
            logger.warning(
                f"⚠️ Не удалось загрузить Cython модуль ({e}). "
                "Используется Python fallback."
            )
            self._has_c_extensions = False

    @property
    def is_c_accelerated(self) -> bool:
        """Проверка, активны ли C-ускорители."""
        return self._has_c_extensions

    def get_parser(self) -> Callable[[bytes], dict]:
        """Возвращает типизированную функцию парсинга (Cython или Python fallback)."""
        return self._parse_func


# Singleton-экземпляр менеджера
cython_manager = CythonWorkerManager()