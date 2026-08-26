"""
Kafka Configuration Module - FIXED
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class KafkaSettings(BaseSettings):
    """Kafka configuration settings"""
    bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers"
    )
    group_id: str = Field(
        default="llm-worker-group",
        description="Consumer group ID"
    )
    auto_offset_reset: str = Field(
        default="earliest",
        description="Auto offset reset policy"
    )
    consumer_poll_timeout: float = Field(
        default=1.0,
        description="Consumer poll timeout"
    )

    # ИСПРАВЛЕНИЕ: используем model_config вместо class Config
    model_config = ConfigDict(
        env_prefix="KAFKA_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )