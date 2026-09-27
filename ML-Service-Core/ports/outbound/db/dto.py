# ports/outbound/db/dto.py
"""
Data Transfer Objects for database communication with Pydantic v2 validation.
Supports positional and named SQL parameters.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Sequence, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator


# ============ Pydantic Models for Validation ============

class QueryRequestModel(BaseModel):
    """Pydantic model for QueryRequest validation."""
    sql: str = Field(..., min_length=1)
    params: Optional[Union[Dict[str, Any], Sequence[Any]]] = None
    timeout: Optional[float] = Field(None, gt=0)
    fetch_size: Optional[int] = Field(None, gt=0, le=100000)
    
    @field_validator('sql')
    @classmethod
    def sql_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('SQL query cannot be empty')
        return v


class QueryResponseModel(BaseModel):
    """Pydantic model for QueryResponse validation."""
    rows: List[Dict[str, Any]]
    row_count: int = Field(..., ge=0)
    columns: List[str]
    execution_time: float = Field(..., ge=0)


class ExecuteRequestModel(BaseModel):
    """Pydantic model for ExecuteRequest validation."""
    sql: str = Field(..., min_length=1)
    params: Optional[Union[Dict[str, Any], Sequence[Any]]] = None
    timeout: Optional[float] = Field(None, gt=0)
    
    @field_validator('sql')
    @classmethod
    def sql_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('SQL query cannot be empty')
        return v


class ExecuteResponseModel(BaseModel):
    """Pydantic model for ExecuteResponse validation."""
    affected_rows: int = Field(..., ge=0)
    last_insert_id: Optional[Union[int, str]] = None


class TransactionRequestModel(BaseModel):
    """Pydantic model for TransactionRequest validation."""
    operations: List[Dict[str, Any]] = Field(..., min_length=1)
    isolation_level: Optional[str] = Field(None, min_length=1)
    timeout: Optional[float] = Field(None, gt=0)


class TransactionResponseModel(BaseModel):
    """Pydantic model for TransactionResponse validation."""
    results: List[Dict[str, Any]]
    committed: bool
    duration: float = Field(..., ge=0)


# ============ Dataclass Versions ============

@dataclass
class QueryRequest:
    """Request to execute a query."""
    sql: str
    params: Optional[Union[Dict[str, Any], Sequence[Any]]] = None
    timeout: Optional[float] = None
    fetch_size: Optional[int] = None
    
    def __post_init__(self) -> None:
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
            fetch_size=self.fetch_size,
        )


@dataclass
class QueryResponse:
    """Response from a query."""
    rows: List[Dict[str, Any]]
    row_count: int
    columns: List[str]
    execution_time: float

    def validate(self) -> QueryResponseModel:
        return QueryResponseModel(
            rows=self.rows,
            row_count=self.row_count,
            columns=self.columns,
            execution_time=self.execution_time,
        )


@dataclass
class ExecuteRequest:
    """Request to execute a command."""
    sql: str
    params: Optional[Union[Dict[str, Any], Sequence[Any]]] = None
    timeout: Optional[float] = None
    
    def __post_init__(self) -> None:
        if not self.sql or not self.sql.strip():
            raise ValueError('SQL query cannot be empty')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('Timeout must be positive')
    
    def validate(self) -> ExecuteRequestModel:
        """Validate using Pydantic model."""
        return ExecuteRequestModel(
            sql=self.sql,
            params=self.params,
            timeout=self.timeout,
        )


@dataclass
class ExecuteResponse:
    """Response from a command."""
    affected_rows: int
    last_insert_id: Optional[Union[int, str]] = None

    def validate(self) -> ExecuteResponseModel:
        return ExecuteResponseModel(
            affected_rows=self.affected_rows,
            last_insert_id=self.last_insert_id,
        )


@dataclass
class TransactionRequest:
    """Request to execute a transactional batch of operations."""
    operations: List[Union[QueryRequest, ExecuteRequest]]
    isolation_level: Optional[str] = None
    timeout: Optional[float] = None
    
    def __post_init__(self) -> None:
        if not self.operations:
            raise ValueError('Operations list cannot be empty')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('Timeout must be positive')
    
    def validate(self) -> TransactionRequestModel:
        """Validate using Pydantic model."""
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
            timeout=self.timeout,
        )


@dataclass
class TransactionResponse:
    """Response from a transaction."""
    results: List[Union[QueryResponse, ExecuteResponse]]
    committed: bool
    duration: float

    def validate(self) -> TransactionResponseModel:
        return TransactionResponseModel(
            results=[
                r.validate().model_dump() if hasattr(r, "validate") else str(r)
                for r in self.results
            ],
            committed=self.committed,
            duration=self.duration,
        )