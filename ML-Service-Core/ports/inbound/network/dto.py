# ports/inbound/network/dto.py
"""
Data Transfer Objects for HTTP communication with Pydantic validation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator


class HttpMethod(str, Enum):
    """HTTP methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


# ============ Pydantic Models for Validation ============

class HttpRequestModel(BaseModel):
    """Pydantic model for HttpRequest validation."""
    url: str = Field(..., min_length=1)
    method: HttpMethod = HttpMethod.GET
    headers: Dict[str, str] = Field(default_factory=dict)
    params: Optional[Dict[str, Any]] = None
    data: Optional[Union[Dict[str, Any], str, bytes]] = None
    json: Optional[Dict[str, Any]] = None
    files: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = Field(30.0, gt=0)
    verify_ssl: bool = True
    
    @validator('url')
    def url_valid(cls, v):
        if not v or not v.strip():
            raise ValueError('URL cannot be empty')
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v
    
    @validator('timeout')
    def timeout_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Timeout must be positive')
        return v


# ============ Dataclass Versions ============

@dataclass
class HttpRequest:
    """HTTP request."""
    url: str
    method: HttpMethod = HttpMethod.GET
    headers: Dict[str, str] = field(default_factory=dict)
    params: Optional[Dict[str, Any]] = None
    data: Optional[Union[Dict[str, Any], str, bytes]] = None
    json: Optional[Dict[str, Any]] = None
    files: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = 30.0
    verify_ssl: bool = True
    
    def __post_init__(self):
        if not self.url or not self.url.strip():
            raise ValueError('URL cannot be empty')
        if not self.url.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('Timeout must be positive')
    
    def validate(self) -> HttpRequestModel:
        """Validate using Pydantic model."""
        return HttpRequestModel(
            url=self.url,
            method=self.method,
            headers=self.headers,
            params=self.params,
            data=self.data,
            json=self.json,
            files=self.files,
            timeout=self.timeout,
            verify_ssl=self.verify_ssl
        )


@dataclass
class HttpResponse:
    """HTTP response."""
    status_code: int
    headers: Dict[str, str]
    data: Optional[bytes] = None
    text: Optional[str] = None
    json_data: Optional[Dict[str, Any]] = None
    url: Optional[str] = None
    elapsed: Optional[float] = None
    
    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300
    
    @property
    def is_redirect(self) -> bool:
        return 300 <= self.status_code < 400
    
    @property
    def is_error(self) -> bool:
        return self.status_code >= 400