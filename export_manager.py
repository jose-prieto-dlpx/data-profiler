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
        "reasoning",
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

    def results_to_pretty_text(self, results: list[PipelineResult]) -> str:
        rows = [result.to_csv_row() for result in results]
        if not rows:
            return "No classification results."

        # Keep output concise while preserving key classification details.
        display_headers = [
            "schema_name",
            "table_name",
            "column_name",
            "status",
            "category",
            "confidence",
            "sensitive",
            "masking_method",
            "decided_by",
        ]

        widths: dict[str, int] = {}
        for header in display_headers:
            max_value_len = max(len(str(row.get(header, ""))) for row in rows)
            widths[header] = max(len(header), max_value_len)

        sep = "-+-".join("-" * widths[h] for h in display_headers)
        lines = []
        lines.append(" | ".join(h.ljust(widths[h]) for h in display_headers))
        lines.append(sep)

        for row in rows:
            lines.append(
                " | ".join(str(row.get(h, "")).ljust(widths[h]) for h in display_headers)
            )

        return "\n".join(lines)
