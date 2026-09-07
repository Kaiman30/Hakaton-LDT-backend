# infrastructure/internal/logging.py
import asyncio
import logging
import inspect
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, List
import asyncpg
import queue
import threading
import time
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[2;36m',
        'INFO': '\033[0;32m',
        'WARNING': '\033[0;33m',
        'ERROR': '\033[0;31m',
        'CRITICAL': '\033[1;31m'
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        location = f"{record.filename}:{record.lineno} in {record.funcName}"
        record.location = location
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


class AsyncPGHandler(logging.Handler):
    """Asynchronous PostgreSQL logging handler with graceful shutdown."""

    def __init__(self, dsn: str, table: str = 'logs', max_queue_size: int = 1000):
        super().__init__()
        self.dsn = dsn
        self.table = table
        self.max_queue_size = max_queue_size
        self.log_queue = queue.Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()
        self._running = True
        
        # Start background thread
        self.worker_thread = threading.Thread(target=self._process_logs, daemon=True)
        self.worker_thread.start()
        
        # Initialize connection pool
        self.pool = None
        asyncio.run(self._initialize_pool())

    async def _initialize_pool(self):
        """Initialize the connection pool asynchronously."""
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=1,
            max_size=5,
            command_timeout=60
        )
        await self._create_table_if_not_exists()

    async def _create_table_if_not_exists(self):
        """Create logs table if it doesn't exist."""
        if not self.pool:
            return
            
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
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

    def emit(self, record):
        """Add log record to queue for async processing."""
        try:
            formatted_msg = self.format(record)
            
            log_entry = {
                'created_at': datetime.utcnow(),
                'level': record.levelname,
                'logger_name': record.name,
                'file_name': record.filename,
                'line_number': record.lineno,
                'function_name': record.funcName,
                'message': formatted_msg
            }
            
            try:
                self.log_queue.put_nowait(log_entry)
            except queue.Full:
                try:
                    self.log_queue.get_nowait()
                    self.log_queue.put_nowait(log_entry)
                except queue.Empty:
                    pass
        except Exception:
            self.handleError(record)

    def _process_logs(self):
        """Background thread function to process logs from queue."""
        while self._running and not self._stop_event.is_set():
            try:
                batch = []
                batch_start_time = time.time()
                
                # Collect logs for batching
                while len(batch) < 100 and (time.time() - batch_start_time) < 1.0:
                    try:
                        log_entry = self.log_queue.get(timeout=0.1)
                        batch.append(log_entry)
                    except queue.Empty:
                        # Check if we should stop
                        if self._stop_event.is_set():
                            break
                        continue
                
                if batch:
                    # Check if we should stop before processing batch
                    if self._stop_event.is_set():
                        # Process remaining logs one more time
                        self._flush_remaining()
                        break
                    
                    asyncio.run(self._insert_batch_async(batch))
                    
            except Exception as e:
                print(f"Error in AsyncPGHandler worker: {e}")
                if not self._stop_event.is_set():
                    time.sleep(0.1)  # Prevent busy loop on error

    def _flush_remaining(self):
        """Flush remaining logs in queue."""
        remaining = []
        while not self.log_queue.empty():
            try:
                remaining.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        
        if remaining:
            try:
                asyncio.run(self._insert_batch_async(remaining))
            except Exception as e:
                print(f"Error flushing remaining logs: {e}")

    async def _insert_batch_async(self, batch: List[dict]):
        """Insert a batch of log records into the database."""
        if not self.pool:
            return
            
        try:
            async with self.pool.acquire() as conn:
                query = f"""
                INSERT INTO {self.table}
                (created_at, level, logger_name, file_name, line_number, function_name, message)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """
                
                values = [
                    (
                        entry['created_at'],
                        entry['level'],
                        entry['logger_name'],
                        entry['file_name'],
                        entry['line_number'],
                        entry['function_name'],
                        entry['message']
                    )
                    for entry in batch
                ]
                
                await conn.executemany(query, values)
                
        except Exception as e:
            print(f"Error inserting logs to database: {e}")
            # Re-queue failed logs
            for entry in batch:
                try:
                    self.log_queue.put_nowait(entry)
                except queue.Full:
                    pass

    async def close_async(self):
        """Gracefully close the handler."""
        self._stop_event.set()
        self._running = False
        
        # Wait for worker thread to finish
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5.0)
        
        # Close connection pool
        if self.pool:
            await self.pool.close()
            await self.pool.wait_closed()
        
        super().close()

    def close(self):
        """Close the handler (synchronous wrapper)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.close_async())
            else:
                loop.run_until_complete(self.close_async())
        except RuntimeError:
            # No event loop running, create one
            asyncio.run(self.close_async())


def setup_logger(
        version: str,
        name: str = 'GUI',
        log_file: str = None,
        level: int = logging.INFO,
        pg_dsn: str = None
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

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

    if pg_dsn:
        pg_handler = AsyncPGHandler(pg_dsn)
        pg_handler.setFormatter(file_formatter)
        logger.addHandler(pg_handler)

    return logger


def get_logger(
    version: str = "1.0.0",
    name: str = "gigachatAPI",
    log_file: Optional[str] = None,
    level: Optional[int] = None,
    pg_dsn: Optional[str] = None,
    enable_debug: bool = False,
) -> logging.Logger:
    """Get configured logger instance."""
    if log_file is None:
        log_file = "logs/system.log"

    if level is None:
        level = logging.DEBUG if enable_debug else logging.INFO

    return setup_logger(version, name, log_file, level=level, pg_dsn=pg_dsn)


def get_logger_from_config(config) -> logging.Logger:
    """Get logger configured from Config object."""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    level = level_map.get(config.log_level, logging.INFO)
    if config.log_enable_debug:
        level = logging.DEBUG

    return get_logger(
        version="1.0.0",
        name="gigachatAPI",
        log_file=config.log_file,
        level=level,
        pg_dsn=getattr(config, 'log_pg_dsn', None),
        enable_debug=config.log_enable_debug,
    )