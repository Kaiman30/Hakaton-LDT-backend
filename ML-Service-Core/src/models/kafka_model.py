"""
DEPRECATED: Old Kafka models - форматы сообщений
This file is deprecated. Use models.kafka_models instead.

key = task_id
headers = JSON(trace_id, status, worker_id)
value = JSON(данные задачи/результата)
"""
import warnings
from typing import Optional, Tuple
from pydantic import BaseModel, Field
from enum import Enum


def deprecated_kafka_model(func):
    """Decorator to mark functions as deprecated"""
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{func.__name__} is deprecated. Use models.kafka_models instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return func(*args, **kwargs)
    return wrapper


class TaskStatus(str, Enum):
    """Статусы задач"""
    PENDING = "1"
    PROCESSING = "2"
    SUCCESS = "3"
    FAILED = "4"


class KafkaKey(BaseModel):
    """Key for kafka (Task_id)"""
    task_id: str = Field(..., description="Id задачи из api gateway")


class KafkaHeaders(BaseModel):
    """Заголовки Kafka сообщений (JSON)"""
    trace_id: str = Field(..., description="Trace ID для мониторинга")
    status: TaskStatus = Field(..., description="Статус задачи 1-4")
    worker_id: str = Field(default="LLM_service_1", description="ID воркера")


class KafkaValueConsumer(BaseModel):
    """Values, readable from kafka"""
    storage_path: str = Field(..., description="Storage Path")
    storage_size: int = Field(default=None, description="Storage Size")
    metadata: str = Field(default=None, description="Metadata")


class KafkaValueProducer(BaseModel):
    """LLM worker result"""
    result: str = Field(..., description="Result")
    error_message: str = Field(..., description="Error Message")


class KafkaMessage(BaseModel):
    """Полный формат Kafka сообщения."""
    key: KafkaKey
    headers: KafkaHeaders
    payload: Optional[KafkaValueProducer] = None

    # Метод для отправки (альтернатива вашему статическому методу)
    @classmethod
    @deprecated_kafka_model
    def build_model(
        cls,
        *,
        task_id: str,
        trace_id: str,
        status: str,
        worker_id: str = "LLM_service_1",
        result: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> "KafkaMessage":
        """Удобный конструктор для создания сообщения."""
        key_obj = KafkaKey(task_id=task_id)
        headers_obj = KafkaHeaders(
            trace_id=trace_id,
            status=TaskStatus(status),
            worker_id=worker_id,
        )
        payload_obj = None
        if result is not None or error_message is not None:
            payload_obj = KafkaValueProducer(
                result=result,
                error_message=error_message,
            )
        return cls(key=key_obj, headers=headers_obj, payload=payload_obj)

    # Метод для получения
    @classmethod
    @deprecated_kafka_model
    def parse(cls, json_str: str) -> "KafkaMessage":
        """Парсит JSON-строку в валидированную структуру."""
        return cls.model_validate_json(json_str)


    @classmethod
    @deprecated_kafka_model
    def read_model(
        cls,
        *,
        key: str,
        headers: Tuple[str, str, str],  # (trace_id, status, worker_id)
        payload: Optional[Tuple[str, Optional[int], Optional[str]]] = None,  # (storage_path, storage_size, metadata)
    ) -> "KafkaMessage":
        """
        Создаёт KafkaMessage из "сырых" компонентов, полученных от Kafka-консьюмера.
        Используется для парсинга входящих сообщений (consumer-side).
        """
        trace_id, status_str, worker_id = headers

        # Создаём ключ
        key_obj = KafkaKey(task_id=key)

        # Создаём заголовки
        headers_obj = KafkaHeaders(
            trace_id=trace_id,
            status=TaskStatus(status_str),  # Валидация через Enum
            worker_id=worker_id
        )

        # Создаём payload для consumer
        payload_obj = None
        if payload is not None:
            storage_path, storage_size, metadata = payload
            payload_obj = KafkaValueConsumer(
                storage_path=storage_path,
                storage_size=storage_size,
                metadata=metadata
            )

        return cls(key=key_obj, headers=headers_obj, payload=payload_obj)


# Import the new models for backward compatibility
# This allows gradual migration from old to new models
# NOTE: Avoiding import to prevent circular dependency with domain_models.py
# New code should directly import from models.kafka_models instead
