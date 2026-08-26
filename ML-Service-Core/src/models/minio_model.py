"""
MinIO модели — только request/response
"""

from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class MinIORequest(BaseModel):
    """Запрос на работу с MinIO"""
    bucket: str = Field(..., description="Название bucket")
    object_name: str = Field(..., description="Путь к файлу в bucket")
    # Расширяемо при необходимости
    content_type: Optional[str] = Field(default="application/octet-stream")

class MinIOResponse(BaseModel):
    """Ответ от MinIO"""
    bucket: str
    object_name: str
    file_size_bytes: int
    content_type: str
    etag: Optional[str] = None  # Для upload
    last_modified: Optional[str] = Field(default_factory=lambda: datetime.utcnow().isoformat())
