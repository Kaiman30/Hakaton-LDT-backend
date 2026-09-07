"""
БД модели для логгирования событий жизненного цикла
Только запись событий, чтение не требуется
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class DBLogEvent(str, Enum):
    """Типы событий для логгирования"""
    TASK_RECEIVED = "task_received"
    STATUS_UPDATED = "status_updated"
    FILE_DOWNLOADED = "file_downloaded"
    LLM_STARTED = "llm_started"
    LLM_COMPLETED = "llm_completed"
    TASK_COMPLETED = "task_completed"
    WORKER_BOOTSTRAP = "worker_bootstrap"
    HEALTH_CHECK = "health_check"


class DBLogEntry(BaseModel):
    """Запись лога в БД"""
    task_id: Optional[str] = Field(default=None, description="ID задачи (NULL для системных)")
    trace_id: Optional[str] = Field(default=None, description="Trace ID")
    event: DBLogEvent = Field(..., description="Тип события")
    status: str = Field(default="success", description="started/success/error")
    duration_ms: float = Field(default=0.0, description="Время выполнения")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Доп. данные")

    # Автогенерируемые поля
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
