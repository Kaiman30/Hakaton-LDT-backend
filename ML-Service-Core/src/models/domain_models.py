"""
Domain Data Models - Centralized imports for domain-specific data models.

This module provides convenient access to all domain-specific data models.
"""

# Export domain-specific models
# Using deprecated kafka_model for backward compatibility
from .kafka_model import TaskStatus, KafkaMessage, KafkaKey, KafkaHeaders, KafkaValueConsumer, KafkaValueProducer
from .kafka_models import (
    KafkaMessageKey,
    KafkaMessageHeaders,
    KafkaMessageValue,
    KafkaPublishRequest,
    KafkaBatchPublishRequest,
    KafkaSubscribeRequest,
    KafkaReceivedMessage as KafkaReceivedMessageNew,
    KafkaCommitRequest,
    KafkaHealthCheckResponse
)
from .llm_service_models import (
    TaskDataModel,
    TaskProcessingResult,
    KafkaReceivedMessageForService as KafkaReceivedMessageOld,
    ProcessedTaskData,
    ProcessingResult,
    LLMResponseParsed
)
from .http_model import HealthResponse, StatusResponse
from .prompt_model import Prompt, PromptService, check_barcode_is_PR, DO3
from .db_model import DBLogEvent, DBLogEntry
from .minio_model import MinIORequest, MinIOResponse

__all__ = [
    # Kafka models (legacy)
    'TaskStatus',
    'KafkaMessage',
    'KafkaKey',
    'KafkaHeaders',
    'KafkaValueConsumer',
    'KafkaValueProducer',

    # Kafka models (new)
    'KafkaMessageKey',
    'KafkaMessageHeaders',
    'KafkaMessageValue',
    'KafkaPublishRequest',
    'KafkaBatchPublishRequest',
    'KafkaSubscribeRequest',
    'KafkaReceivedMessageNew',
    'KafkaCommitRequest',
    'KafkaHealthCheckResponse',

    # LLM Service models
    'TaskDataModel',
    'TaskProcessingResult',
    'KafkaReceivedMessageOld',
    'ProcessedTaskData',
    'ProcessingResult',
    'LLMResponseParsed',

    # HTTP models
    'HealthResponse',
    'StatusResponse',

    # Prompt models
    'Prompt',
    'PromptService',
    'check_barcode_is_PR',
    'DO3',

    # Database models
    'DBLogEvent',
    'DBLogEntry',

    # MinIO models
    'MinIORequest',
    'MinIOResponse',
]