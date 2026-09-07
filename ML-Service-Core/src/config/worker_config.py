"""
Worker Configuration Module - FIXED
"""

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class WorkerSettings(BaseSettings):
    """Worker configuration settings"""
    max_concurrent_tasks: int = Field(
        default=10,
        description="Max concurrent tasks"
    )
    executor_max_workers: int = Field(
        default=20,
        description="Max executor workers"
    )

    # Circuit breaker
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description="Failure threshold"
    )
    circuit_breaker_timeout_sec: float = Field(
        default=30.0,
        description="Timeout in seconds"
    )

    # Retry settings
    max_retries: int = Field(
        default=3,
        description="Max retries"
    )
    retry_initial_delay: float = Field(
        default=2.0,
        description="Initial delay"
    )
    retry_max_delay: float = Field(
        default=10.0,
        description="Max delay"
    )
    python_gil_enabled: bool = Field(
        default=False,
        description="Enable GIL"
    )

    # ИСПРАВЛЕНИЕ: используем model_config вместо class Config
    model_config = ConfigDict(
        env_prefix="WORKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )