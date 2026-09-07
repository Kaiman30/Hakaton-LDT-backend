
import asyncio
import logging
import queue
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import asyncpg


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветами для консоли. НЕ мутирует record — безопасен для множества handler'ов."""

    COLORS = {
        'DEBUG': '\\033[2;36m',
        'INFO': '\\033[0;32m',
        'WARNING': '\\033[0;33m',
        'ERROR': '\\033[0;31m',
        'CRITICAL': '\\033[1;31m'
    }
    RESET = '\\033[0m'

    def format(self, record):
        # Добавляем location (не мутируем стандартные поля)
        record.location = f"{record.filename}:{record.lineno} in {record.funcName}"

        # Сохраняем оригинал
        orig_levelname = record.levelname

        # Цвет ТОЛЬКО для строки вывода — record не трогаем
        colored = f"{self.COLORS.get(orig_levelname, self.RESET)}{orig_levelname}{self.RESET}"

        # Форматируем вручную, чтобы не мутировать record.levelname
        msg = self._fmt % {
            'version': getattr(record, 'version', 'unknown'),
            'location': record.location,
            'asctime': self.formatTime(record),
            'name': record.name,
            'levelname': colored,
            'message': record.getMessage(),
        }

        if record.exc_info:
            msg += self.formatException(record.exc_info)

        return msg


class AsyncPGHandler(logging.Handler):
    """
    Async PostgreSQL log handler для FT Python.

    Архитектура:
    - emit() — быстрый, неблокирующий, кладёт в threading.Queue
    - Фоновый поток с ОДНИМ event loop на всю жизнь handler'а
    - Lazy init pool (через внешний вызов или при первой вставке)
    - Batch insert с retry
    """

    def __init__(
        self,
        dsn: str,
        table: str = 'logs',
        max_queue_size: int = 10000,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        put_timeout: float = 0.01,
    ):
        super().__init__()
        self.dsn = dsn
        self.table = table
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.put_timeout = put_timeout

        # Threading queue — emit() вызывается из sync контекста logging
        self._log_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._running = True
        self._pool: Optional[asyncpg.Pool] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready_event = threading.Event()

        # Запускаем фоновый поток с event loop
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="AsyncPGHandler")
        self._thread.start()

        # Ждём готовности loop (не pool — он lazy)
        self._ready_event.wait(timeout=5.0)

    def _run_loop(self):
        """Фоновый поток: один event loop на всю жизнь handler'а."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready_event.set()

        # Запускаем воркер вставки
        self._loop.run_until_complete(self._flush_worker())

        # Graceful shutdown
        if self._pool:
            self._loop.run_until_complete(self._pool.close())

    async def _init_pool(self):
        """Инициализация pool в фоновом потоке (lazy)."""
        try:
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=1,
                max_size=3,  # Логгер не должен жрать коннекции
                command_timeout=30,
            )
            await self._create_table()
        except Exception as e:
            # Логгер не должен падать — пишем в stderr
            import sys
            print(f"[AsyncPGHandler] Failed to init pool: {e}", file=sys.stderr)

    async def _create_table(self):
        async with self._pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    level VARCHAR(10) NOT NULL,
                    logger_name VARCHAR(255) NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    line_number INTEGER NOT NULL,
                    function_name VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    trace_id VARCHAR(64)
                );
                CREATE INDEX IF NOT EXISTS idx_logs_created_at ON {self.table}(created_at);
                CREATE INDEX IF NOT EXISTS idx_logs_level ON {self.table}(level);
            """)

    def emit(self, record: logging.LogRecord):
        """
        Быстрый, неблокирующий. Блокирует максимум put_timeout (10ms).
        При переполнении — дроп (лучше потерять лог, чем затормозить ML-пайплайн).
        """
        try:
            entry = {
                'created_at': datetime.utcnow(),
                'level': record.levelname,  # Оригинал, без цветов
                'logger_name': record.name,
                'file_name': record.filename,
                'line_number': record.lineno,
                'function_name': record.funcName,
                'message': record.getMessage(),
                'trace_id': getattr(record, 'trace_id', None),
            }

            try:
                # Блокирующий put с таймаутом — не теряем логи при кратковременном всплеске
                self._log_queue.put(entry, timeout=self.put_timeout)
            except queue.Full:
                # Дроп самого старого — ring buffer behavior
                try:
                    self._log_queue.get_nowait()
                    self._log_queue.put_nowait(entry)
                except queue.Empty:
                    pass

        except Exception:
            self.handleError(record)

    async def _flush_worker(self):
        """Основной цикл: батчит и вставляет."""
        while self._running or not self._log_queue.empty():
            batch = []
            deadline = time.time() + self.flush_interval

            while len(batch) < self.batch_size and time.time() < deadline:
                try:
                    entry = self._log_queue.get(timeout=0.05)
                    batch.append(entry)
                except queue.Empty:
                    break

            if batch:
                # Lazy init pool при первой вставке
                if self._pool is None:
                    await self._init_pool()
                if self._pool:
                    await self._insert_batch(batch)

            if not self._running and self._log_queue.empty():
                break

    async def _insert_batch(self, batch: list):
        """Вставка батча. Retry при ошибке — один раз."""
        if not self._pool:
            return

        query = f"""
            INSERT INTO {self.table}
            (created_at, level, logger_name, file_name, line_number, function_name, message, trace_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """

        values = [
            (
                e['created_at'], e['level'], e['logger_name'],
                e['file_name'], e['line_number'], e['function_name'],
                e['message'], e['trace_id'],
            )
            for e in batch
        ]

        try:
            async with self._pool.acquire() as conn:
                await conn.executemany(query, values)
        except Exception as e:
            import sys
            print(f"[AsyncPGHandler] Insert failed: {e}", file=sys.stderr)
            # Не падаем — логи потеряны, но система работает

    def close(self):
        """Graceful shutdown: дожидаемся drain очереди."""
        self._running = False
        self._thread.join(timeout=5.0)
        super().close()


