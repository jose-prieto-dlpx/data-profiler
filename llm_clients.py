from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any
from urllib import request

from config_manager import Layer2Config
from models import ClassificationDecision


class LLMClient(ABC):
    @abstractmethod
    def classify(
        self,
        domain: str,
        table_name: str,
        column_name: str,
        sample_values: list[str],
        valid_labels: list[str],
    ) -> ClassificationDecision:
        """Classify sampled values with LLM and return category + confidence."""


class NoOpLLMClient(LLMClient):
    def classify(
        self,
        domain: str,
        table_name: str,
        column_name: str,
        sample_values: list[str],
        valid_labels: list[str],
    ) -> ClassificationDecision:
        return ClassificationDecision(
            status="UNCLASSIFIED",
            category="UNKNOWN",
            confidence=0.0,
            decided_by="layer_2",
            notes="LLM provider disabled.",
        )


class OpenAILLMClient(LLMClient):
    def __init__(self, cfg: Layer2Config, logger: logging.Logger | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("openai package is required for provider=openai") from exc

        self._cfg = cfg
        self._logger = logger or logging.getLogger(__name__)
        self._client = OpenAI()

    def classify(
        self,
        domain: str,
        table_name: str,
        column_name: str,
        sample_values: list[str],
        valid_labels: list[str],
    ) -> ClassificationDecision:
        system_prompt, user_prompt = _build_prompts(
            cfg=self._cfg,
            domain=domain,
            table_name=table_name,
            column_name=column_name,
            sample_values=sample_values,
            valid_labels=valid_labels,
        )

        try:
            response = self._client.chat.completions.create(
                model=self._cfg.model,
                temperature=self._cfg.temperature,
                max_tokens=self._cfg.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=self._cfg.timeout_seconds,
            )
            content = response.choices[0].message.content or ""
            payload = _safe_parse_json(content)
            return _decision_from_payload(payload, valid_labels)
        except Exception as exc:
            self._logger.exception("OpenAI classification failed for %s.%s", table_name, column_name)
            return ClassificationDecision(
                status="ERROR",
                category="UNKNOWN",
                confidence=0.0,
                decided_by="layer_2",
                error=str(exc),
            )


class OllamaLLMClient(LLMClient):
    def __init__(self, cfg: Layer2Config, logger: logging.Logger | None = None) -> None:
        self._cfg = cfg
        self._logger = logger or logging.getLogger(__name__)

    def classify(
        self,
        domain: str,
        table_name: str,
        column_name: str,
        sample_values: list[str],
        valid_labels: list[str],
    ) -> ClassificationDecision:
        system_prompt, user_prompt = _build_prompts(
            cfg=self._cfg,
            domain=domain,
            table_name=table_name,
            column_name=column_name,
            sample_values=sample_values,
            valid_labels=valid_labels,
        )

        payload = {
            "model": self._cfg.model,
            "stream": False,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "options": {
                "temperature": self._cfg.temperature,
            },
        }

        req = request.Request(
            url="http://localhost:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._cfg.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
            body_payload = json.loads(body)
            text = str(body_payload.get("response", ""))
            parsed = _safe_parse_json(text)
            return _decision_from_payload(parsed, valid_labels)
        except Exception as exc:
            self._logger.exception("Ollama classification failed for %s.%s", table_name, column_name)
            return ClassificationDecision(
                status="ERROR",
                category="UNKNOWN",
                confidence=0.0,
                decided_by="layer_2",
                error=str(exc),
            )


def create_llm_client(cfg: Layer2Config, logger: logging.Logger | None = None) -> LLMClient:
    provider = cfg.provider.lower().strip()
    if provider == "openai":
        return OpenAILLMClient(cfg=cfg, logger=logger)
    if provider == "ollama":
        return OllamaLLMClient(cfg=cfg, logger=logger)
    return NoOpLLMClient()


def _build_prompts(
    cfg: Layer2Config,
    domain: str,
    table_name: str,
    column_name: str,
    sample_values: list[str],
    valid_labels: list[str],
) -> tuple[str, str]:
    labels = valid_labels or cfg.valid_labels
    labels_text = ", ".join(labels)
    system_prompt = cfg.system_prompt_template.format(
        domain=domain,
        valid_labels=labels_text,
    )

    clipped_samples = sample_values[:20]
    user_prompt = (
        "Classify this database column. Return JSON ONLY with keys "
        "category (string) and confidence (float in [0,1]).\n"
        f"table: {table_name}\n"
        f"column: {column_name}\n"
        f"samples: {json.dumps(clipped_samples, ensure_ascii=True)}\n"
        f"valid_labels: {json.dumps(labels, ensure_ascii=True)}"
    )
    return system_prompt, user_prompt


def _safe_parse_json(text: str) -> dict[str, Any]:
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_]*\\n", "", stripped)
        stripped = stripped.replace("```", "")

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _decision_from_payload(
    payload: dict[str, Any],
    valid_labels: list[str],
) -> ClassificationDecision:
    raw_category = str(payload.get("category", "UNKNOWN")).upper()
    confidence = payload.get("confidence", 0.0)

    try:
        score = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        score = 0.0

    if valid_labels and raw_category not in [label.upper() for label in valid_labels]:
        return ClassificationDecision(
            status="UNCLASSIFIED",
            category="UNKNOWN",
            confidence=0.0,
            decided_by="layer_2",
            notes=f"LLM returned category '{raw_category}' not in closed label list.",
        )

    return ClassificationDecision(
        status="CLASSIFIED" if raw_category != "UNKNOWN" else "UNCLASSIFIED",
        category=raw_category,
        confidence=score,
        decided_by="layer_2",
    )
