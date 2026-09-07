# ports/outbound/db/dto.py
"""
Data Transfer Objects for database communication with Pydantic validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator, root_validator


# ============ Pydantic Models for Validation ============

class QueryRequestModel(BaseModel):
    """Pydantic model for QueryRequest validation."""
    sql: str = Field(..., min_length=1)
    params: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = Field(None, gt=0)
    fetch_size: Optional[int] = Field(None, gt=0, le=100000)
    
    @validator('sql')
    def sql_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('SQL query cannot be empty')
        return v


class ExecuteRequestModel(BaseModel):
    """Pydantic model for ExecuteRequest validation."""
    sql: str = Field(..., min_length=1)
    params: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = Field(None, gt=0)
    
    @validator('sql')
    def sql_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('SQL query cannot be empty')
        return v


class TransactionRequestModel(BaseModel):
    """Pydantic model for TransactionRequest validation."""
    operations: List[Union[Dict[str, Any], Any]] = Field(..., min_items=1)
    isolation_level: Optional[str] = Field(None, min_length=1)
    timeout: Optional[float] = Field(None, gt=0)
    
    @validator('operations')
    def operations_not_empty(cls, v):
        if not v:
            raise ValueError('Operations list cannot be empty')
        return v


# ============ Dataclass Versions ============

@dataclass
class QueryRequest:
    """Request to execute a query."""
    sql: str
    params: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = None
    fetch_size: Optional[int] = None
    
    def __post_init__(self):
        if not self.sql or not self.sql.strip():
            raise ValueError('SQL query cannot be empty')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('Timeout must be positive')
        if self.fetch_size is not None and self.fetch_size <= 0:
            raise ValueError('Fetch size must be positive')
    
    def validate(self) -> QueryRequestModel:
        """Validate using Pydantic model."""
        return QueryRequestModel(
            sql=self.sql,
            params=self.params,
            timeout=self.timeout,
            fetch_size=self.fetch_size
        )


@dataclass
class QueryResponse:
    """Response from a query."""
    rows: List[Dict[str, Any]]
    row_count: int
    columns: List[str]
    execution_time: float


@dataclass
class ExecuteRequest:
    """Request to execute a command."""
    sql: str
    params: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = None
    
    def __post_init__(self):
        if not self.sql or not self.sql.strip():
            raise ValueError('SQL query cannot be empty')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('Timeout must be positive')
    
    def validate(self) -> ExecuteRequestModel:
        """Validate using Pydantic model."""
        return ExecuteRequestModel(
            sql=self.sql,
            params=self.params,
            timeout=self.timeout
        )


@dataclass
class ExecuteResponse:
    """Response from a command."""
    affected_rows: int
    last_insert_id: Optional[int] = None


@dataclass
class TransactionRequest:
    """Request to execute a transaction."""
    operations: List[Union[QueryRequest, ExecuteRequest]]
    isolation_level: Optional[str] = None
    timeout: Optional[float] = None
    
    def __post_init__(self):
        if not self.operations:
            raise ValueError('Operations list cannot be empty')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('Timeout must be positive')
    
    def validate(self) -> TransactionRequestModel:
        """Validate using Pydantic model."""
        # Convert operations to dict representation for validation
        ops_data = []
        for op in self.operations:
            if isinstance(op, QueryRequest):
                ops_data.append({"type": "query", "sql": op.sql, "params": op.params})
            elif isinstance(op, ExecuteRequest):
                ops_data.append({"type": "execute", "sql": op.sql, "params": op.params})
            else:
                ops_data.append({"type": "unknown", "data": str(op)})
        
        return TransactionRequestModel(
            operations=ops_data,
            isolation_level=self.isolation_level,
            timeout=self.timeout
        )


@dataclass
class TransactionResponse:
    """Response from a transaction."""
    results: List[Union[QueryResponse, ExecuteResponse]]
    committed: bool
    duration: float