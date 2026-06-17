from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Iterator

from config_loader import DatabaseConfig

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    raise ImportError("psycopg2-binary required: pip install psycopg2-binary")


class DatabaseReader:
    def __init__(self, db_config: DatabaseConfig, logger: logging.Logger | None = None):
        self.config = db_config
        self.logger = logger or logging.getLogger(__name__)

    @contextmanager
    def _connection(self) -> Iterator[psycopg2.extensions.connection]:
        conn = psycopg2.connect(self.config.to_dsn())
        try:
            yield conn
        finally:
            conn.close()

    def get_columns(self, schema: str) -> list[dict]:
        """Fetch column metadata from schema."""
        query = """
            SELECT table_schema, table_name, column_name, data_type, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """
        try:
            with self._connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (schema,))
                    return [
                        {
                            "schema_name": r[0],
                            "table_name": r[1],
                            "column_name": r[2],
                            "data_type": r[3],
                        }
                        for r in cur.fetchall()
                    ]
        except Exception as e:
            self.logger.exception("Failed to fetch columns from schema %s", schema)
            raise RuntimeError(f"Schema read failed: {e}") from e

    def get_samples(self, schema: str, table: str, column: str, limit: int) -> list[str | None]:
        """Fetch sample values from column."""
        query = sql.SQL("SELECT {col} FROM {schema}.{table} LIMIT %s").format(
            col=sql.Identifier(column),
            schema=sql.Identifier(schema),
            table=sql.Identifier(table),
        )
        try:
            with self._connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (limit,))
                    return [row[0] for row in cur.fetchall()]
        except Exception as e:
            self.logger.exception(
                "Failed to sample %s.%s.%s",
                schema,
                table,
                column,
            )
            raise RuntimeError(
                f"Failed to sample {schema}.{table}.{column}: {e}"
            ) from e
