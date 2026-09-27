# ports/outbound/ml/llm/dto.py
"""
Data Transfer Objects for LLM communication with Pydantic v2 validation.
Supports multimodal content, function calling, and structured streaming.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, BinaryIO, Dict, List, Optional, Union, AsyncIterator
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MessageRole(str, Enum):
    """Role of a message in the conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class CompletionMode(str, Enum):
    """Mode for text completion."""
    GENERATE = "generate"
    STREAM = "stream"
    EMBED = "embed"


# ============ Pydantic Models for Validation ============

class MessageModel(BaseModel):
    """Pydantic model for Message validation (supports text & multimodal content)."""
    role: MessageRole
    content: Optional[Union[str, List[Union[str, Dict[str, Any]]]]] = None
    name: Optional[str] = Field(None, min_length=1)
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

    @model_validator(mode='after')
    def validate_content_or_tool_calls(self) -> 'MessageModel':
        if not self.content and not self.tool_calls:
            raise ValueError('Message must contain either content or tool_calls')
        return self


class ChatRequestModel(BaseModel):
    """Pydantic model for ChatRequest validation."""
    messages: List[MessageModel] = Field(..., min_length=1)
    model: Optional[str] = Field(None, min_length=1)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0, le=100000)
    top_p: float = Field(1.0, ge=0.0, le=1.0)
    frequency_penalty: float = Field(0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(0.0, ge=-2.0, le=2.0)
    stop: Optional[Union[str, List[str]]] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    @model_validator(mode='after')
    def validate_tool_choice(self) -> 'ChatRequestModel':
        if self.tool_choice and not self.tools:
            raise ValueError('tool_choice requires tools to be provided')
        return self


class UsageModel(BaseModel):
    """Pydantic model for Usage validation."""
    prompt_tokens: int = Field(0, ge=0)
    completion_tokens: int = Field(0, ge=0)
    total_tokens: int = Field(0, ge=0)


class ChatChoiceModel(BaseModel):
    """Pydantic model for ChatChoice validation."""
    index: int = Field(0, ge=0)
    message: MessageModel
    finish_reason: Optional[str] = None


class ChatResponseModel(BaseModel):
    """Pydantic model for ChatResponse validation."""
    id: str = Field(..., min_length=1)
    choices: List[ChatChoiceModel] = Field(..., min_length=1)
    usage: UsageModel
    created: datetime
    model: str = Field(..., min_length=1)
    system_fingerprint: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ChatStreamChunkModel(BaseModel):
    """Pydantic model for structured streaming chunks."""
    id: str
    delta_content: Optional[str] = None
    delta_tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    usage: Optional[UsageModel] = None


class EmbeddingRequestModel(BaseModel):
    """Pydantic model for EmbeddingRequest validation."""
    input: Union[str, List[str]]
    model: Optional[str] = Field(None, min_length=1)
    dimensions: Optional[int] = Field(None, gt=0, le=10000)

    @field_validator('input')
    @classmethod
    def input_not_empty(cls, v: Union[str, List[str]]) -> Union[str, List[str]]:
        if isinstance(v, str) and not v.strip():
            raise ValueError('Input text cannot be empty')
        if isinstance(v, list) and not v:
            raise ValueError('Input list cannot be empty')
        return v


class EmbeddingModel(BaseModel):
    """Pydantic model for Embedding validation."""
    index: int = Field(0, ge=0)
    embedding: List[float] = Field(..., min_length=1)
    text: Optional[str] = None


class EmbeddingResponseModel(BaseModel):
    """Pydantic model for EmbeddingResponse validation."""
    data: List[EmbeddingModel] = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    usage: UsageModel


class TokenCountResponseModel(BaseModel):
    """Pydantic model for TokenCountResponse validation."""
    text: str = Field(..., min_length=1)
    tokens: int = Field(0, ge=0)
    characters: int = Field(0, ge=0)
    model: str = Field(..., min_length=1)


class FileUploadRequestModel(BaseModel):
    """Pydantic model for FileUploadRequest validation."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    file_data: Union[bytes, BinaryIO, AsyncIterator[bytes]]
    filename: str = Field(..., min_length=1)
    mime_type: Optional[str] = None
    timeout: Optional[float] = Field(None, gt=0)


class FileUploadResponseModel(BaseModel):
    """Pydantic model for FileUploadResponse validation."""
    file_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
    mime_type: Optional[str] = None
    size: int = Field(..., ge=0)
    created_at: datetime
    expires_at: Optional[datetime] = None


class FileInfoResponseModel(BaseModel):
    """Pydantic model for FileInfoResponse validation."""
    file_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
    mime_type: Optional[str] = None
    size: int = Field(..., ge=0)
    created_at: datetime
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FilesListResponseModel(BaseModel):
    """Pydantic model for FilesListResponse validation."""
    files: List[Dict[str, Any]]
    total: int = Field(..., ge=0)


class DeleteFilesResponseModel(BaseModel):
    """Pydantic model for DeleteFilesResponse validation."""
    deleted: List[str]
    failed: List[str]
    success: bool


# ============ Dataclass Versions ============

@dataclass
class Message:
    """A single message in a conversation (supports multimodal content)."""
    role: MessageRole
    content: Optional[Union[str, List[Union[str, Dict[str, Any]]]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.content and not self.tool_calls:
            raise ValueError('Message content and tool_calls cannot both be empty')

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"role": self.role.value}
        if self.content is not None:
            result["content"] = self.content
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=MessageRole(data["role"]),
            content=data.get("content"),
            name=data.get("name"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )

    def validate(self) -> MessageModel:
        return MessageModel(
            role=self.role,
            content=self.content,
            name=self.name,
            tool_calls=self.tool_calls,
            tool_call_id=self.tool_call_id,
        )


@dataclass
class ChatRequest:
    """Request for chat completion."""
    messages: List[Message]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[Union[str, List[str]]] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError('Messages list cannot be empty')
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError('Temperature must be between 0 and 2')
        if not (0.0 <= self.top_p <= 1.0):
            raise ValueError('Top_p must be between 0 and 1')
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError('max_tokens must be positive')

    def validate(self) -> ChatRequestModel:
        return ChatRequestModel(
            messages=[msg.validate() for msg in self.messages],
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            stop=self.stop,
            stream=self.stream,
            tools=self.tools,
            tool_choice=self.tool_choice,
            metadata=self.metadata,
        )


@dataclass
class ChatStreamChunk:
    """A single chunk from streaming completion."""
    id: str
    delta_content: Optional[str] = None
    delta_tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    usage: Optional["Usage"] = None


@dataclass
class Usage:
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.completion_tokens < 0 or self.total_tokens < 0:
            raise ValueError('Token counts cannot be negative')

    def validate(self) -> UsageModel:
        return UsageModel(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
        )


@dataclass
class ChatChoice:
    """A single completion choice."""
    index: int
    message: Message
    finish_reason: Optional[str] = None

    def validate(self) -> ChatChoiceModel:
        return ChatChoiceModel(
            index=self.index,
            message=self.message.validate(),
            finish_reason=self.finish_reason,
        )


@dataclass
class ChatResponse:
    """Response from chat completion."""
    id: str
    choices: List[ChatChoice]
    usage: Usage
    created: datetime
    model: str
    system_fingerprint: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @property
    def first_choice(self) -> ChatChoice:
        return self.choices[0]

    @property
    def content(self) -> Optional[Union[str, List[Union[str, Dict[str, Any]]]]]:
        return self.first_choice.message.content if self.choices else ""

    def validate(self) -> ChatResponseModel:
        return ChatResponseModel(
            id=self.id,
            choices=[c.validate() for c in self.choices],
            usage=self.usage.validate(),
            created=self.created,
            model=self.model,
            system_fingerprint=self.system_fingerprint,
            metadata=self.metadata,
        )


@dataclass
class EmbeddingRequest:
    """Request for embeddings."""
    input: Union[str, List[str]]
    model: Optional[str] = None
    dimensions: Optional[int] = None

    def validate(self) -> EmbeddingRequestModel:
        return EmbeddingRequestModel(
            input=self.input,
            model=self.model,
            dimensions=self.dimensions,
        )


@dataclass
class Embedding:
    """A single embedding vector."""
    index: int
    vector: List[float]
    text: Optional[str] = None

    def validate(self) -> EmbeddingModel:
        return EmbeddingModel(
            index=self.index,
            embedding=self.vector,
            text=self.text,
        )


@dataclass
class EmbeddingResponse:
    """Response from embeddings."""
    embeddings: List[Embedding]
    model: str
    usage: Usage

    def validate(self) -> EmbeddingResponseModel:
        return EmbeddingResponseModel(
            data=[e.validate() for e in self.embeddings],
            model=self.model,
            usage=self.usage.validate(),
        )


@dataclass
class TokenCountResponse:
    """Response from token counting."""
    text: str
    tokens: int
    characters: int
    model: str

    def validate(self) -> TokenCountResponseModel:
        return TokenCountResponseModel(
            text=self.text,
            tokens=self.tokens,
            characters=self.characters,
            model=self.model,
        )


@dataclass
class FileUploadResponse:
    """Response from file upload."""
    file_id: str
    filename: str
    mime_type: Optional[str] = None
    size: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

    def validate(self) -> FileUploadResponseModel:
        return FileUploadResponseModel(
            file_id=self.file_id,
            filename=self.filename,
            mime_type=self.mime_type,
            size=self.size,
            created_at=self.created_at,
            expires_at=self.expires_at,
        )


@dataclass
class FileInfoResponse:
    """Response from file info."""
    file_id: str
    filename: str
    mime_type: Optional[str] = None
    size: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> FileInfoResponseModel:
        return FileInfoResponseModel(
            file_id=self.file_id,
            filename=self.filename,
            mime_type=self.mime_type,
            size=self.size,
            created_at=self.created_at,
            expires_at=self.expires_at,
            metadata=self.metadata,
        )


@dataclass
class FilesListResponse:
    """Response from listing files."""
    files: List[Dict[str, Any]]
    total: int

    def validate(self) -> FilesListResponseModel:
        return FilesListResponseModel(
            files=self.files,
            total=self.total,
        )


@dataclass
class DeleteFilesResponse:
    """Response from deleting files."""
    deleted: List[str]
    failed: List[str]
    success: bool

    def validate(self) -> DeleteFilesResponseModel:
        return DeleteFilesResponseModel(
            deleted=self.deleted,
            failed=self.failed,
            success=self.success,
        )