
"""
Единый observer с декораторной конфигурацией.
Один класс — множество поведений через декораторы.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, ParamSpec, TYPE_CHECKING

T = TypeVar('T')
P = ParamSpec('P')

# Optional import — только для type checking
if TYPE_CHECKING:
    try:
        from prometheus_client import Counter, Histogram
    except ImportError:
        pass


class EventType(str, Enum):
    OPERATION_STARTED = "operation_started"
    OPERATION_COMPLETED = "operation_completed"
    OPERATION_FAILED = "operation_failed"


@dataclass(frozen=True)
class ConnectorEvent:
    """Единая структура для ВСЕХ событий."""
    event_type: EventType
    source: str
    action: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "source": self.source,
            "action": self.action,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
            "payload": self.payload,
        }


# ============ ДЕКОРАТОРЫ ============

def traced(action: Optional[str] = None):
    """Декоратор: автоматически создаёт события start/complete/fail."""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Определяем action заранее, в момент декорирования
        _action_name = action or func.__name__
        
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            _source = args[0].__class__.__name__ if args else "unknown"
            
            start = time.perf_counter()
            publisher = _get_publisher()
            
            # START
            if publisher:
                publisher.emit_sync(ConnectorEvent(
                    event_type=EventType.OPERATION_STARTED,
                    source=_source,
                    action=_action_name,
                    metadata={"args_count": len(args), "kwargs_keys": list(kwargs.keys())},
                ))
            
            try:
                result = await func(*args, **kwargs)
                
                # COMPLETE
                if publisher:
                    publisher.emit_sync(ConnectorEvent(
                        event_type=EventType.OPERATION_COMPLETED,
                        source=_source,
                        action=_action_name,
                        duration_ms=(time.perf_counter() - start) * 1000,
                        payload={"result_type": type(result).__name__},
                    ))
                return result
                
            except Exception as e:
                # FAIL
                if publisher:
                    publisher.emit_sync(ConnectorEvent(
                        event_type=EventType.OPERATION_FAILED,
                        source=_source,
                        action=_action_name,
                        duration_ms=(time.perf_counter() - start) * 1000,
                        success=False,
                        error=str(e),
                        payload={"exception_type": type(e).__name__},
                    ))
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            _source = args[0].__class__.__name__ if args else "unknown"
            
            start = time.perf_counter()
            publisher = _get_publisher()
            
            if publisher:
                publisher.emit_sync(ConnectorEvent(
                    event_type=EventType.OPERATION_STARTED,
                    source=_source,
                    action=_action_name,
                ))
            
            try:
                result = func(*args, **kwargs)
                if publisher:
                    publisher.emit_sync(ConnectorEvent(
                        event_type=EventType.OPERATION_COMPLETED,
                        source=_source,
                        action=_action_name,
                        duration_ms=(time.perf_counter() - start) * 1000,
                    ))
                return result
            except Exception as e:
                if publisher:
                    publisher.emit_sync(ConnectorEvent(
                        event_type=EventType.OPERATION_FAILED,
                        source=_source,
                        action=_action_name,
                        success=False,
                        error=str(e),
                    ))
                raise
        
        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        wrapper._is_traced = True  # type: ignore
        wrapper._traced_action = _action_name  # type: ignore
        return wrapper
    
    return decorator


def metered(counter_name: Optional[str] = None, histogram_name: Optional[str] = None):
    """Декоратор: считает вызовы и latency."""
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        _counter = counter_name or f"{func.__name__}_total"
        _hist = histogram_name or f"{func.__name__}_duration_ms"
        
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            metrics = _get_metrics()
            if metrics:
                metrics.inc_counter(_counter)
            
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                if metrics:
                    metrics.observe_histogram(_hist, (time.perf_counter() - start) * 1000)
        
        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            metrics = _get_metrics()
            if metrics:
                metrics.inc_counter(_counter)
            
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                if metrics:
                    metrics.observe_histogram(_hist, (time.perf_counter() - start) * 1000)
        
        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    return decorator


# ============ ЕДИНЫЙ PUBLISHER ============

class UnifiedPublisher:
    """
    Один publisher — все observer\'ы внутри.
    """
    
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        max_traces: int = 10000,
        enable_prometheus: bool = False,
    ):
        self.logger = logger
        self._traces: deque = deque(maxlen=max_traces)
        self._trace_lock = threading.Lock()
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self._metrics_lock = threading.Lock()
        self._failed_sources: Set[str] = set()
        self._enable_prometheus = enable_prometheus
        
        # Prometheus — lazy init
        self._prom_counters: Optional[Dict[str, Any]] = None
        self._prom_histograms: Optional[Dict[str, Any]] = None
    
    def _init_prometheus(self) -> None:
        """Lazy init prometheus metrics."""
        if self._prom_counters is not None:
            return
        try:
            from prometheus_client import Counter, Histogram
            self._prom_counters = {}
            self._prom_histograms = {}
        except ImportError:
            self._enable_prometheus = False
            self._prom_counters = {}
            self._prom_histograms = {}
    
    # --- Единая точка входа ---
    
    def emit_sync(self, event: ConnectorEvent) -> None:
        """Синхронный вызов из любого места."""
        self._log(event)
        self._update_metrics(event)
        self._store_trace(event)
        if self._enable_prometheus:
            self._update_prometheus(event)
    
    async def emit(self, event: ConnectorEvent) -> None:
        """Async версия."""
        self.emit_sync(event)
    
    # --- Внутренние обработчики ---
    
    def _log(self, event: ConnectorEvent) -> None:
        if not self.logger:
            return
        
        level = logging.ERROR if not event.success else (
            logging.DEBUG if event.event_type == EventType.OPERATION_STARTED else logging.INFO
        )
        
        msg = f"[{event.event_type.value}] {event.source}::{event.action}"
        if event.duration_ms is not None:
            msg += f" ({event.duration_ms:.2f}ms)"
        if event.error:
            msg += f" - {event.error}"
        
        extra = {
            "trace_id": event.metadata.get("trace_id"),
            "event_type": event.event_type.value,
            "source": event.source,
            "action": event.action,
        }
        
        self.logger.log(level, msg, extra=extra)
    
    def _update_metrics(self, event: ConnectorEvent) -> None:
        if event.duration_ms is None:
            return
        
        key = f"{event.source}.{event.action}"
        
        with self._metrics_lock:
            if key not in self._metrics:
                self._metrics[key] = {"count": 0, "total_ms": 0.0, "min_ms": float, "max_ms": 0.0}
            
            m = self._metrics[key]
            m["count"] += 1
            m["total_ms"] += event.duration_ms
            m["min_ms"] = min(m["min_ms"], event.duration_ms)
            m["max_ms"] = max(m["max_ms"], event.duration_ms)
    
    def _store_trace(self, event: ConnectorEvent) -> None:
        with self._trace_lock:
            self._traces.append(event)
    
    def _update_prometheus(self, event: ConnectorEvent) -> None:
        if not self._enable_prometheus:
            return
        self._init_prometheus()
        # Реализация при необходимости
    
    # --- Метрики API для декоратора @metered ---
    
    def inc_counter(self, name: str) -> None:
        """Инкремент счётчика (для @metered)."""
        if not self._enable_prometheus:
            return
        self._init_prometheus()
        # TODO: реализация
    
    def observe_histogram(self, name: str, value: float) -> None:
        """Запись в гистограмму (для @metered)."""
        if not self._enable_prometheus:
            return
        self._init_prometheus()
        # TODO: реализация
    
    # --- Query API ---
    
    def get_metrics(self) -> Dict[str, Dict[str, float]]:
        with self._metrics_lock:
            result = {}
            for key, m in self._metrics.items():
                if m["count"] > 0:
                    result[key] = {
                        "count": m["count"],
                        "avg_ms": m["total_ms"] / m["count"],
                        "min_ms": m["min_ms"],
                        "max_ms": m["max_ms"],
                    }
            return result
    
    def get_traces(self, limit: int = 100, source: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._trace_lock:
            traces = list(self._traces)
            if source:
                traces = [t for t in traces if t.source == source]
            return [t.to_dict() for t in traces[-limit:]]
    
    def reset(self) -> None:
        with self._metrics_lock:
            self._metrics.clear()
        with self._trace_lock:
            self._traces.clear()


# ============ ГЛОБАЛЬНЫЙ ДОСТУП ============

_publisher: Optional[UnifiedPublisher] = None
_metrics: Optional[UnifiedPublisher] = None

def init_publisher(logger: Optional[logging.Logger] = None, **kwargs) -> UnifiedPublisher:
    global _publisher, _metrics
    _publisher = UnifiedPublisher(logger=logger, **kwargs)
    _metrics = _publisher
    return _publisher

def _get_publisher() -> Optional[UnifiedPublisher]:
    return _publisher

def _get_metrics() -> Optional[UnifiedPublisher]:
    return _metrics



# # ============ ИСПОЛЬЗОВАНИЕ ============

# # Инициализация (один раз)
# from utils.logging import get_logger
# init_publisher(logger=get_logger("app"))


# # В BL — просто декораторы
# class OCRWorker:
    
#     @traced(action="preprocess")
#     @metered(counter_name="ocr_preprocess_total")
#     async def preprocess(self, image: bytes, width: int, height: int) -> bytes:
#         """Только бизнес-логика. Никаких emit вручную."""
#         # ... обработка ...
#         return result
    
#     @traced  # action = "detect_text" (из имени метода)
#     async def detect_text(self, image: bytes) -> list[str]:
#         # ...
#         return ["text1", "text2"]


# # В Gateway
# class TaskHandler:
    
#     @traced(action="create_task")
#     async def create_task(self, tenant_id: str, files: list) -> dict:
#         # ...
#         return {"task_id": "abc123"}


# # Получение метрик (для health endpoint)
# metrics = _publisher.get_metrics()
# # {
# #   "OCRWorker.preprocess": {"count": 150, "avg_ms": 45.2, "min_ms": 12.0, "max_ms": 120.0},
# #   "TaskHandler.create_task": {"count": 50, "avg_ms": 5.1, ...}
