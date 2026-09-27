# cython_workers/func_spec/base_specs.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class IDataParserSpec(Protocol):
    """Контракт для C/Cython парсера."""
    def parse_payload(self, raw_bytes: bytes) -> dict: ...