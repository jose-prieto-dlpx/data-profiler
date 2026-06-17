from __future__ import annotations

import argparse
import sys

from flask import Flask, jsonify, request

from config_loader import ConfigLoader
from database_reader import DatabaseReader
from logging_setup import create_json_logger

app = Flask(__name__)
logger = create_json_logger("data_reader_service")

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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and Flask debug mode.",
    )
    return parser.parse_args(argv)


def _configure_logger(debug: bool) -> None:
    global logger
    logger = create_json_logger("data_reader_service", debug=debug)


def _resolve_config_path() -> str:
    config_path = str(request.args.get("config_path") or app.config["CONFIG_PATH"])
    logger.debug("Resolved config path for request: %s", config_path)
    return config_path


def _get_db_reader() -> tuple[str, DatabaseReader]:
    config_path = _resolve_config_path()
    reader = reader_cache.get(config_path)
    if reader is None:
        logger.debug("DatabaseReader cache miss for config %s; loading configuration", config_path)
        config = ConfigLoader.load(config_path)
        reader = DatabaseReader(config.database, logger=logger)
        reader_cache[config_path] = reader
        logger.info("Data reader initialized for config %s", config_path)
    else:
        logger.debug("DatabaseReader cache hit for config %s", config_path)
    return config_path, reader


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/schema/<schema_name>", methods=["GET"])
def get_schema(schema_name: str):
    try:
        logger.debug("Schema request received: schema=%s", schema_name)
        config_path, db_reader = _get_db_reader()
        logger.debug("Fetching schema metadata from database: schema=%s, config=%s", schema_name, config_path)
        columns = db_reader.get_columns(schema_name)
        logger.info(
            "Retrieved %d columns from schema %s using config %s",
            len(columns),
            schema_name,
            config_path,
        )
        logger.debug("Schema response prepared with %d columns", len(columns))
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
        logger.debug("Sample request received: %s.%s.%s", schema, table, column)
        config_path, db_reader = _get_db_reader()
        limit = request.args.get("limit", default=20, type=int)
        logger.debug(
            "Fetching samples from database: %s.%s.%s limit=%d config=%s",
            schema,
            table,
            column,
            limit,
            config_path,
        )
        samples = db_reader.get_samples(schema, table, column, limit)
        logger.info(
            "Retrieved %d samples from %s.%s.%s using config %s",
            len(samples),
            schema,
            table,
            column,
            config_path,
        )
        logger.debug("Sample response prepared with %d values", len(samples))
        return jsonify({"samples": samples}), 200
    except FileNotFoundError as e:
        logger.exception("Reader config file not found")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Sample read failed for %s.%s.%s: %s", schema, table, column, str(e))
        # Return 200 with an explicit error payload so classifier can log and continue.
        logger.debug("Returning sample error contract payload for %s.%s.%s", schema, table, column)
        return jsonify({"samples": [], "error": str(e)}), 200


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    _configure_logger(args.debug)
    app.config["CONFIG_PATH"] = args.config_path
    logger.info("Starting Data Reader Service on port %d", args.port)
    logger.info("Using default config path %s", args.config_path)
    logger.info("Debug mode enabled: %s", args.debug)
    app.run(host="0.0.0.0", port=args.port, debug=args.debug, use_reloader=False)
