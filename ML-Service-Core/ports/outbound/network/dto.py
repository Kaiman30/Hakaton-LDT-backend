# ports/outbound/http/dto.py
"""
Data Transfer Objects for HTTP client communication with Pydantic v2 validation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, AsyncIterator, Tuple
from pydantic import BaseModel, Field, HttpUrl, field_validator, ConfigDict


# ============ Pydantic Models for Validation ============

class HTTPRequestModel(BaseModel):
    """Pydantic model for HTTPRequest validation."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str = Field(..., min_length=1)
    method: str = Field("GET", min_length=2, max_length=10)
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, Any]] = None
    json_data: Optional[Any] = None
    data: Optional[Union[Dict[str, Any], bytes, str]] = None
    timeout: Optional[float] = Field(None, gt=0)
    follow_redirects: bool = True

    @field_validator('method')
    @classmethod
    def normalize_method(cls, v: str) -> str:
        return v.upper().strip()


class HTTPResponseModel(BaseModel):
    """Pydantic model for HTTPResponse validation."""
    status_code: int = Field(..., ge=100, le=599)
    headers: Dict[str, str]
    body: bytes
    url: str
    
    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


# ============ Dataclass Versions ============

@dataclass
class HTTPRequest:
    """Request DTO for HTTP operations."""
    url: str
    method: str = "GET"
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, Any]] = None
    json_data: Optional[Any] = None
    data: Optional[Union[Dict[str, Any], bytes, str]] = None
    timeout: Optional[float] = None
    follow_redirects: bool = True

    def __post_init__(self) -> None:
        self.method = self.method.upper().strip()
        if not self.url or not self.url.strip():
            raise ValueError("URL cannot be empty")
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError("Timeout must be positive")

    def validate(self) -> HTTPRequestModel:
        return HTTPRequestModel(
            url=self.url,
            method=self.method,
            headers=self.headers,
            params=self.params,
            json_data=self.json_data,
            data=self.data,
            timeout=self.timeout,
            follow_redirects=self.follow_redirects,
        )


@dataclass
class HTTPResponse:
    """Response DTO for HTTP operations."""
    status_code: int
    headers: Dict[str, str]
    body: bytes
    url: str

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        import json
        return json.loads(self.body.decode('utf-8'))

    @property
    def text(self) -> str:
        return self.body.decode('utf-8')

    def validate(self) -> HTTPResponseModel:
        return HTTPResponseModel(
            status_code=self.status_code,
            headers=self.headers,
            body=self.body,
            url=self.url,
        )