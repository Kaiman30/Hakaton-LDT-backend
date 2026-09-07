"""
MinIO Connector - Thread-safe for no-GIL Python
Unified download method with configurable parameters
"""
import asyncio
import io
from typing import Optional, Any, AsyncIterable
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from minio import Minio
from minio.error import S3Error

from core.base_class.base_connectors import FileStorageConnector
from core.registry import register_connector, dependence_connector


@register_connector("Minio")
@dependence_connector("Storage")
class MinIOConnector(FileStorageConnector):
    """
    MinIO connector with no-GIL compatibility
    - Thread-safe client usage
    - Unified download method with optional timeout/streaming
    - No multiple executor contexts (safe for free-threaded Python)
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        get_logger,
        executor: ThreadPoolExecutor,
        use_ssl: bool = False,
    ):
        super().__init__(name="minio")
        self.logger = get_logger()
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.use_ssl = use_ssl
        self.client: Optional[Minio] = None
        self.executor = executor

        # Thread safety lock for MinIO client (required for no-GIL)
        self._client_lock = Lock()
        self._health_status = False

    @classmethod
    def from_config(cls, config: Any, executor: Optional[ThreadPoolExecutor] = None, **kwargs) -> "MinIOConnector":
        """
        Create MinIOConnector from config.

        Args:
            config: Settings object with config.minio
            executor: Optional ThreadPoolExecutor for blocking operations
            **kwargs: Additional arguments (ignored for compatibility)

        Returns:
            Configured MinIOConnector instance
        """
        from utils.logging import get_logger_from_config

        if executor is None:
            executor = ThreadPoolExecutor(max_workers=10)

        return cls(
            endpoint=config.minio.endpoint,
            access_key=config.minio.access_key,
            secret_key=config.minio.secret_key,
            bucket=config.minio.bucket_name,
            get_logger=lambda: get_logger_from_config(config),
            executor=executor,
            use_ssl=config.minio.use_ssl,
        )

    async def initialize(self) -> None:
        """Initialize MinIO client (thread-safe)"""
        try:
            with self._client_lock:
                self.client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.use_ssl,
                )

                # Create bucket if not exists
                if not self.client.bucket_exists(self.bucket):
                    self.client.make_bucket(self.bucket)
                    self.logger.info(f"Created MinIO bucket: {self.bucket}")

            self._set_health(True)
            self.logger.info(f"MinIO initialized: {self.endpoint}")
        except Exception as e:
            self.logger.error(f"Failed to initialize MinIO: {e}")
            self._set_health(False)
            raise

    async def shutdown(self) -> None:
        """Shutdown MinIO client"""
        if self.client:
            with self._client_lock:
                try:
                    self.client = None
                    self.logger.info("MinIO client closed")
                except Exception as e:
                    self.logger.error(f"Error closing MinIO client: {e}")

    async def download(
        self,
        object_name: str,
        *,
        timeout: Optional[float] = 30.0,
        use_streaming: bool = False,
        chunk_size: int = 65536 * 4,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        **_: Any,
    ) -> Any:
        """
        Unified download method with optional parameters

        Args:
            object_name: Name of the object to download
            timeout: Download timeout in seconds (None = no timeout)
            use_streaming: If True, yields chunks; if False, returns full bytes
            chunk_size: Size of chunks for streaming (default 64KB)
            max_retries: Number of retry attempts on failure (default 0 = no retry)
            retry_delay: Delay between retries in seconds (exponential backoff applied)

        Returns:
            If use_streaming=False: bytes of the file
            If use_streaming=True: AsyncGenerator yielding chunks

        Raises:
            ValueError: If parameters are invalid
            TimeoutError: If download exceeds timeout
            S3Error: If MinIO operation fails
            RuntimeError: If all retries exhausted
        """
        # ============ Input Validation ============
        if not object_name or not isinstance(object_name, str):
            raise ValueError("object_name must be a non-empty string")

        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive or None")

        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        if retry_delay < 0:
            raise ValueError("retry_delay must be non-negative")

        # Normalize path
        object_name = object_name.lstrip("/")

        if not self.client:
            raise RuntimeError("MinIO client not initialized")

        # ============ Retry Loop ============
        last_error = None
        current_retry_delay = retry_delay

        for attempt in range(max_retries + 1):
            try:
                self.logger.debug(
                    f"Download attempt {attempt + 1}/{max_retries + 1}: {object_name} "
                    f"(timeout={timeout}s, streaming={use_streaming})"
                )

                # Use streaming or full download
                if use_streaming:
                    return self._download_stream(
                        object_name=object_name,
                        chunk_size=chunk_size,
                        timeout=timeout,
                    )
                else:
                    return await self._download_binary(
                        object_name=object_name,
                        timeout=timeout,
                    )

            except (S3Error, RuntimeError, OSError, TimeoutError) as e:
                last_error = e

                if attempt < max_retries:
                    self.logger.warning(
                        f"Download attempt {attempt + 1} failed for {object_name}: {e}. "
                        f"Retrying in {current_retry_delay:.1f}s..."
                    )
                    await asyncio.sleep(current_retry_delay)
                    current_retry_delay *= 1.5  # Exponential backoff
                else:
                    self.logger.error(
                        f"Download failed after {max_retries + 1} attempts: {object_name}"
                    )

            except asyncio.CancelledError:
                self.logger.warning(f"Download cancelled: {object_name}")
                raise

            except Exception as e:
                self.logger.error(f"Unexpected error in download: {e}", exc_info=True)
                last_error = e

        # All retries exhausted
        raise RuntimeError(
            f"Failed to download {object_name} after {max_retries + 1} attempts: {last_error}"
        ) from last_error

    async def _download_binary(
        self,
        object_name: str,
        timeout: Optional[float],
    ) -> bytes:
        """
        Download entire file as bytes (private method)
        Thread-safe: uses executor + lock for MinIO client access
        """
        try:
            loop = asyncio.get_running_loop()

            # Run blocking operation in executor
            from functools import partial
            download_func = partial(
                self._blocking_download_binary,
                object_name=object_name
            )

            if timeout:
                # Download with timeout
                try:
                    self.logger.debug(f"Starting binary download with {timeout}s timeout: {object_name}")
                    data = await asyncio.wait_for(
                        loop.run_in_executor(self.executor, download_func),
                        timeout=timeout
                    )
                    self.logger.info(f"Successfully downloaded: {object_name} ({len(data)} bytes)")
                    return data
                except asyncio.TimeoutError:
                    self.logger.error(f"Download timeout ({timeout}s): {object_name}")
                    raise TimeoutError(
                        f"Download exceeded {timeout} seconds: {object_name}"
                    )
            else:
                # Download without timeout
                self.logger.debug(f"Starting binary download (no timeout): {object_name}")
                data = await loop.run_in_executor(self.executor, download_func)
                self.logger.info(f"Successfully downloaded: {object_name} ({len(data)} bytes)")
                return data

        except TimeoutError:
            raise
        except Exception as e:
            self.logger.error(f"Error in binary download: {e}", exc_info=True)
            raise

    def _blocking_download_binary(self, object_name: str) -> bytes:
        """
        Blocking binary download (runs in executor thread)
        Thread-safe: protected by lock when accessing MinIO client
        """
        buffer = io.BytesIO()

        try:
            # Acquire lock for MinIO client access (no-GIL safe)
            with self._client_lock:
                response = self.client.get_object(self.bucket, object_name)

            chunk_size = 8192
            bytes_read = 0

            try:
                while True:
                    try:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        buffer.write(chunk)
                        bytes_read += len(chunk)
                    except Exception as e:
                        self.logger.error(f"Error reading chunk from {object_name}: {e}")
                        raise

                data = buffer.getvalue()
                self.logger.debug(f"Read {bytes_read} bytes from {object_name}")
                return data
            finally:
                response.close()

        except S3Error as e:
            self.logger.error(f"S3 error for {object_name}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error in blocking download: {e}", exc_info=True)
            raise
        finally:
            buffer.close()

    async def _download_stream(
        self,
        object_name: str,
        chunk_size: int,
        timeout: Optional[float],
    ) -> AsyncIterable:
        """
        Stream download in chunks (returns async generator)
        Thread-safe: lock protects MinIO client access
        """
        try:
            loop = asyncio.get_running_loop()

            self.logger.debug(f"Starting streaming download: {object_name}")

            # Get response in executor (thread-safe via lock)
            from functools import partial
            get_response_func = partial(
                self._blocking_get_response,
                object_name=object_name
            )

            if timeout:
                try:
                    response = await asyncio.wait_for(
                        loop.run_in_executor(self.executor, get_response_func),
                        timeout=timeout / 2  # Half timeout for initial connection
                    )
                except asyncio.TimeoutError:
                    self.logger.error(f"Connection timeout: {object_name}")
                    raise TimeoutError(f"Failed to connect within {timeout}s")
            else:
                response = await loop.run_in_executor(self.executor, get_response_func)

            bytes_read = 0
            try:
                while True:
                    # Read chunk in executor
                    read_func = partial(response.read, chunk_size)

                    if timeout:
                        try:
                            chunk = await asyncio.wait_for(
                                loop.run_in_executor(self.executor, read_func),
                                timeout=timeout / (bytes_read // chunk_size + 1)  # Per-chunk timeout
                            )
                        except asyncio.TimeoutError:
                            self.logger.error(f"Chunk read timeout: {object_name} at {bytes_read} bytes")
                            raise TimeoutError(f"Chunk read timeout at {bytes_read} bytes")
                    else:
                        chunk = await loop.run_in_executor(self.executor, read_func)

                    if not chunk:
                        break

                    bytes_read += len(chunk)
                    yield chunk

                self.logger.info(f"Streaming download completed: {object_name} ({bytes_read} bytes)")

            finally:
                response.close()

        except S3Error as e:
            self.logger.error(f"MinIO error streaming {object_name}: {e}")
            raise
        except TimeoutError:
            raise
        except asyncio.CancelledError:
            self.logger.warning(f"Streaming download cancelled: {object_name}")
            raise
        except Exception as e:
            self.logger.error(f"Error in streaming download: {e}", exc_info=True)
            raise RuntimeError(f"Failed to stream file: {str(e)}") from e

    def _blocking_get_response(self, object_name: str):
        """
        Get MinIO response object (runs in executor)
        Thread-safe: protected by lock
        """
        try:
            with self._client_lock:
                return self.client.get_object(self.bucket, object_name)
        except S3Error as e:
            self.logger.error(f"Error getting object {object_name}: {e}")
            raise

    async def health_check(self) -> bool:
        """Check MinIO connectivity (thread-safe)"""
        try:
            with self._client_lock:
                if self.client:
                    self.client.bucket_exists(self.bucket)
                    self._set_health(True)
                    return True
        except Exception as e:
            self.logger.warning(f"MinIO health check failed: {e}")
            self._set_health(False)
        return False

    async def upload(self, object_name: str, data: bytes, *, timeout: float = 30.0, **kwargs) -> None:
        """Upload bytes to MinIO bucket"""
        try:
            await asyncio.wait_for(
                self._upload_binary(object_name, data),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"Upload timeout for {object_name}")

    async def _upload_binary(self, object_name: str, data: bytes) -> None:
        """Blocking upload in thread pool"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._blocking_upload_binary,
            object_name,
            data
        )

    def _blocking_upload_binary(self, object_name: str, data: bytes) -> None:
        """Synchronous upload implementation"""
        self.client.put_object(self.bucket, object_name, io.BytesIO(data), len(data))
