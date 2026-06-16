from __future__ import annotations

import logging
import re

from config_manager import Layer1Rule
from models import ClassificationDecision


class LocalRegexClassifier:
    def __init__(self, rules: list[Layer1Rule], logger: logging.Logger | None = None) -> None:
        self._rules = rules
        self._logger = logger or logging.getLogger(__name__)

    def classify(self, values: list[str]) -> ClassificationDecision:
        if not values:
            return ClassificationDecision(
                status="UNCLASSIFIED",
                category="UNKNOWN",
                confidence=0.0,
                decided_by="layer_1",
                notes="No non-empty sample values available for local classification.",
            )

        best_category = "UNKNOWN"
        best_score = 0.0
        best_rule: Layer1Rule | None = None

        for rule in self._rules:
            try:
                matches = sum(
                    1
                    for value in values
                    if re.search(rule.regex, value, flags=re.IGNORECASE) is not None
                )
            except re.error:
                self._logger.warning("Skipping invalid regex in layer_1_rules: %s", rule.regex)
                continue

            ratio = matches / len(values)
            score = min(1.0, rule.confidence * ratio)
            if score > best_score:
                best_score = score
                best_category = rule.category
                best_rule = rule

        notes = "No rule matched."
        if best_rule is not None:
            notes = f"Best regex rule '{best_rule.regex}' score={best_score:.4f}."

        return ClassificationDecision(
            status="CLASSIFIED" if best_score > 0 else "UNCLASSIFIED",
            category=best_category,
            confidence=best_score,
            decided_by="layer_1",
            notes=notes,
        )
