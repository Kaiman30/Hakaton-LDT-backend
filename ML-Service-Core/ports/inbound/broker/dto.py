# ports/inbound/broker/dto.py
"""
Data Transfer Objects for message queue communication with Pydantic validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field, validator


class MessagePriority(str, Enum):
    """Priority levels for messages."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# ============ Pydantic Models for Validation ============

class QueueMessageModel(BaseModel):
    """Pydantic model for QueueMessage validation."""
    id: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(..., min_items=1)
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = Field(default_factory=datetime.now)
    headers: Dict[str, str] = Field(default_factory=dict)
    key: Optional[str] = None
    partition: Optional[int] = Field(None, ge=0)
    offset: Optional[int] = Field(None, ge=0)
    
    @validator('topic')
    def topic_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Topic cannot be empty')
        return v


class PublishRequestModel(BaseModel):
    """Pydantic model for PublishRequest validation."""
    topic: str = Field(..., min_length=1)
    message: Dict[str, Any] = Field(..., min_items=1)
    key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    priority: MessagePriority = MessagePriority.NORMAL
    partition: Optional[int] = Field(None, ge=0)
    timeout: Optional[float] = Field(None, gt=0)
    
    @validator('topic')
    def topic_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Topic cannot be empty')
        return v


class BatchPublishRequestModel(BaseModel):
    """Pydantic model for BatchPublishRequest validation."""
    topic: str = Field(..., min_length=1)
    messages: List[Dict[str, Any]] = Field(..., min_items=1)
    key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    priority: MessagePriority = MessagePriority.NORMAL
    partition: Optional[int] = Field(None, ge=0)
    timeout: Optional[float] = Field(None, gt=0)
    default_format: Optional[Dict[str, Any]] = None
    
    @validator('topic')
    def topic_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Topic cannot be empty')
        return v


class SubscribeRequestModel(BaseModel):
    """Pydantic model for SubscribeRequest validation."""
    topics: List[str] = Field(..., min_items=1)
    group_id: str = Field(..., min_length=1)
    auto_offset_reset: str = Field(default="latest", regex="^(earliest|latest|none)$")
    enable_auto_commit: bool = True
    session_timeout: Optional[float] = Field(None, gt=0)
    
    @validator('topics')
    def topics_not_empty(cls, v):
        if not v:
            raise ValueError('Topics list cannot be empty')
        for topic in v:
            if not topic or not topic.strip():
                raise ValueError('Topic cannot be empty')
        return v


class ConsumeRequestModel(BaseModel):
    """Pydantic model for ConsumeRequest validation."""
    topic: str = Field(..., min_length=1)
    group_id: str = Field(..., min_length=1)
    max_messages: int = Field(10, gt=0, le=1000)
    timeout: float = Field(5.0, gt=0)
    auto_commit: bool = True
    partition: Optional[int] = Field(None, ge=0)
    from_beginning: bool = False
    
    @validator('topic')
    def topic_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Topic cannot be empty')
        return v


class CommitRequestModel(BaseModel):
    """Pydantic model for CommitRequest validation."""
    message_ids: List[str] = Field(..., min_items=1)
    group_id: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    
    @validator('message_ids')
    def message_ids_not_empty(cls, v):
        if not v:
            raise ValueError('Message IDs list cannot be empty')
        return v


# ============ Dataclass Versions ============

@dataclass
class QueueMessage:
    """A message in a queue."""
    id: str
    topic: str
    payload: Dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    headers: Dict[str, str] = field(default_factory=dict)
    key: Optional[str] = None
    partition: Optional[int] = None
    offset: Optional[int] = None
    
    def __post_init__(self):
        if not self.id or not self.id.strip():
            raise ValueError('Message ID cannot be empty')
        if not self.topic or not self.topic.strip():
            raise ValueError('Topic cannot be empty')
        if not self.payload:
            raise ValueError('Payload cannot be empty')
        if self.partition is not None and self.partition < 0:
            raise ValueError('Partition must be non-negative')
        if self.offset is not None and self.offset < 0:
            raise ValueError('Offset must be non-negative')
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "topic": self.topic,
            "payload": self.payload,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "headers": self.headers,
            "key": self.key,
        }
        if self.partition is not None:
            result["partition"] = self.partition
        if self.offset is not None:
            result["offset"] = self.offset
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueMessage":
        return cls(
            id=data["id"],
            topic=data["topic"],
            payload=data["payload"],
            priority=MessagePriority(data.get("priority", "normal")),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            headers=data.get("headers", {}),
            key=data.get("key"),
            partition=data.get("partition"),
            offset=data.get("offset"),
        )
    
    def validate(self) -> QueueMessageModel:
        """Validate using Pydantic model."""
        return QueueMessageModel(
            id=self.id,
            topic=self.topic,
            payload=self.payload,
            priority=self.priority,
            timestamp=self.timestamp,
            headers=self.headers,
            key=self.key,
            partition=self.partition,
            offset=self.offset
        )


