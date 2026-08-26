"""
HTTP Server Configuration Module - FIXED
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class HttpSettings(BaseSettings):
    """HTTP server configuration settings"""
    enabled: bool = Field(
        default=True,
        description="Enable HTTP monitoring server"
    )
    host: str = Field(
        default="127.0.0.1",
        description="Host for HTTP server (Default - localhost)"
    )
    port: int = Field(
        default=8000,
        description="Port for HTTP server (Default - 8000)"
    )

    # ИСПРАВЛЕНИЕ: используем model_config вместо class Config
    model_config = ConfigDict(
        env_prefix="HTTP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )