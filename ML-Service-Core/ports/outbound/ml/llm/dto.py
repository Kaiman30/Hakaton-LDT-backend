# ports/outbound/ml/llm/dto.py
"""
Data Transfer Objects for LLM communication with Pydantic validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


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
    """Pydantic model for Message validation."""
    role: MessageRole
    content: str = Field(..., min_length=1)
    name: Optional[str] = Field(None, min_length=1)
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
    @field_validator('content')
    def content_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Message content cannot be empty')
        return v


class ChatRequestModel(BaseModel):
    """Pydantic model for ChatRequest validation."""
    messages: List[MessageModel] = Field(..., min_items=1)
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
    
    @model_validator
    def validate_tool_choice(cls, values):
        """Validate tool_choice consistency."""
        tools = values.get('tools')
        tool_choice = values.get('tool_choice')
        
        if tool_choice and not tools:
            raise ValueError('tool_choice requires tools to be provided')
        
        return values


class EmbeddingRequestModel(BaseModel):
    """Pydantic model for EmbeddingRequest validation."""
    input: Union[str, List[str]]
    model: Optional[str] = Field(None, min_length=1)
    dimensions: Optional[int] = Field(None, gt=0, le=10000)
    
    @field_validator('input')
    def input_not_empty(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError('Input text cannot be empty')
        if isinstance(v, list) and not v:
            raise ValueError('Input list cannot be empty')
        return v


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
    choices: List[ChatChoiceModel] = Field(..., min_items=1)
    usage: UsageModel
    created: datetime
    model: str = Field(..., min_length=1)
    system_fingerprint: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class EmbeddingModel(BaseModel):
    """Pydantic model for Embedding validation."""
    index: int = Field(0, ge=0)
    embedding: List[float] = Field(..., min_items=1)
    text: Optional[str] = None


class EmbeddingResponseModel(BaseModel):
    """Pydantic model for EmbeddingResponse validation."""
    data: List[EmbeddingModel] = Field(..., min_items=1)
    model: str = Field(..., min_length=1)
    usage: UsageModel


class TokenCountResponseModel(BaseModel):
    """Pydantic model for TokenCountResponse validation."""
    text: str = Field(..., min_length=1)
    tokens: int = Field(0, ge=0)
    characters: int = Field(0, ge=0)
    model: str = Field(..., min_length=1)


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
    """A single message in a conversation."""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
    def __post_init__(self):
        """Validate after initialization."""
        if not self.content or not self.content.strip():
            raise ValueError('Message content cannot be empty')
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "role": self.role.value,
            "content": self.content,
        }
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
            content=data["content"],
            name=data.get("name"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )
    
    def validate(self) -> MessageModel:
        """Validate using Pydantic model."""
        return MessageModel(
            role=self.role,
            content=self.content,
            name=self.name,
            tool_calls=self.tool_calls,
            tool_call_id=self.tool_call_id
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
    
    def __post_init__(self):
        """Validate after initialization."""
        if not self.messages:
            raise ValueError('Messages list cannot be empty')
        if self.temperature < 0 or self.temperature > 2:
            raise ValueError('Temperature must be between 0 and 2')
        if self.top_p < 0 or self.top_p > 1:
            raise ValueError('Top_p must be between 0 and 1')
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError('max_tokens must be positive')
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "messages": [msg.to_dict() for msg in self.messages],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": self.stream,
        }
        if self.model:
            result["model"] = self.model
        if self.max_tokens:
            result["max_tokens"] = self.max_tokens
        if self.frequency_penalty:
            result["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty:
            result["presence_penalty"] = self.presence_penalty
        if self.stop:
            result["stop"] = self.stop
        if self.tools:
            result["tools"] = self.tools
        if self.tool_choice:
            result["tool_choice"] = self.tool_choice
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    def validate(self) -> ChatRequestModel:
        """Validate using Pydantic model."""
        return ChatRequestModel(
            messages=[MessageModel(
                role=msg.role,
                content=msg.content,
                name=msg.name,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id
            ) for msg in self.messages],
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
            metadata=self.metadata
        )


@dataclass
class Usage:
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    def __post_init__(self):
        if self.prompt_tokens < 0:
            raise ValueError('prompt_tokens cannot be negative')
        if self.completion_tokens < 0:
            raise ValueError('completion_tokens cannot be negative')
        if self.total_tokens < 0:
            raise ValueError('total_tokens cannot be negative')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Usage":
        return cls(
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
        )
    
    def validate(self) -> UsageModel:
        """Validate using Pydantic model."""
        return UsageModel(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens
        )


@dataclass
class ChatChoice:
    """A single completion choice."""
    index: int
    message: Message
    finish_reason: Optional[str] = None
    
    def __post_init__(self):
        if self.index < 0:
            raise ValueError('Index cannot be negative')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatChoice":
        return cls(
            index=data.get("index", 0),
            message=Message.from_dict(data["message"]),
            finish_reason=data.get("finish_reason"),
        )
    
    def validate(self) -> ChatChoiceModel:
        """Validate using Pydantic model."""
        return ChatChoiceModel(
            index=self.index,
            message=self.message.validate(),
            finish_reason=self.finish_reason
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
    
    def __post_init__(self):
        if not self.id or not self.id.strip():
            raise ValueError('Response ID cannot be empty')
        if not self.choices:
            raise ValueError('Choices list cannot be empty')
        if not self.model or not self.model.strip():
            raise ValueError('Model cannot be empty')
    
    @property
    def first_choice(self) -> ChatChoice:
        return self.choices[0]
    
    @property
    def content(self) -> str:
        return self.first_choice.message.content if self.choices else ""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatResponse":
        return cls(
            id=data["id"],
            choices=[ChatChoice.from_dict(c) for c in data["choices"]],
            usage=Usage.from_dict(data["usage"]),
            created=datetime.fromtimestamp(data.get("created", datetime.now().timestamp())),
            model=data.get("model", ""),
            system_fingerprint=data.get("system_fingerprint"),
            metadata=data.get("metadata"),
        )
    
    def validate(self) -> ChatResponseModel:
        """Validate using Pydantic model."""
        return ChatResponseModel(
            id=self.id,
            choices=[c.validate() for c in self.choices],
            usage=self.usage.validate(),
            created=self.created,
            model=self.model,
            system_fingerprint=self.system_fingerprint,
            metadata=self.metadata
        )


@dataclass
class EmbeddingRequest:
    """Request for embeddings."""
    input: Union[str, List[str]]
    model: Optional[str] = None
    dimensions: Optional[int] = None
    
    def __post_init__(self):
        """Validate after initialization."""
        if isinstance(self.input, str) and not self.input.strip():
            raise ValueError('Input text cannot be empty')
        if isinstance(self.input, list) and not self.input:
            raise ValueError('Input list cannot be empty')
        if self.dimensions is not None and self.dimensions <= 0:
            raise ValueError('Dimensions must be positive')
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"input": self.input}
        if self.model:
            result["model"] = self.model
        if self.dimensions:
            result["dimensions"] = self.dimensions
        return result
    
    def validate(self) -> EmbeddingRequestModel:
        """Validate using Pydantic model."""
        return EmbeddingRequestModel(
            input=self.input,
            model=self.model,
            dimensions=self.dimensions
        )


@dataclass
class Embedding:
    """A single embedding vector."""
    index: int
    vector: List[float]
    text: Optional[str] = None
    
    def __post_init__(self):
        if self.index < 0:
            raise ValueError('Index cannot be negative')
        if not self.vector:
            raise ValueError('Vector cannot be empty')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Embedding":
        return cls(
            index=data.get("index", 0),
            vector=data["embedding"],
            text=data.get("text"),
        )
    
    def validate(self) -> EmbeddingModel:
        """Validate using Pydantic model."""
        return EmbeddingModel(
            index=self.index,
            embedding=self.vector,
            text=self.text
        )


@dataclass
class EmbeddingResponse:
    """Response from embeddings."""
    embeddings: List[Embedding]
    model: str
    usage: Usage
    
    def __post_init__(self):
        if not self.embeddings:
            raise ValueError('Embeddings list cannot be empty')
        if not self.model or not self.model.strip():
            raise ValueError('Model cannot be empty')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmbeddingResponse":
        return cls(
            embeddings=[Embedding.from_dict(e) for e in data["data"]],
            model=data.get("model", ""),
            usage=Usage.from_dict(data.get("usage", {})),
        )
    
    def validate(self) -> EmbeddingResponseModel:
        """Validate using Pydantic model."""
        return EmbeddingResponseModel(
            data=[e.validate() for e in self.embeddings],
            model=self.model,
            usage=self.usage.validate()
        )


@dataclass
class TokenCountResponse:
    """Response from token counting."""
    text: str
    tokens: int
    characters: int
    model: str
    
    def __post_init__(self):
        if not self.text or not self.text.strip():
            raise ValueError('Text cannot be empty')
        if self.tokens < 0:
            raise ValueError('Tokens cannot be negative')
        if self.characters < 0:
            raise ValueError('Characters cannot be negative')
        if not self.model or not self.model.strip():
            raise ValueError('Model cannot be empty')
    
    def validate(self) -> TokenCountResponseModel:
        """Validate using Pydantic model."""
        return TokenCountResponseModel(
            text=self.text,
            tokens=self.tokens,
            characters=self.characters,
            model=self.model
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
    
    def __post_init__(self):
        if not self.file_id or not self.file_id.strip():
            raise ValueError('File ID cannot be empty')
        if not self.filename or not self.filename.strip():
            raise ValueError('Filename cannot be empty')
        if self.size < 0:
            raise ValueError('Size cannot be negative')
    
    def validate(self) -> FileUploadResponseModel:
        """Validate using Pydantic model."""
        return FileUploadResponseModel(
            file_id=self.file_id,
            filename=self.filename,
            mime_type=self.mime_type,
            size=self.size,
            created_at=self.created_at,
            expires_at=self.expires_at
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
    
    def __post_init__(self):
        if not self.file_id or not self.file_id.strip():
            raise ValueError('File ID cannot be empty')
        if not self.filename or not self.filename.strip():
            raise ValueError('Filename cannot be empty')
        if self.size < 0:
            raise ValueError('Size cannot be negative')
    
    def validate(self) -> FileInfoResponseModel:
        """Validate using Pydantic model."""
        return FileInfoResponseModel(
            file_id=self.file_id,
            filename=self.filename,
            mime_type=self.mime_type,
            size=self.size,
            created_at=self.created_at,
            expires_at=self.expires_at,
            metadata=self.metadata
        )


@dataclass
class FilesListResponse:
    """Response from listing files."""
    files: List[Dict[str, Any]]
    total: int
    
    def __post_init__(self):
        if self.total < 0:
            raise ValueError('Total cannot be negative')
    
    def validate(self) -> FilesListResponseModel:
        """Validate using Pydantic model."""
        return FilesListResponseModel(
            files=self.files,
            total=self.total
        )


@dataclass
class DeleteFilesResponse:
    """Response from deleting files."""
    deleted: List[str]
    failed: List[str]
    success: bool
    
    def validate(self) -> DeleteFilesResponseModel:
        """Validate using Pydantic model."""
        return DeleteFilesResponseModel(
            deleted=self.deleted,
            failed=self.failed,
            success=self.success
        )