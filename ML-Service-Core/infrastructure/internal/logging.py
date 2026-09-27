# infrastructure/internal/logging.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, List
import asyncpg

from core.base_class.lifecycle import Lifecycle


class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[2;36m',
        'INFO': '\033[0;32m',
        'WARNING': '\033[0;33m',
        'ERROR': '\033[0;31m',
        'CRITICAL': '\033[1;31m'
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.location = f"{record.filename}:{record.lineno} in {record.funcName}"
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


class AsyncPGHandler(logging.Handler, Lifecycle):
    """
    Асинхронный PostgreSQL хэндлер логирования.
    Реализует протокол Lifecycle для интеграции с DI-контейнером.
    """

    def __init__(self, dsn: str, table: str = 'logs', max_queue_size: int = 1000):
        super().__init__()
        self._dsn = dsn
        self._table = table
        self._max_queue_size = max_queue_size
        
        self._pool: Optional[asyncpg.Pool] = None
        self._queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._healthy: bool = False
        self._name: str = "asyncpg_logger"

    @property
    def name(self) -> str:
        return self._name

    @property
    def healthy(self) -> bool:
        return self._healthy

    async def initialize(self) -> None:
        """Инициализация пула соединений и запуск фоновой задачи очереди."""
        if self._pool is not None:
            return

        self._queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=1,
            max_size=5,
            command_timeout=60
        )
        await self._create_table_if_not_exists()
        self._worker_task = asyncio.create_task(self._process_logs())
        self._healthy = True

    async def shutdown(self) -> None:
        """Graceful shutdown: сброс остатков очереди и закрытие пула."""
        self._healthy = False

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        # Сбрасываем оставшиеся записи из очереди
        await self._flush_remaining()

        if self._pool:
            await self._pool.close()
            self._pool = None

    async def check_health(self) -> bool:
        if not self._pool or not self._healthy:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            self._healthy = False
            return False

    async def _create_table_if_not_exists(self) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                level VARCHAR(10) NOT NULL,
                logger_name VARCHAR(255) NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                line_number INTEGER NOT NULL,
                function_name VARCHAR(255) NOT NULL,
                message TEXT NOT NULL
            );
            """)

    def emit(self, record: logging.LogRecord) -> None:
        """Поместить запись в неблокирующую асинхронную очередь."""
        if not self._healthy or self._queue is None:
            return

        try:
            log_entry = {
                'created_at': datetime.now(timezone.utc),
                'level': record.levelname,
                'logger_name': record.name,
                'file_name': record.filename,
                'line_number': record.lineno,
                'function_name': record.funcName,
                'message': self.format(record)
            }
            
            try:
                self._queue.put_nowait(log_entry)
            except asyncio.QueueFull:
                # В случае переполнения выбиваем самый старый лог
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(log_entry)
                except asyncio.QueueEmpty:
                    pass
        except Exception:
            self.handleError(record)

    async def _process_logs(self) -> None:
        """Фоновый воркер пачечной вставки логов."""
        while True:
            batch: List[dict] = []
            try:
                # Ждем первый элемент
                entry = await self._queue.get()
                batch.append(entry)
                self._queue.task_done()

                # Собираем остальные доступные элементы до лимита 100 шт
                while len(batch) < 100 and not self._queue.empty():
                    entry = self._queue.get_nowait()
                    batch.append(entry)
                    self._queue.task_done()

                if batch:
                    await self._insert_batch(batch)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # В случае ошибки логгера печатаем в stderr, чтобы не уйти в бесконечную рекурсию
                print(f"Error in AsyncPGHandler worker: {e}")
                await asyncio.sleep(0.5)

    async def _insert_batch(self, batch: List[dict]) -> None:
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                query = f"""
                INSERT INTO {self._table}
                (created_at, level, logger_name, file_name, line_number, function_name, message)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """
                values = [
                    (
                        e['created_at'], e['level'], e['logger_name'],
                        e['file_name'], e['line_number'], e['function_name'], e['message']
                    )
                    for e in batch
                ]
                await conn.executemany(query, values)
        except Exception as e:
            print(f"Error inserting logs to Postgres: {e}")

    async def _flush_remaining(self) -> None:
        if not self._queue or self._queue.empty():
            return
        remaining: List[dict] = []
        while not self._queue.empty():
            remaining.append(self._queue.get_nowait())
            self._queue.task_done()
        if remaining:
            await self._insert_batch(remaining)


def setup_logger(
    version: str,
    name: str = 'GUI',
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    pg_dsn: Optional[str] = None
) -> tuple[logging.Logger, Optional[AsyncPGHandler]]:
    """
    Создает логгер. Возвращает (logger, pg_handler).
    pg_handler регистрируется в DI-контейнере как Lifecycle компонент.
    """
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger, None

    file_formatter = logging.Formatter(
        f'{version} - %(location)s - %(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_formatter = ColoredFormatter(
        f'{version} - %(location)s - %(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    pg_handler: Optional[AsyncPGHandler] = None
    if pg_dsn:
        pg_handler = AsyncPGHandler(pg_dsn)
        pg_handler.setFormatter(file_formatter)
        logger.addHandler(pg_handler)

    return logger, pg_handler