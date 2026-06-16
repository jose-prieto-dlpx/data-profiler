from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ColumnMetadata:
    schema_name: str
    table_name: str
    column_name: str
    data_type: str
    ordinal_position: int


@dataclass
class ClassificationDecision:
    status: str
    category: str
    confidence: float
    decided_by: str
    sensitive: bool = False
    masking_method: str = ""
    notes: str = ""
    error: str = ""


@dataclass
class PipelineResult:
    column: ColumnMetadata
    decision: ClassificationDecision

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "schema_name": self.column.schema_name,
            "table_name": self.column.table_name,
            "column_name": self.column.column_name,
            "data_type": self.column.data_type,
            "status": self.decision.status,
            "category": self.decision.category,
            "confidence": f"{self.decision.confidence:.4f}",
            "sensitive": str(self.decision.sensitive).upper(),
            "masking_method": self.decision.masking_method,
            "decided_by": self.decision.decided_by,
            "notes": self.decision.notes,
            "error": self.decision.error,
        }
