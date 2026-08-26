"""
MinIO Configuration Module - FIXED
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class MinIOSettings(BaseSettings):
    """MinIO configuration settings"""
    endpoint: str = Field(
        default="localhost:9000",
        description="MinIO endpoint"
    )
    access_key: str = Field(
        default="minioadmin",
        description="MinIO access key"
    )
    secret_key: str = Field(
        default="minioadmin",
        description="MinIO secret key"
    )
    bucket_name: str = Field(
        default="documents",
        description="Bucket name"
    )
    use_ssl: bool = Field(
        default=False,
        description="Use SSL"
    )
    enabled: bool = Field(
        default=True,
        description="Enable MinIO"
    )

    # ИСПРАВЛЕНИЕ: используем model_config вместо class Config
    model_config = ConfigDict(
        env_prefix="MINIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )