"""
PostgreSQL Configuration Module - FIXED
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class PostgreSettings(BaseSettings):
    """PostgreSQL configuration settings"""
    host: str = Field(
        default="localhost",
        description="Database host"
    )
    port: int = Field(
        default=5432,
        description="Database port"
    )
    database: str = Field(
        default="worker_db",
        description="Database name"
    )
    user: str = Field(
        default="postgres",
        description="Database user"
    )
    password: str = Field(
        default="postgres",
        description="Database password"
    )
    pool_min_size: int = Field(
        default=1,
        description="Pool min size"
    )
    pool_max_size: int = Field(
        default=20,
        description="Pool max size"
    )
    enabled: bool = Field(
        default=True,
        description="Enable PostgreSQL"
    )

    @property
    def dsn(self) -> str:
        """PostgreSQL connection string"""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}"
        )

    # ИСПРАВЛЕНИЕ: используем model_config вместо class Config
    model_config = ConfigDict(
        env_prefix="POSTGRES_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )