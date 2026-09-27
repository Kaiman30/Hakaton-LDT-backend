# ports/outbound/storage/dto.py
"""
Data Transfer Objects for Outbound Storage communication with Pydantic v2 validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, BinaryIO, Dict, List, Optional, Union, AsyncIterator
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StorageObjectType(str, Enum):
    """Types of storage objects."""
    FILE = "file"
    FOLDER = "folder"


# ============ Pydantic Models for Validation ============

class StorageObjectModel(BaseModel):
    """Pydantic model for StorageObject validation."""
    name: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    type: StorageObjectType
    size: Optional[int] = Field(None, ge=0)
    last_modified: Optional[datetime] = None
    etag: Optional[str] = None
    content_type: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    @field_validator('path')
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Path cannot be empty')
        return v.strip()


class UploadRequestModel(BaseModel):
    """Pydantic model for UploadRequest validation."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str = Field(..., min_length=1)
    data: Union[bytes, BinaryIO, str, AsyncIterator[bytes]]
    content_type: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    bucket: Optional[str] = Field(None, min_length=1)
    part_size: Optional[int] = Field(None, gt=0, le=1024 * 1024 * 100)  # Max 100MB

    @field_validator('path')
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Path cannot be empty')
        return v.strip()


class DownloadRequestModel(BaseModel):
    """Pydantic model for DownloadRequest validation."""
    path: str = Field(..., min_length=1)
    bucket: Optional[str] = Field(None, min_length=1)
    offset: Optional[int] = Field(None, ge=0)
    length: Optional[int] = Field(None, gt=0)
    version_id: Optional[str] = None

    @field_validator('path')
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Path cannot be empty')
        return v.strip()


class DeleteRequestModel(BaseModel):
    """Pydantic model for DeleteRequest validation."""
    paths: List[str] = Field(..., min_length=1)
    bucket: Optional[str] = Field(None, min_length=1)
    recursive: bool = False

    @field_validator('paths')
    @classmethod
    def paths_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError('Paths list cannot be empty')
        for path in v:
            if not path or not path.strip():
                raise ValueError('Path inside paths list cannot be empty')
        return v


class ListRequestModel(BaseModel):
    """Pydantic model for ListRequest validation."""
    path: str = Field(default="", min_length=0)
    bucket: Optional[str] = Field(None, min_length=1)
    recursive: bool = False
    max_items: Optional[int] = Field(None, gt=0, le=10000)
    prefix: Optional[str] = None
    delimiter: Optional[str] = None


# ============ Dataclass Versions ============

@dataclass
class StorageObject:
    """A file or folder in storage."""
    name: str
    path: str
    type: StorageObjectType
    size: Optional[int] = None
    last_modified: Optional[datetime] = None
    etag: Optional[str] = None
    content_type: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.path or not self.path.strip():
            raise ValueError('Path cannot be empty')
        if self.size is not None and self.size < 0:
            raise ValueError('Size cannot be negative')

    @property
    def is_file(self) -> bool:
        return self.type == StorageObjectType.FILE

    @property
    def is_folder(self) -> bool:
        return self.type == StorageObjectType.FOLDER

    def validate(self) -> StorageObjectModel:
        return StorageObjectModel(
            name=self.name,
            path=self.path,
            type=self.type,
            size=self.size,
            last_modified=self.last_modified,
            etag=self.etag,
            content_type=self.content_type,
            metadata=self.metadata,
        )


@dataclass
class UploadRequest:
    """Request to upload a file."""
    path: str
    data: Union[bytes, BinaryIO, str, AsyncIterator[bytes]]
    content_type: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    bucket: Optional[str] = None
    part_size: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.path or not self.path.strip():
            raise ValueError('Path cannot be empty')
        if self.part_size is not None and self.part_size <= 0:
            raise ValueError('Part size must be positive')

    def validate(self) -> UploadRequestModel:
        return UploadRequestModel(
            path=self.path,
            data=self.data,
            content_type=self.content_type,
            metadata=self.metadata,
            bucket=self.bucket,
            part_size=self.part_size,
        )


@dataclass
class UploadResponse:
    """Response from uploading."""
    path: str
    etag: str
    size: int
    upload_id: Optional[str] = None
    version_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.size < 0:
            raise ValueError('Size cannot be negative')


@dataclass
class DownloadRequest:
    """Request to download a file."""
    path: str
    bucket: Optional[str] = None
    offset: Optional[int] = None
    length: Optional[int] = None
    version_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.path or not self.path.strip():
            raise ValueError('Path cannot be empty')
        if self.offset is not None and self.offset < 0:
            raise ValueError('Offset cannot be negative')
        if self.length is not None and self.length <= 0:
            raise ValueError('Length must be positive')

    def validate(self) -> DownloadRequestModel:
        return DownloadRequestModel(
            path=self.path,
            bucket=self.bucket,
            offset=self.offset,
            length=self.length,
            version_id=self.version_id,
        )


@dataclass
class DownloadResponse:
    """Response from downloading (for small objects or metadata)."""
    content_type: str
    size: int
    last_modified: datetime
    etag: str
    data: Optional[bytes] = None


@dataclass
class DeleteRequest:
    """Request to delete files."""
    paths: List[str]
    bucket: Optional[str] = None
    recursive: bool = False

    def __post_init__(self) -> None:
        if not self.paths:
            raise ValueError('Paths list cannot be empty')
        for path in self.paths:
            if not path or not path.strip():
                raise ValueError('Path cannot be empty')

    def validate(self) -> DeleteRequestModel:
        return DeleteRequestModel(
            paths=self.paths,
            bucket=self.bucket,
            recursive=self.recursive,
        )


@dataclass
class DeleteResponse:
    """Response from deletion."""
    deleted: List[str]
    failed: List[Dict[str, Any]]


@dataclass
class ListRequest:
    """Request to list objects."""
    path: str = ""
    bucket: Optional[str] = None
    recursive: bool = False
    max_items: Optional[int] = None
    prefix: Optional[str] = None
    delimiter: Optional[str] = None

    def __post_init__(self) -> None:
        if self.max_items is not None and self.max_items <= 0:
            raise ValueError('max_items must be positive')

    def validate(self) -> ListRequestModel:
        return ListRequestModel(
            path=self.path,
            bucket=self.bucket,
            recursive=self.recursive,
            max_items=self.max_items,
            prefix=self.prefix,
            delimiter=self.delimiter,
        )


@dataclass
class ListResponse:
    """Response from listing."""
    objects: List[StorageObject]
    next_marker: Optional[str] = None
    is_truncated: bool = False