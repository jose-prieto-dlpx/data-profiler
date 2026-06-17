from __future__ import annotations

import argparse
import logging
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated data classification and masking pipeline for PostgreSQL."
    )
    parser.add_argument("--config", required=True, help="Path to YAML domain configuration.")
    parser.add_argument("--schema", default="public", help="Schema name to scan.")
    parser.add_argument("--output", default="classification_output.csv", help="Output CSV file path.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(debug=args.debug)
    logger = logging.getLogger("main")

    db_client: PostgresClient | None = None

    try:
        cfg_mgr = ConfigManager.load_from_file(args.config)

        db_client = PostgresClient(dsn=cfg_mgr.config.database.to_dsn())

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

        pretty_text = exporter.results_to_pretty_text(results)
        print(pretty_text)

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
