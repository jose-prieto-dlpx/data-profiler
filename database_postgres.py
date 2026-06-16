from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from database_generic import DatabaseClient
from models import ColumnMetadata

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.pool import ThreadedConnectionPool
except ImportError as exc:
    raise ImportError(
        "psycopg2 is required for Postgres support. Install with 'pip install psycopg2-binary'."
    ) from exc


class PostgresClient(DatabaseClient):
    def __init__(
        self,
        dsn: str,
        minconn: int = 1,
        maxconn: int = 5,
        logger: logging.Logger | None = None,
    ) -> None:
        self._dsn = dsn
        self._minconn = minconn
        self._maxconn = maxconn
        self._pool: ThreadedConnectionPool | None = None
        self._logger = logger or logging.getLogger(__name__)

    def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = ThreadedConnectionPool(self._minconn, self._maxconn, self._dsn)
        self._logger.debug("Postgres connection pool initialized.")

    def close(self) -> None:
        if self._pool is not None:
            self._pool.closeall()
            self._logger.debug("Postgres connection pool closed.")
            self._pool = None

    @contextmanager
    def _session(self) -> Iterator[psycopg2.extensions.connection]:
        if self._pool is None:
            raise RuntimeError("Postgres pool is not initialized. Call connect() first.")

        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)

    def get_columns(self, schema_name: str) -> list[ColumnMetadata]:
        query = """
            SELECT
                table_schema,
                table_name,
                column_name,
                data_type,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """

        rows: list[tuple[str, str, str, str, int]] = []
        try:
            with self._session() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (schema_name,))
                    rows = cur.fetchall()
        except Exception as exc:
            self._logger.exception("Failed to fetch schema metadata for schema=%s", schema_name)
            raise RuntimeError(f"Could not read schema metadata: {exc}") from exc

        return [
            ColumnMetadata(
                schema_name=r[0],
                table_name=r[1],
                column_name=r[2],
                data_type=r[3],
                ordinal_position=r[4],
            )
            for r in rows
        ]

    def sample_column_values(
        self,
        schema_name: str,
        table_name: str,
        column_name: str,
        limit: int,
    ) -> list[str | None]:
        query = sql.SQL("SELECT {col} FROM {schema}.{table} LIMIT %s").format(
            col=sql.Identifier(column_name),
            schema=sql.Identifier(schema_name),
            table=sql.Identifier(table_name),
        )

        try:
            with self._session() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (limit,))
                    rows = cur.fetchall()
                    return [row[0] for row in rows]
        except Exception:
            self._logger.exception(
                "Failed to sample values for %s.%s.%s",
                schema_name,
                table_name,
                column_name,
            )
            return []
