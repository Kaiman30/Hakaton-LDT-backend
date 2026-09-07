import asyncpg
from asyncpg import Pool
import asyncio
import io
from typing import Optional, AsyncGenerator, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from functools import partial
import logging

from core.base_class.base_connector import DBConnector


@register_connector("Postgres")
@dependence_connector("DB")
class PGConnector(DBConnector):
    """PostgreSQL async connector with connection pooling and concurrent operations"""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        min_pool_size: int = 1,
        max_pool_size: int = 20,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize PostgreSQL connector

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_pool_size: Minimum connections in pool
            max_pool_size: Maximum connections in pool
            logger: Logger instance
        """
        super().__init__(name="postgres")
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.logger = logger

        self._pool: Optional[Pool] = None
        self._executor = ThreadPoolExecutor(max_workers=max_pool_size)
        self._lock = Lock()

    @classmethod
    def from_config(cls, config: Any, **kwargs) -> "PGConnector":
        """
        Create PGConnector from config.

        Args:
            config: Settings object with config.postgres
            **kwargs: Additional arguments (ignored for compatibility)

        Returns:
            Configured PGConnector instance
        """
        return cls(
            host=config.postgres.host,
            port=config.postgres.port,
            database=config.postgres.database,
            user=config.postgres.user,
            password=config.postgres.password,
            min_pool_size=config.postgres.pool_min_size,
            max_pool_size=config.postgres.pool_max_size,
            logger=logging.getLogger(__name__),
        )

    async def initialize(self) -> None:
        """Initialize connection pool"""
        try:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                ssl=False,
            )
            self.logger.info(
                f"PostgreSQL pool initialized: {self.min_pool_size}-{self.max_pool_size} connections"
            )
            self._set_health(True)
        except Exception as e:
            self.logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            self._set_health(False)
            raise

    async def shutdown(self) -> None:
        """Close connection pool"""
        if self._pool:
            try:
                await self._pool.close()
                self.logger.info("PostgreSQL pool closed")
            except Exception as e:
                self.logger.error(f"Error closing pool: {e}")

    async def load(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return results as list of dicts

        Args:
            query: SQL SELECT query
            *args: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(query, *args)
                self.logger.debug(f"Loaded {len(rows)} rows from query")
                return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"Error loading data: {e}")
            raise

    async def load_one(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """
        Execute SELECT query and return single result

        Args:
            query: SQL SELECT query
            *args: Query parameters

        Returns:
            Single result row as dictionary or None
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(query, *args)
                return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"Error loading single row: {e}")
            raise

    async def load_scalar(self, query: str, *args) -> Any:
        """
        Execute SELECT query and return single scalar value

        Args:
            query: SQL SELECT query
            *args: Query parameters

        Returns:
            Single scalar value
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self._pool.acquire() as connection:
                value = await connection.fetchval(query, *args)
                return value
        except Exception as e:
            self.logger.error(f"Error loading scalar: {e}")
            raise

    async def load_stream(
            self,
            query: str,
            *args,
            chunk_size: int = 1000,
    ) -> AsyncGenerator[List[Dict[str, Any]], None]:
        """
        Stream large result sets in chunks

        Args:
            query: SQL SELECT query
            *args: Query parameters
            chunk_size: Number of rows per chunk

        Yields:
            Chunks of result rows as dictionaries
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self._pool.acquire() as connection:
                # asyncpg cursor doesn't use 'size' parameter, fetch chunks manually
                offset = 0
                while True:
                    # Fetch chunk using LIMIT/OFFSET
                    limited_query = f"{query} LIMIT $1 OFFSET $2"
                    records = await connection.fetch(limited_query, chunk_size, offset, *args)

                    if not records:
                        break

                    yield [dict(row) for row in records]
                    self.logger.debug(f"Streamed chunk of {len(records)} rows")

                    offset += chunk_size

                    if len(records) < chunk_size:
                        break

        except Exception as e:
            self.logger.error(f"Error streaming data: {e}")
            raise

    async def execute(self, query: str, *args, **kwargs) -> str:
        """Execute INSERT/UPDATE/DELETE query (поддержка %s параметров)"""
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self._pool.acquire() as connection:
                # asyncpg использует $1, $2... а не %s
                # Преобразуем %s -> $1, $2... для совместимости
                if '%' in query and args:
                    import re
                    param_count = len(args)
                    query = re.sub(r'%s', lambda m: f'${m.start() // 2 + 1}', query)

                result = await connection.execute(query, *args)
                self.logger.info(f"Executed query: {result}")
                return result
        except Exception as e:
            self.logger.error(f"Error executing query: {e}")
            raise

    async def execute_many(
        self,
        query: str,
        args_list: List[tuple],
    ) -> str:
        """
        Execute INSERT/UPDATE/DELETE query multiple times with different parameters

        Args:
            query: SQL DML query with parameters
            args_list: List of parameter tuples

        Returns:
            Command result
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self._pool.acquire() as connection:
                result = await connection.executemany(query, args_list)
                self.logger.info(f"Executed batch query: {result}")
                return result
        except Exception as e:
            self.logger.error(f"Error executing batch query: {e}")
            raise

    async def load_concurrent(
        self,
        queries: List[tuple],  # [(query, *args), ...]
    ) -> List[List[Dict[str, Any]]]:
        """
        Execute multiple SELECT queries concurrently

        Args:
            queries: List of (query, *args) tuples

        Returns:
            List of result lists (one per query)
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            tasks = [
                self.load(query, *args) if len(args) > 0 else self.load(query)
                for query, *args in queries
            ]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            self.logger.info(f"Executed {len(queries)} concurrent queries")
            return results
        except Exception as e:
            self.logger.error(f"Error executing concurrent queries: {e}")
            raise

    def _load_blocking(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Blocking load function (for use in thread pool)

        Args:
            query: SQL SELECT query
            *args: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        # Run async code in new event loop (for thread pool)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.load(query, *args))
            return result
        finally:
            loop.close()

    async def load_with_thread_pool(
        self,
        queries: List[tuple],
    ) -> List[List[Dict[str, Any]]]:
        """
        Load data using thread pool executor (useful for CPU-bound operations after fetch)

        Args:
            queries: List of (query, *args) tuples

        Returns:
            List of result lists
        """
        loop = asyncio.get_running_loop()
        tasks = []

        for query, *args in queries:
            # Submit to thread pool
            task = loop.run_in_executor(
                self._executor,
                partial(self._load_blocking, query, *args),
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=False)
        self.logger.info(f"Loaded {len(queries)} queries via thread pool")
        return results

    async def bulk_insert(
        self,
        table: str,
        columns: List[str],
        rows: List[tuple],
        batch_size: int = 1000,
    ) -> int:
        """
        Bulk insert rows with batching

        Args:
            table: Table name
            columns: Column names
            rows: List of row tuples
            batch_size: Number of rows per batch

        Returns:
            Total number of inserted rows
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            total_inserted = 0
            columns_str = ", ".join(columns)
            placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
            query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

            # Process in batches
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                await self.execute_many(query, batch)
                total_inserted += len(batch)
                self.logger.info(f"Inserted batch: {total_inserted}/{len(rows)} rows")

            self.logger.info(f"Bulk insert completed: {total_inserted} total rows")
            return total_inserted

        except Exception as e:
            self.logger.error(f"Error in bulk insert: {e}")
            raise

    async def load_to_buffer(
        self,
        query: str,
        *args,
        format: str = "csv",
    ) -> io.BytesIO:
        """
        Load query results to in-memory buffer (CSV or JSON format)

        Args:
            query: SQL SELECT query
            *args: Query parameters
            format: Output format ('csv' or 'json')

        Returns:
            BytesIO buffer with formatted data
        """
        import csv
        import json

        try:
            rows = await self.load(query, *args)

            if not rows:
                return io.BytesIO()

            buffer = io.BytesIO()

            if format == "csv":
                text_buffer = io.StringIO()
                writer = csv.DictWriter(text_buffer, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
                buffer.write(text_buffer.getvalue().encode("utf-8"))

            elif format == "json":
                json_str = json.dumps(rows, indent=2, default=str)
                buffer.write(json_str.encode("utf-8"))

            buffer.seek(0)
            self.logger.info(f"Loaded {len(rows)} rows to {format} buffer")
            return buffer

        except Exception as e:
            self.logger.error(f"Error loading to buffer: {e}")
            raise

    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        if not self._pool:
            return {}

        return {
            "size": self._pool.get_size(),
            "free_size": self._pool.get_idle_size(),
            "min_size": self._pool._minsize,
            "max_size": self._pool._maxsize,
        }

    async def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            async with self._pool.acquire() as connection:
                await connection.fetchval("SELECT 1")
            self.logger.debug("Health check passed")
            return True
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False