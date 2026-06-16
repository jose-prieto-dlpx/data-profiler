from __future__ import annotations

from abc import ABC, abstractmethod

from models import ColumnMetadata


class DatabaseClient(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Initialize the database connection resources."""

    @abstractmethod
    def close(self) -> None:
        """Release all database connection resources."""

    @abstractmethod
    def get_columns(self, schema_name: str) -> list[ColumnMetadata]:
        """Return all columns for a given schema."""

    @abstractmethod
    def sample_column_values(
        self,
        schema_name: str,
        table_name: str,
        column_name: str,
        limit: int,
    ) -> list[str | None]:
        """Return up to limit values from the target column."""
