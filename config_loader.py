from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


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
class Layer0Rule:
    category: str
    confidence: float
    table_name: str | None = None
    column_name: str | None = None
    table_regex: str | None = None
    column_regex: str | None = None

    def matches(self, table_name: str, column_name: str) -> bool:
        table_ok = (
            self.table_name and self.table_name.lower() == table_name.lower()
        ) or (
            self.table_regex and re.search(self.table_regex, table_name, re.IGNORECASE)
        )
        col_ok = (
            self.column_name and self.column_name.lower() == column_name.lower()
        ) or (
            self.column_regex and re.search(self.column_regex, column_name, re.IGNORECASE)
        )
        return table_ok and col_ok


@dataclass(frozen=True)
class Layer1Rule:
    category: str
    regex: str
    confidence: float


@dataclass(frozen=True)
class Layer2Config:
    provider: str = "none"
    model: str = ""
    country: str = ""
    url: str = "http://localhost:11434/api/generate"
    temperature: float = 0.0
    timeout_seconds: int = 30
    max_tokens: int = 256
    system_prompt_template: str = (
        "You are classifying database columns for domain {domain}. "
        "Allowed labels: {valid_labels}. Return JSON only."
    )
    valid_labels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ServiceConfig:
    data_reader_url: str = "http://localhost:5001"
    classifiers: list[str] = field(default_factory=lambda: ["http://localhost:5002"])


@dataclass(frozen=True)
class ConfigData:
    domain: str
    confidence_threshold: float
    sample_size: int
    blacklist_tables: set[str]
    blacklist_columns: set[str]
    blacklist_pairs: set[tuple[str, str]]
    layer_0_rules: list[Layer0Rule]
    layer_1_rules: list[Layer1Rule]
    layer_2: Layer2Config
    security_masking: dict[str, str]
    database: DatabaseConfig
    services: ServiceConfig


class ConfigLoader:
    @staticmethod
    def load(file_path: str | Path) -> ConfigData:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        blacklist = raw.get("blacklist", {})
        blacklist_tables = {str(t).lower() for t in blacklist.get("tables", [])}
        blacklist_columns = {str(c).lower() for c in blacklist.get("columns", [])}
        blacklist_pairs = {
            (str(item.get("table", "")).lower(), str(item.get("column", "")).lower())
            for item in blacklist.get("table_columns", [])
            if item.get("table") and item.get("column")
        }

        layer_0 = [
            Layer0Rule(
                category=str(r.get("category", "UNKNOWN")).upper(),
                confidence=float(r.get("confidence", 0.0)),
                table_name=r.get("table_name"),
                column_name=r.get("column_name"),
                table_regex=r.get("table_regex"),
                column_regex=r.get("column_regex"),
            )
            for r in raw.get("layer_0_rules", [])
        ]

        layer_1 = [
            Layer1Rule(
                category=str(r.get("category", "UNKNOWN")).upper(),
                regex=str(r.get("regex", ".*")),
                confidence=float(r.get("confidence", 0.0)),
            )
            for r in raw.get("layer_1_rules", [])
        ]

        layer_2_raw = raw.get("layer_2_rules", {})
        layer_2 = Layer2Config(
            provider=str(layer_2_raw.get("provider", "none")).lower(),
            model=str(layer_2_raw.get("model", "")),
            country=str(layer_2_raw.get("country", raw.get("country", ""))),
            url=str(layer_2_raw.get("url", "http://localhost:11434/api/generate")),
            temperature=float(layer_2_raw.get("temperature", 0.0)),
            timeout_seconds=int(layer_2_raw.get("timeout_seconds", 30)),
            max_tokens=int(layer_2_raw.get("max_tokens", 256)),
            system_prompt_template=str(
                layer_2_raw.get(
                    "system_prompt_template",
                    Layer2Config.system_prompt_template,
                )
            ),
            valid_labels=[str(v).upper() for v in layer_2_raw.get("valid_labels", [])],
        )

        database = DatabaseConfig(
            host=raw.get("database", {}).get("host") or os.getenv("PGHOST", "localhost"),
            port=int(raw.get("database", {}).get("port") or os.getenv("PGPORT", 5432)),
            dbname=raw.get("database", {}).get("dbname") or os.getenv("PGDATABASE", "postgres"),
            user=raw.get("database", {}).get("user") or os.getenv("PGUSER", "postgres"),
            password=raw.get("database", {}).get("password") or os.getenv("PGPASSWORD", ""),
            sslmode=raw.get("database", {}).get("sslmode") or os.getenv("PGSSLMODE", "prefer"),
        )

        services_raw = raw.get("services", {})
        services = ServiceConfig(
            data_reader_url=str(services_raw.get("data_reader_url", "http://localhost:5001")),
            classifiers=[
                str(url)
                for url in services_raw.get("classifiers", ["http://localhost:5002"])
                if str(url).strip()
            ] or ["http://localhost:5002"],
        )

        return ConfigData(
            domain=raw.get("domain", "generic"),
            confidence_threshold=float(raw.get("confidence_threshold", 0.8)),
            sample_size=int(raw.get("sample_size", 20)),
            blacklist_tables=blacklist_tables,
            blacklist_columns=blacklist_columns,
            blacklist_pairs=blacklist_pairs,
            layer_0_rules=layer_0,
            layer_1_rules=layer_1,
            layer_2=layer_2,
            security_masking={
                str(k).upper(): str(v).upper()
                for k, v in (raw.get("security_masking", {}) or {}).items()
            },
            database=database,
            services=services,
        )

    @staticmethod
    def is_blacklisted(config: ConfigData, table: str, column: str) -> bool:
        return (
            table.lower() in config.blacklist_tables
            or column.lower() in config.blacklist_columns
            or (table.lower(), column.lower()) in config.blacklist_pairs
        )

    @staticmethod
    def match_layer0(config: ConfigData, table: str, column: str) -> Layer0Rule | None:
        for rule in config.layer_0_rules:
            if rule.matches(table, column):
                return rule
        return None

    @staticmethod
    def masking_for_category(config: ConfigData, category: str) -> str:
        return config.security_masking.get(category.upper(), "")
