from __future__ import annotations

import json
import logging
import re
from typing import Any

from config_loader import ConfigData, Layer1Rule
from models import ClassificationResult, ColumnMetadata


DECIDED_BY_FILTER_0 = "Filter 0 - Blacklist"
DECIDED_BY_LAYER_0 = "Layer 0 - Schema Rules"
DECIDED_BY_EMPTY_CHECK = "Empty Check - No Sample Values"
DECIDED_BY_LAYER_1 = "Layer 1 - Regex Rules"
DECIDED_BY_LAYER_2 = "Layer 2 - LLM Fallback"


class LayerRouter:
    """Routes classification through 4 layers with confidence fallback."""

    def __init__(self, config: ConfigData, logger: logging.Logger | None = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def classify(self, column: ColumnMetadata, samples: list[str | None]) -> ClassificationResult:
        from config_loader import ConfigLoader

        col_key = (column.table_name, column.column_name)

        # Filter 0: Blacklist
        if ConfigLoader.is_blacklisted(self.config, column.table_name, column.column_name):
            return ClassificationResult(
                schema_name=column.schema_name,
                table_name=column.table_name,
                column_name=column.column_name,
                data_type=column.data_type,
                status="EXCLUDED",
                category="EXCLUDED",
                confidence=1.0,
                sensitive=False,
                masking_method="",
                decided_by=DECIDED_BY_FILTER_0,
                notes="Blacklisted.",
            )

        # Layer 0: Schema match
        rule0 = ConfigLoader.match_layer0(self.config, column.table_name, column.column_name)
        if rule0 and rule0.confidence >= self.config.confidence_threshold:
            result = ClassificationResult(
                schema_name=column.schema_name,
                table_name=column.table_name,
                column_name=column.column_name,
                data_type=column.data_type,
                status="CLASSIFIED",
                category=rule0.category,
                confidence=rule0.confidence,
                sensitive=False,
                masking_method="",
                decided_by=DECIDED_BY_LAYER_0,
                notes="Schema match.",
            )
            return self._apply_masking(result)

        # Empty column check
        non_empty = [
            str(v).strip() for v in samples if v is not None and str(v).strip()
        ]
        if not non_empty:
            return ClassificationResult(
                schema_name=column.schema_name,
                table_name=column.table_name,
                column_name=column.column_name,
                data_type=column.data_type,
                status="EMPTY_COLUMN",
                category="EMPTY_COLUMN",
                confidence=1.0,
                sensitive=False,
                masking_method="",
                decided_by=DECIDED_BY_EMPTY_CHECK,
                notes="No non-empty values in sample.",
            )

        # Layer 1: Local regex
        result1 = self._layer1_classify(non_empty)
        if result1["confidence"] >= self.config.confidence_threshold:
            result = ClassificationResult(
                schema_name=column.schema_name,
                table_name=column.table_name,
                column_name=column.column_name,
                data_type=column.data_type,
                status="CLASSIFIED",
                category=result1["category"],
                confidence=result1["confidence"],
                sensitive=False,
                masking_method="",
                decided_by=DECIDED_BY_LAYER_1,
                notes=result1["notes"],
            )
            return self._apply_masking(result) if result1["category"] != "UNKNOWN" else self._return_unclassified(column, DECIDED_BY_LAYER_1)

        # Layer 2: LLM (stub - to be called via API by classifier service)
        return self._return_unclassified(column, DECIDED_BY_LAYER_2)

    def _layer1_classify(self, values: list[str]) -> dict[str, Any]:
        best_cat = "UNKNOWN"
        best_score = 0.0
        best_rule = None

        for rule in self.config.layer_1_rules:
            try:
                matches = sum(
                    1 for v in values if re.search(rule.regex, v, re.IGNORECASE)
                )
            except re.error:
                self.logger.warning("Invalid regex: %s", rule.regex)
                continue

            score = min(1.0, rule.confidence * (matches / len(values)))
            if score > best_score:
                best_score = score
                best_cat = rule.category
                best_rule = rule

        notes = f"Best match: {best_rule.regex if best_rule else 'none'}, score={best_score:.4f}"
        return {"category": best_cat, "confidence": best_score, "notes": notes}

    def _return_unclassified(self, column: ColumnMetadata, layer: str) -> ClassificationResult:
        return ClassificationResult(
            schema_name=column.schema_name,
            table_name=column.table_name,
            column_name=column.column_name,
            data_type=column.data_type,
            status="UNCLASSIFIED",
            category="UNKNOWN",
            confidence=0.0,
            sensitive=False,
            masking_method="",
            decided_by=layer,
            notes="No layer met confidence threshold.",
        )

    def _apply_masking(self, result: ClassificationResult) -> ClassificationResult:
        if result.status != "CLASSIFIED":
            return result

        masking = self.config.security_masking.get(result.category.upper(), "")
        result.sensitive = True
        if masking:
            result.masking_method = masking
        else:
            result.masking_method = "REVIEW_REQUIRED"
            self.logger.warning(
                "Classified column %s.%s.%s as %s but no masking method is configured. "
                "Using fallback masking method %s.",
                result.schema_name,
                result.table_name,
                result.column_name,
                result.category,
                result.masking_method,
            )
        return result
