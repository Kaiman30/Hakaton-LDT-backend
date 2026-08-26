"""
GigaChat API Data Models
Separated from connector to improve code organization and maintainability
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class GigaChatMessage:
    """Represents a single message in a conversation"""
    role: str  # 'system', 'user', 'assistant'
    content: str
    attachments: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary format for API"""
        result = {
            "role": self.role,
            "content": self.content
        }
        if self.attachments:
            result["attachments"] = self.attachments
        return result


@dataclass
class GigaChatChatRequest:
    """Request model for chat completion"""
    messages: List[GigaChatMessage]
    model: str = "GigaChat-Max"
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    stream: bool = False
    function_call: str = "auto"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert request to dictionary format for API"""
        result = {
            "function_call": self.function_call,
            "model": self.model,
            "messages": [msg.to_dict() for msg in self.messages],
            "temperature": self.temperature,
            "stream": self.stream,
        }
        if self.max_tokens:
            result["max_tokens"] = self.max_tokens
        return result


@dataclass
class GigaChatChatResponse:
    """Response model for chat completion"""
    response: str
    tokens_used: int
    tokens_total: int
    model: str
    usage: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format"""
        return asdict(self)


@dataclass
class GigaChatFileUploadRequest:
    """Request model for file upload"""
    purpose: str = "general"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert request to dictionary format for API"""
        return {"purpose": self.purpose}


@dataclass
class GigaChatFileInfo:
    """Model representing file information"""
    file_id: str
    filename: str
    size: Optional[int] = None
    created_at: Optional[str] = None
    purpose: Optional[str] = None
    status: str = "uploaded"
    
    @classmethod
    def from_api_response(cls, api_data: Dict[str, Any]) -> 'GigaChatFileInfo':
        """Create FileInfo from API response"""
        return cls(
            file_id=api_data.get("id"),
            filename=api_data.get("filename"),
            size=api_data.get("size"),
            created_at=api_data.get("created_at"),
            purpose=api_data.get("purpose"),
            status="uploaded"
        )


@dataclass
class GigaChatTokenResponse:
    """Response model for token refresh"""
    access_token: str
    expires_in: Optional[int] = None
    token_type: str = "Bearer"

    @classmethod
    def from_api_response(cls, api_data: Dict[str, Any]) -> 'GigaChatTokenResponse':
        """Create TokenResponse from API response"""
        # GigaChat API может возвращать expires_in как expires_at или вообще не включать
        expires_in_val = api_data.get("expires_in") or api_data.get("expires_at")
        return cls(
            access_token=api_data["access_token"],
            expires_in=expires_in_val,
            token_type=api_data.get("token_type", "Bearer")
        )


@dataclass
class GigaChatModelInfo:
    """Model representing model information"""
    id: str
    object: str
    owned_by: str
    created: int
    
    @classmethod
    def from_api_response(cls, api_data: Dict[str, Any]) -> 'GigaChatModelInfo':
        """Create ModelInfo from API response"""
        return cls(
            id=api_data["id"],
            object=api_data["object"],
            owned_by=api_data["owned_by"],
            created=api_data["created"]
        )


@dataclass
class GigaChatHealthCheckResponse:
    """Response model for health check"""
    success: bool
    models_available: Optional[List[GigaChatModelInfo]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format"""
        return asdict(self)
    