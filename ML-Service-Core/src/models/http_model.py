from typing import Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: Optional[float] = None


class StatusResponse(BaseModel):
    current_operation: str
    active_tasks: int