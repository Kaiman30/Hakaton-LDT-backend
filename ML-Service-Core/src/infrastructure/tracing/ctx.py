from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4


@dataclass(slots=True)
class TraceContext:
    trace_id: str
    correlation_id: str
    task_id: str | None = None


_current_trace: ContextVar[TraceContext | None] = ContextVar(
    "trace_context",
    default=None,
)


def start_trace(task_id=None):
    ctx = TraceContext(
        trace_id=str(uuid4()),
        correlation_id=str(uuid4()),
        task_id=task_id,
    )

    _current_trace.set(ctx)

    return ctx


def current_trace():
    return _current_trace.get()


def clear_trace():
    _current_trace.set(None)