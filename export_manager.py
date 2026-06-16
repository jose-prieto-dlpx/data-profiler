from __future__ import annotations

import csv
import io
from pathlib import Path

from models import PipelineResult


class ExportManager:
    HEADERS = [
        "schema_name",
        "table_name",
        "column_name",
        "data_type",
        "status",
        "category",
        "confidence",
        "sensitive",
        "masking_method",
        "decided_by",
        "notes",
        "error",
    ]

    def results_to_csv_text(self, results: list[PipelineResult]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=self.HEADERS)
        writer.writeheader()
        for result in results:
            writer.writerow(result.to_csv_row())
        return buffer.getvalue()

    def write_csv(self, results: list[PipelineResult], output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.HEADERS)
            writer.writeheader()
            for result in results:
                writer.writerow(result.to_csv_row())
