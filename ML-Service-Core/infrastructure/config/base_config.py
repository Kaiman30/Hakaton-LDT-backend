"""
Base configuration module using Pydantic BaseSettings for environment and file parsing.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    """
    Базовый класс конфигурации для инфраструктурных компонентов.
    Автоматически подтягивает переменные из окружения и .env файлов.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # Игнорировать лишние параметры в окружении
        case_sensitive=False,    # Регистронезависимость для переменных окружения
    )