def setup_logger(
    version: str,
    name: str = 'app',
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    pg_dsn: Optional[str] = None,
) -> logging.Logger:
    """Создаёт НОВЫЙ сконфигурированный логгер (сбрасывает старые handlers)."""
    logger = logging.getLogger(name)

    # Сбрасываем старые handlers для переинициализации
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    logger.setLevel(level)

    fmt = '%(version)s - %(location)s - %(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Console — с цветами
    console = logging.StreamHandler()
    console.setFormatter(ColoredFormatter(fmt))
    logger.addHandler(console)

    # File — без цветов
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(file_handler)

    # PostgreSQL — async, в фоновом потоке
    if pg_dsn:
        pg_handler = AsyncPGHandler(pg_dsn)
        pg_handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(pg_handler)

    return logger


def get_logger(
    version: str = "1.0.0",
    name: str = "app",
    log_file: Optional[str] = None,
    level: Optional[int] = None,
    pg_dsn: Optional[str] = None,
    enable_debug: bool = False,
) -> logging.Logger:
    """
    Получает логгер. Если уже есть handlers — возвращает как есть (idempotent).
    Если нужна переинициализация — используй setup_logger().
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    if level is None:
        level = logging.DEBUG if enable_debug else logging.INFO

    return setup_logger(version, name, log_file, level, pg_dsn)


def get_logger_from_config(config) -> logging.Logger:
    """Фабрика из конфига."""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level = level_map.get(config.log_level, logging.INFO)
    if getattr(config, 'log_enable_debug', False):
        level = logging.DEBUG

    return get_logger(
        version=getattr(config, 'version', '1.0.0'),
        name=getattr(config, 'app_name', 'app'),
        log_file=config.log_file,
        level=level,
        pg_dsn=getattr(config, 'log_pg_dsn', None),
    )