@dataclass
class PublishRequest:
    """Request to publish a message."""
    topic: str
    message: Dict[str, Any]
    key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    priority: MessagePriority = MessagePriority.NORMAL
    partition: Optional[int] = None
    timeout: Optional[float] = None
    
    def __post_init__(self):
        if not self.topic or not self.topic.strip():
            raise ValueError('Topic cannot be empty')
        if not self.message:
            raise ValueError('Message cannot be empty')
        if self.partition is not None and self.partition < 0:
            raise ValueError('Partition must be non-negative')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('Timeout must be positive')
    
    def validate(self) -> PublishRequestModel:
        """Validate using Pydantic model."""
        return PublishRequestModel(
            topic=self.topic,
            message=self.message,
            key=self.key,
            headers=self.headers,
            priority=self.priority,
            partition=self.partition,
            timeout=self.timeout
        )


@dataclass
class PublishResponse:
    """Response from publishing."""
    message_id: str
    topic: str
    partition: int
    offset: int
    timestamp: datetime


@dataclass
class BatchPublishRequest:
    """Request to publish multiple messages."""
    topic: str
    messages: List[Dict[str, Any]]
    key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    priority: MessagePriority = MessagePriority.NORMAL
    partition: Optional[int] = None
    timeout: Optional[float] = None
    default_format: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if not self.topic or not self.topic.strip():
            raise ValueError('Topic cannot be empty')
        if not self.messages:
            raise ValueError('Messages list cannot be empty')
        if self.partition is not None and self.partition < 0:
            raise ValueError('Partition must be non-negative')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('Timeout must be positive')
    
    def validate(self) -> BatchPublishRequestModel:
        """Validate using Pydantic model."""
        return BatchPublishRequestModel(
            topic=self.topic,
            messages=self.messages,
            key=self.key,
            headers=self.headers,
            priority=self.priority,
            partition=self.partition,
            timeout=self.timeout,
            default_format=self.default_format
        )


@dataclass
class BatchPublishResponse:
    """Response from batch publishing."""
    message_ids: List[str]
    topic: str
    partition: int
    count: int
    timestamp: datetime


@dataclass
class SubscribeRequest:
    """Request to subscribe to topics."""
    topics: List[str]
    group_id: str
    auto_offset_reset: str = "latest"  # earliest, latest, none
    enable_auto_commit: bool = True
    session_timeout: Optional[float] = None
    
    def __post_init__(self):
        if not self.topics:
            raise ValueError('Topics list cannot be empty')
        for topic in self.topics:
            if not topic or not topic.strip():
                raise ValueError('Topic cannot be empty')
        if not self.group_id or not self.group_id.strip():
            raise ValueError('Group ID cannot be empty')
        if self.auto_offset_reset not in ["earliest", "latest", "none"]:
            raise ValueError('auto_offset_reset must be one of: earliest, latest, none')
        if self.session_timeout is not None and self.session_timeout <= 0:
            raise ValueError('Session timeout must be positive')
    
    def validate(self) -> SubscribeRequestModel:
        """Validate using Pydantic model."""
        return SubscribeRequestModel(
            topics=self.topics,
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=self.enable_auto_commit,
            session_timeout=self.session_timeout
        )


@dataclass
class ConsumeRequest:
    """Request to consume messages."""
    topic: str
    group_id: str
    max_messages: int = 10
    timeout: float = 5.0
    auto_commit: bool = True
    partition: Optional[int] = None
    from_beginning: bool = False
    
    def __post_init__(self):
        if not self.topic or not self.topic.strip():
            raise ValueError('Topic cannot be empty')
        if not self.group_id or not self.group_id.strip():
            raise ValueError('Group ID cannot be empty')
        if self.max_messages <= 0:
            raise ValueError('max_messages must be positive')
        if self.timeout <= 0:
            raise ValueError('Timeout must be positive')
        if self.partition is not None and self.partition < 0:
            raise ValueError('Partition must be non-negative')
    
    def validate(self) -> ConsumeRequestModel:
        """Validate using Pydantic model."""
        return ConsumeRequestModel(
            topic=self.topic,
            group_id=self.group_id,
            max_messages=self.max_messages,
            timeout=self.timeout,
            auto_commit=self.auto_commit,
            partition=self.partition,
            from_beginning=self.from_beginning
        )


@dataclass
class ConsumeResponse:
    """Response from consuming."""
    messages: List[QueueMessage]
    has_more: bool
    total_consumed: int


@dataclass
class CommitRequest:
    """Request to commit consumed messages."""
    message_ids: List[str]
    group_id: str
    topic: str
    
    def __post_init__(self):
        if not self.message_ids:
            raise ValueError('Message IDs list cannot be empty')
        if not self.group_id or not self.group_id.strip():
            raise ValueError('Group ID cannot be empty')
        if not self.topic or not self.topic.strip():
            raise ValueError('Topic cannot be empty')
    
    def validate(self) -> CommitRequestModel:
        """Validate using Pydantic model."""
        return CommitRequestModel(
            message_ids=self.message_ids,
            group_id=self.group_id,
            topic=self.topic
        )


@dataclass
class CommitResponse:
    """Response from committing."""
    committed: List[str]
    failed: List[str]
    success: bool