from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class ColumnMetadata:
    """Database column metadata from data reader."""
    schema_name: str
    table_name: str
    column_name: str
    data_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClassificationResult:
    """Classification result from classifier service."""
    schema_name: str
    table_name: str
    column_name: str
    data_type: str
    status: str
    category: str
    confidence: float
    sensitive: bool
    masking_method: str
    decided_by: str
    notes: str
    reasoning: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
