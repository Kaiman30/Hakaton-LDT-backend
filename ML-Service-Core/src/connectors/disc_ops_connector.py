import asyncio
import pickle
import os
import io
import logging
from typing import Any, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, BrokenExecutor
from threading import Lock
from pathlib import Path

from core.base_class.base_connectors import QueueConnector


class DiskQueueConnector(QueueConnector):
    """
    Асинхронный коннектор для сохранения и восстановления очереди в файл.
    Поддерживает буферизацию, потокобезопасность, retry и асинхронное выполнение в пуле потоков.
    Оптимизирован для No-GIL Python и Cython-совместимости.
    """

    def __init__(
        self,
        file_path: str,
        *,
        flush_threshold: int = 100,
        flush_interval: float = 5.0,
        max_buffer_size: int = 10000,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        logger: Optional[logging.Logger] = None,
        executor: Optional[ThreadPoolExecutor] = None,
        **_: Any,
    ) -> None:
        super().__init__(name="disk_queue")
        self.file_path = Path(file_path)
        self.flush_threshold = flush_threshold
        self.flush_interval = flush_interval
        self.max_buffer_size = max_buffer_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logger or logging.getLogger(__name__)
        self.executor = executor or ThreadPoolExecutor(max_workers=2)

        # Асинхронная защита доступа к буферу
        self._lock = asyncio.Lock()
        # Потокобезопасная защита доступа к файлу
        self._file_lock = Lock()

        # Внутренний буфер
        self._buffer: List[Any] = []
        self._change_count = 0
        self._timer_handle: Optional[asyncio.TimerHandle] = None

    async def initialize(self) -> None:
        if not self.file_path.parent.exists():
            raise ValueError(f"Directory for file does not exist: {self.file_path.parent}")

        last_error = None
        current_retry_delay = self.retry_delay

        for attempt in range(self.max_retries + 1):
            try:
                self.logger.debug(
                    f"Initialize attempt {attempt + 1}/{self.max_retries + 1}: {self.file_path}"
                )

                if self.file_path.exists():
                    buffer = await asyncio.get_running_loop().run_in_executor(
                        self.executor, self._blocking_load_from_disk
                    )
                    async with self._lock:
                        self._buffer = buffer
                    self.logger.info(f"Loaded {len(self._buffer)} items from {self.file_path}")
                else:
                    self.logger.info(f"File does not exist, starting with empty queue: {self.file_path}")

                return

            except (OSError, IOError, pickle.PickleError) as e:
                last_error = e
                if attempt < self.max_retries:
                    self.logger.warning(
                        f"Initialize attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {current_retry_delay:.1f}s..."
                    )
                    await asyncio.sleep(current_retry_delay)
                    current_retry_delay *= 1.5
                else:
                    self.logger.error(f"Initialize failed after {self.max_retries + 1} attempts: {self.file_path}")
            except asyncio.CancelledError:
                self.logger.warning(f"Initialize cancelled: {self.file_path}")
                raise
            except Exception as e:
                self.logger.error(f"Unexpected error in initialize: {e}", exc_info=True)
                last_error = e

        raise RuntimeError(
            f"Failed to initialize {self.file_path} after {self.max_retries + 1} attempts: {last_error}"
        ) from last_error

    async def shutdown(self) -> None:
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        await self._flush_now()
        self.executor.shutdown(wait=True)

    async def add_item(self, item: Any) -> None:
        if item is None:
            raise ValueError("Item cannot be None")

        async with self._lock:
            if len(self._buffer) >= self.max_buffer_size:
                raise RuntimeError(f"Buffer size limit exceeded: {self.max_buffer_size}")

            self._buffer.append(item)
            self._change_count += 1

            if self._timer_handle is None:
                self._timer_handle = asyncio.get_running_loop().call_later(
                    self.flush_interval, lambda: asyncio.create_task(self._flush_if_needed())
                )

            if self._change_count >= self.flush_threshold:
                await self._flush_now()

    async def remove_item(self, item: Any) -> bool:
        async with self._lock:
            if item in self._buffer:
                self._buffer.remove(item)
                self._change_count += 1
                if self._change_count >= self.flush_threshold:
                    await self._flush_now()
                return True
            return False

    async def get_all_items(self) -> List[Any]:
        async with self._lock:
            return self._buffer.copy()

    async def clear(self) -> None:
        async with self._lock:
            self._buffer.clear()
            self._change_count += 1
        await self._flush_now()

    # ============ Private Methods ============

    async def _flush_if_needed(self) -> None:
        async with self._lock:
            if self._timer_handle and not self._timer_handle.cancelled():
                if self._change_count >= self.flush_threshold:
                    await self._flush_now()

    async def _flush_now(self) -> None:
        async with self._lock:
            if not self._buffer:
                return

            if self.executor._shutdown:
                self.logger.warning("Executor is shut down, skipping flush.")
                return

            self.logger.debug(f"Flushing {len(self._buffer)} items to {self.file_path}")

            try:
                await asyncio.get_running_loop().run_in_executor(
                    self.executor, self._blocking_save_to_disk, self._buffer.copy()
                )
                self._change_count = 0  # Обнуляем только при успехе
            except BrokenExecutor:
                self.logger.error("Executor is broken, cannot flush.")
            finally:
                if self._timer_handle:
                    self._timer_handle.cancel()
                    self._timer_handle = None

    def _blocking_save_to_disk(self, buffer: List[Any]) -> None:
        temp_path = self.file_path.with_suffix(self.file_path.suffix + ".tmp")

        with self._file_lock:
            try:
                with temp_path.open("wb") as f:
                    pickle.dump(buffer, f)
                temp_path.replace(self.file_path)
                self.logger.debug(f"Successfully saved {len(buffer)} items to {self.file_path}")
            except Exception as e:
                self.logger.error(f"Error saving to disk: {e}", exc_info=True)
                if temp_path.exists():
                    temp_path.unlink()
                raise

    def _blocking_load_from_disk(self) -> List[Any]:
        with self._file_lock:
            try:
                with self.file_path.open("rb") as f:
                    data = pickle.load(f)
                if not isinstance(data, list):
                    raise ValueError(f"Data in {self.file_path} is not a list")
                return data
            except Exception as e:
                self.logger.error(f"Error loading from disk: {e}", exc_info=True)
                raise