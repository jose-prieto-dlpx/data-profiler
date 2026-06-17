from __future__ import annotations

import argparse
import logging
import sys

from flask import Flask, jsonify, request

from config_loader import ConfigLoader
from database_reader import DatabaseReader

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config/sample_healthcare.yaml"
reader_cache: dict[str, DatabaseReader] = {}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the data reader service.")
    parser.add_argument("port", nargs="?", type=int, default=5001)
    parser.add_argument(
        "--config",
        dest="config_path",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the reader configuration YAML file.",
    )
    return parser.parse_args(argv)


def _resolve_config_path() -> str:
    return str(request.args.get("config_path") or app.config["CONFIG_PATH"])


def _get_db_reader() -> tuple[str, DatabaseReader]:
    config_path = _resolve_config_path()
    reader = reader_cache.get(config_path)
    if reader is None:
        config = ConfigLoader.load(config_path)
        reader = DatabaseReader(config.database, logger=logger)
        reader_cache[config_path] = reader
        logger.info("Data reader initialized for config %s", config_path)
    return config_path, reader


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/schema/<schema_name>", methods=["GET"])
def get_schema(schema_name: str):
    try:
        config_path, db_reader = _get_db_reader()
        columns = db_reader.get_columns(schema_name)
        logger.info(
            "Retrieved %d columns from schema %s using config %s",
            len(columns),
            schema_name,
            config_path,
        )
        return jsonify({"columns": columns}), 200
    except FileNotFoundError as e:
        logger.exception("Reader config file not found")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to get schema %s", schema_name)
        return jsonify({"error": str(e)}), 500


@app.route("/sample/<schema>/<table>/<column>", methods=["GET"])
def get_sample(schema: str, table: str, column: str):
    try:
        config_path, db_reader = _get_db_reader()
        limit = request.args.get("limit", default=20, type=int)
        samples = db_reader.get_samples(schema, table, column, limit)
        logger.info(
            "Retrieved %d samples from %s.%s.%s using config %s",
            len(samples),
            schema,
            table,
            column,
            config_path,
        )
        return jsonify({"samples": samples}), 200
    except FileNotFoundError as e:
        logger.exception("Reader config file not found")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Sample read failed for %s.%s.%s: %s", schema, table, column, str(e))
        # Return 200 with an explicit error payload so classifier can log and continue.
        return jsonify({"samples": [], "error": str(e)}), 200


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    app.config["CONFIG_PATH"] = args.config_path
    logger.info("Starting Data Reader Service on port %d", args.port)
    logger.info("Using default config path %s", args.config_path)
    app.run(host="0.0.0.0", port=args.port, debug=False)
