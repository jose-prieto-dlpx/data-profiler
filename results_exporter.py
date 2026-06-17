from __future__ import annotations

import csv
import io
from pathlib import Path

from models import ClassificationResult


class ResultsExporter:
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
        "reasoning",
        "error",
    ]

    DISPLAY_HEADERS = [
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

    @staticmethod
    def to_csv(results: list[ClassificationResult]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=ResultsExporter.HEADERS)
        writer.writeheader()
        for result in results:
            row = result.to_dict()
            row["confidence"] = f"{result.confidence:.4f}"
            row["sensitive"] = str(result.sensitive).upper()
            writer.writerow(row)
        return buffer.getvalue()

    @staticmethod
    def to_pretty_table(results: list[ClassificationResult]) -> str:
        if not results:
            return "No results."

        rows = [r.to_dict() for r in results]
        widths: dict[str, int] = {}

        for header in ResultsExporter.DISPLAY_HEADERS:
            max_len = max(
                len(str(row.get(header, ""))) if header != "confidence" else len("0.0000")
                for row in rows
            )
            widths[header] = max(len(header), max_len)

        sep = "-+-".join("-" * widths[h] for h in ResultsExporter.DISPLAY_HEADERS)
        lines = [
            " | ".join(h.ljust(widths[h]) for h in ResultsExporter.DISPLAY_HEADERS),
            sep,
        ]

        for result in results:
            values = []
            for h in ResultsExporter.DISPLAY_HEADERS:
                val = result.to_dict()[h]
                if h == "confidence":
                    val = f"{val:.4f}"
                values.append(str(val).ljust(widths[h]))
            lines.append(" | ".join(values))

        return "\n".join(lines)

    @staticmethod
    def to_file(results: list[ClassificationResult], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write(ResultsExporter.to_csv(results))
