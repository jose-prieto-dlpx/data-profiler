from __future__ import annotations

import argparse
import logging
import os
import sys

from classification_pipeline import ClassificationPipeline
from config_manager import ConfigManager
from database_postgres import PostgresClient
from export_manager import ExportManager
from llm_clients import create_llm_client


def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def build_dsn(args: argparse.Namespace) -> str:
    if args.dsn:
        return args.dsn

    host = args.host or os.getenv("PGHOST", "localhost")
    port = args.port or os.getenv("PGPORT", "5432")
    dbname = args.dbname or os.getenv("PGDATABASE", "postgres")
    user = args.user or os.getenv("PGUSER", "postgres")
    password = args.password or os.getenv("PGPASSWORD", "")
    sslmode = args.sslmode or os.getenv("PGSSLMODE", "prefer")

    return (
        f"host={host} port={port} dbname={dbname} "
        f"user={user} password={password} sslmode={sslmode}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated data classification and masking pipeline for PostgreSQL."
    )
    parser.add_argument("--config", required=True, help="Path to YAML domain configuration.")
    parser.add_argument("--schema", default="public", help="Schema name to scan.")
    parser.add_argument("--output", default="classification_output.csv", help="Output CSV file path.")

    parser.add_argument("--dsn", default="", help="Full PostgreSQL DSN string.")
    parser.add_argument("--host", default="", help="PostgreSQL host.")
    parser.add_argument("--port", default="", help="PostgreSQL port.")
    parser.add_argument("--dbname", default="", help="PostgreSQL database name.")
    parser.add_argument("--user", default="", help="PostgreSQL username.")
    parser.add_argument("--password", default="", help="PostgreSQL password.")
    parser.add_argument("--sslmode", default="", help="PostgreSQL SSL mode.")

    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(debug=args.debug)
    logger = logging.getLogger("main")

    db_client: PostgresClient | None = None

    try:
        cfg_mgr = ConfigManager.load_from_file(args.config)

        dsn = build_dsn(args)
        db_client = PostgresClient(dsn=dsn, logger=logger)
        db_client.connect()

        columns = db_client.get_columns(args.schema)
        logger.info("Discovered %d columns in schema '%s'.", len(columns), args.schema)

        llm_client = create_llm_client(cfg_mgr.config.layer_2, logger=logger)
        pipeline = ClassificationPipeline(
            db_client=db_client,
            config_manager=cfg_mgr,
            llm_client=llm_client,
            logger=logger,
        )

        results = pipeline.run(columns)

        exporter = ExportManager()
        exporter.write_csv(results, args.output)

        csv_text = exporter.results_to_csv_text(results)
        print(csv_text)

        logger.info("Classification finished. CSV written to '%s'.", args.output)
        return 0

    except Exception:
        logger.exception("Pipeline execution failed.")
        return 1

    finally:
        if db_client is not None:
            try:
                db_client.close()
            except Exception:
                logger.exception("Failed while closing database resources.")


if __name__ == "__main__":
    sys.exit(main())
