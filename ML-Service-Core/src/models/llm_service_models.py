"""
LLM Service Data Models - Models for the LLM service business logic.

These models represent the data structures used in the LLM service
for task processing, results, and internal operations.
"""

from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from pydantic import BaseModel


# Pydantic models for validation
class TaskDataModel(BaseModel):
    """Model for task data extracted from Kafka message"""
    task_id: str
    storage_path: Optional[str] = None
    trace_id: str
    prompt_id: int
    original_message: Dict[str, Any]  # Original Kafka message


class TaskProcessingResult(BaseModel):
    """Model for task processing result"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None


class KafkaReceivedMessageForService(BaseModel):
    """Model for received Kafka message with metadata in LLM service"""
    kafka_key: Optional[str] = None
    payload: Dict[str, Any]
    kafka_headers: Optional[Dict[str, str]] = None
    kafka_topic: Optional[str] = None
    kafka_partition: Optional[int] = None
    kafka_offset: Optional[int] = None
    kafka_timestamp: Optional[int] = None
    kafka_timestamp_type: Optional[int] = None


# Dataclass models for internal use
@dataclass
class ProcessedTaskData:
    """Internal representation of processed task data"""
    task_id: str
    storage_path: Optional[str]
    trace_id: str
    prompt_id: int
    original_message: Dict[str, Any]


@dataclass
class ProcessingResult:
    """Internal representation of processing result"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None


@dataclass
class LLMResponseParsed:
    """Parsed response from LLM"""
    success: bool
    content: Dict[str, Any]
    tokens_used: Optional[int] = None
    tokens_total: Optional[int] = None
    model: Optional[str] = None
    processing_time_ms: Optional[float] = None