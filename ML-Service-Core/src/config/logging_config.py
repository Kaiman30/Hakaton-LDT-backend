"""
Logging Configuration Module - FIXED
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class LoggingSettings(BaseSettings):
    """Logging configuration settings"""
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or text")
    log_enable_debug: bool = Field(default=False, description="Enable debug logging")
    log_file: Optional[str] = Field(default=None, description="Log file path")

    # ИСПРАВЛЕНИЕ: используем model_config вместо class Config
    model_config = ConfigDict(
        env_prefix="LOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )