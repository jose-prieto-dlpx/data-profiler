from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BlacklistConfig:
    tables: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)
    table_columns: set[tuple[str, str]] = field(default_factory=set)


@dataclass(frozen=True)
class Layer0Rule:
    category: str
    confidence: float
    table_name: str | None = None
    column_name: str | None = None
    table_regex: str | None = None
    column_regex: str | None = None

    def matches(self, table_name: str, column_name: str) -> bool:
        table_ok = False
        col_ok = False

        if self.table_name is not None:
            table_ok = self.table_name.lower() == table_name.lower()
        elif self.table_regex is not None:
            table_ok = re.search(self.table_regex, table_name, flags=re.IGNORECASE) is not None

        if self.column_name is not None:
            col_ok = self.column_name.lower() == column_name.lower()
        elif self.column_regex is not None:
            col_ok = re.search(self.column_regex, column_name, flags=re.IGNORECASE) is not None

        return table_ok and col_ok


@dataclass(frozen=True)
class Layer1Rule:
    category: str
    regex: str
    confidence: float


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    dbname: str = "postgres"
    user: str = "postgres"
    password: str = ""
    sslmode: str = "prefer"

    def to_dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password} sslmode={self.sslmode}"
        )


@dataclass(frozen=True)
class Layer2Config:
    provider: str = "none"
    model: str = ""
    temperature: float = 0.0
    timeout_seconds: int = 30
    max_tokens: int = 256
    system_prompt_template: str = (
        "You are classifying database columns for domain {domain}. "
        "Allowed labels: {valid_labels}. Return JSON only."
    )
    valid_labels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineConfig:
    domain: str
    confidence_threshold: float
    sample_size: int
    blacklist: BlacklistConfig
    layer_0_rules: list[Layer0Rule]
    layer_1_rules: list[Layer1Rule]
    layer_2: Layer2Config
    security_masking: dict[str, str]
    database: DatabaseConfig


class ConfigManager:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    @classmethod
    def load_from_file(cls, file_path: str | Path) -> "ConfigManager":
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        cfg = PipelineConfig(
            domain=raw.get("domain", "generic"),
            confidence_threshold=float(raw.get("confidence_threshold", 0.8)),
            sample_size=int(raw.get("sample_size", 20)),
            blacklist=_parse_blacklist(raw.get("blacklist", {})),
            layer_0_rules=_parse_layer0(raw.get("layer_0_rules", [])),
            layer_1_rules=_parse_layer1(raw.get("layer_1_rules", [])),
            layer_2=_parse_layer2(raw.get("layer_2_rules", {})),
            security_masking={
                str(k).upper(): str(v).upper()
                for k, v in (raw.get("security_masking", {}) or {}).items()
            },
            database=_parse_database(raw.get("database", {})),
        )
        return cls(cfg)

    def is_blacklisted(self, table_name: str, column_name: str) -> bool:
        if table_name.lower() in self.config.blacklist.tables:
            return True
        if column_name.lower() in self.config.blacklist.columns:
            return True
        return (table_name.lower(), column_name.lower()) in self.config.blacklist.table_columns

    def match_layer0(self, table_name: str, column_name: str) -> Layer0Rule | None:
        for rule in self.config.layer_0_rules:
            if rule.matches(table_name, column_name):
                return rule
        return None

    def masking_for_category(self, category: str) -> str:
        return self.config.security_masking.get(category.upper(), "")


def _parse_blacklist(raw: dict) -> BlacklistConfig:
    tables = {str(t).lower() for t in raw.get("tables", [])}
    columns = {str(c).lower() for c in raw.get("columns", [])}

    table_columns: set[tuple[str, str]] = set()
    for item in raw.get("table_columns", []):
        if isinstance(item, dict):
            t = str(item.get("table", "")).lower()
            c = str(item.get("column", "")).lower()
            if t and c:
                table_columns.add((t, c))

    return BlacklistConfig(tables=tables, columns=columns, table_columns=table_columns)


def _parse_layer0(raw: list[dict]) -> list[Layer0Rule]:
    parsed: list[Layer0Rule] = []
    for item in raw:
        parsed.append(
            Layer0Rule(
                category=str(item.get("category", "UNKNOWN")).upper(),
                confidence=float(item.get("confidence", 0.0)),
                table_name=item.get("table_name"),
                column_name=item.get("column_name"),
                table_regex=item.get("table_regex"),
                column_regex=item.get("column_regex"),
            )
        )
    return parsed


def _parse_layer1(raw: list[dict]) -> list[Layer1Rule]:
    parsed: list[Layer1Rule] = []
    for item in raw:
        parsed.append(
            Layer1Rule(
                category=str(item.get("category", "UNKNOWN")).upper(),
                regex=str(item.get("regex", ".*")),
                confidence=float(item.get("confidence", 0.0)),
            )
        )
    return parsed


def _parse_layer2(raw: dict) -> Layer2Config:
    labels = [str(v).upper() for v in raw.get("valid_labels", [])]
    return Layer2Config(
        provider=str(raw.get("provider", "none")).lower(),
        model=str(raw.get("model", "")),
        temperature=float(raw.get("temperature", 0.0)),
        timeout_seconds=int(raw.get("timeout_seconds", 30)),
        max_tokens=int(raw.get("max_tokens", 256)),
        system_prompt_template=str(
            raw.get(
                "system_prompt_template",
                Layer2Config.system_prompt_template,
            )
        ),
        valid_labels=labels,
    )


def _parse_database(raw: dict) -> DatabaseConfig:
    return DatabaseConfig(
        host=raw.get("host") or os.getenv("PGHOST", "localhost"),
        port=int(raw.get("port") or os.getenv("PGPORT", 5432)),
        dbname=raw.get("dbname") or os.getenv("PGDATABASE", "postgres"),
        user=raw.get("user") or os.getenv("PGUSER", "postgres"),
        password=raw.get("password") or os.getenv("PGPASSWORD", ""),
        sslmode=raw.get("sslmode") or os.getenv("PGSSLMODE", "prefer"),
    )
