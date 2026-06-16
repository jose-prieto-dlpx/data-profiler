from __future__ import annotations

import logging

from config_manager import ConfigManager
from database_generic import DatabaseClient
from llm_clients import LLMClient
from local_classifier import LocalRegexClassifier
from models import ClassificationDecision, ColumnMetadata, PipelineResult


class ClassificationPipeline:
    def __init__(
        self,
        db_client: DatabaseClient,
        config_manager: ConfigManager,
        llm_client: LLMClient,
        logger: logging.Logger | None = None,
    ) -> None:
        self._db = db_client
        self._cfg_mgr = config_manager
        self._llm = llm_client
        self._logger = logger or logging.getLogger(__name__)
        self._local_classifier = LocalRegexClassifier(
            rules=self._cfg_mgr.config.layer_1_rules,
            logger=self._logger,
        )

    def run(self, columns: list[ColumnMetadata]) -> list[PipelineResult]:
        results: list[PipelineResult] = []
        for col in columns:
            results.append(self._classify_single_column(col))
        return results

    def _classify_single_column(self, col: ColumnMetadata) -> PipelineResult:
        try:
            self._logger.debug(
                "Processing column: %s.%s.%s",
                col.schema_name,
                col.table_name,
                col.column_name,
            )

            # Filter 0: blacklist
            if self._cfg_mgr.is_blacklisted(col.table_name, col.column_name):
                decision = ClassificationDecision(
                    status="EXCLUDED",
                    category="EXCLUDED",
                    confidence=1.0,
                    decided_by="filter_0",
                    notes="Column matched blacklist rules.",
                )
                return PipelineResult(column=col, decision=decision)

            threshold = self._cfg_mgr.config.confidence_threshold
            sample_size = self._cfg_mgr.config.sample_size

            # Layer 0: metadata/schema match
            layer0_rule = self._cfg_mgr.match_layer0(col.table_name, col.column_name)
            if layer0_rule and layer0_rule.confidence >= threshold:
                decision = ClassificationDecision(
                    status="CLASSIFIED",
                    category=layer0_rule.category,
                    confidence=layer0_rule.confidence,
                    decided_by="layer_0",
                    notes="Matched schema metadata rule.",
                )
                return PipelineResult(column=col, decision=self._apply_security(decision))

            # Empty column check (after Layer 0 fails)
            samples = self._db.sample_column_values(
                schema_name=col.schema_name,
                table_name=col.table_name,
                column_name=col.column_name,
                limit=sample_size,
            )
            non_empty = [
                str(value).strip()
                for value in samples
                if value is not None and str(value).strip() != ""
            ]

            if not non_empty:
                decision = ClassificationDecision(
                    status="EMPTY_COLUMN",
                    category="EMPTY_COLUMN",
                    confidence=1.0,
                    decided_by="empty_check",
                    notes="Sample values are 100% empty or NULL.",
                )
                return PipelineResult(column=col, decision=decision)

            # Layer 1: local regex classifier
            layer1_decision = self._local_classifier.classify(non_empty)
            if layer1_decision.confidence >= threshold:
                return PipelineResult(
                    column=col,
                    decision=self._apply_security(layer1_decision),
                )

            # Layer 2: LLM fallback
            layer2_decision = self._llm.classify(
                domain=self._cfg_mgr.config.domain,
                table_name=col.table_name,
                column_name=col.column_name,
                sample_values=non_empty,
                valid_labels=self._cfg_mgr.config.layer_2.valid_labels,
            )

            final_decision = layer2_decision
            if layer2_decision.category == "UNKNOWN" and layer1_decision.confidence > 0:
                final_decision = layer1_decision
                final_decision.notes = (
                    "LLM returned UNKNOWN; retained best Layer 1 local classification."
                )

            if final_decision.status == "UNCLASSIFIED" and final_decision.category == "UNKNOWN":
                final_decision.notes = final_decision.notes or "No layer met confidence threshold."

            return PipelineResult(column=col, decision=self._apply_security(final_decision))

        except Exception as exc:
            self._logger.exception(
                "Failed to classify column %s.%s.%s",
                col.schema_name,
                col.table_name,
                col.column_name,
            )
            return PipelineResult(
                column=col,
                decision=ClassificationDecision(
                    status="ERROR",
                    category="UNKNOWN",
                    confidence=0.0,
                    decided_by="pipeline",
                    error=str(exc),
                ),
            )

    def _apply_security(self, decision: ClassificationDecision) -> ClassificationDecision:
        masking_method = self._cfg_mgr.masking_for_category(decision.category)
        if masking_method:
            decision.sensitive = True
            decision.masking_method = masking_method
        else:
            decision.sensitive = False
            decision.masking_method = ""
        return decision
