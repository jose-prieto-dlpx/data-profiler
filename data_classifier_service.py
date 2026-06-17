from __future__ import annotations

import argparse
import sys

import requests
from flask import Flask, jsonify, request

from config_loader import ConfigLoader
from layer_router import LayerRouter
from logging_setup import create_json_logger
from models import ClassificationResult, ColumnMetadata

DECIDED_BY_DATA_READER = "Data Reader - Sample Retrieval"

app = Flask(__name__)
logger = create_json_logger("data_classifier_service")

DEFAULT_CONFIG_PATH = "config/sample_healthcare.yaml"

router_cache: dict[str, LayerRouter] = {}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the data classifier service.")
    parser.add_argument("port", nargs="?", type=int, default=5002)
    parser.add_argument(
        "--config",
        dest="config_path",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the classifier configuration YAML file.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and Flask debug mode.",
    )
    return parser.parse_args(argv)


def _configure_logger(debug: bool) -> None:
    global logger
    logger = create_json_logger("data_classifier_service", debug=debug)


def _resolve_config_path(payload: dict) -> str:
    config_path = str(payload.get("config_path") or app.config["CONFIG_PATH"])
    logger.debug("Resolved classifier config path: %s", config_path)
    return config_path


def _get_runtime_dependencies(payload: dict) -> tuple[str, object, LayerRouter, str]:
    config_path = _resolve_config_path(payload)
    logger.debug("Loading classifier runtime dependencies for config %s", config_path)
    config = ConfigLoader.load(config_path)

    router = router_cache.get(config_path)
    if router is None:
        logger.debug("LayerRouter cache miss for config %s; creating router", config_path)
        router = LayerRouter(config, logger=logger)
        router_cache[config_path] = router
        logger.info("Data classifier initialized for config %s", config_path)
    else:
        logger.debug("LayerRouter cache hit for config %s", config_path)

    return config_path, config, router, config.services.data_reader_url


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/classify", methods=["POST"])
def classify_column():
    try:
        payload = request.get_json() or {}
        logger.debug("Classifier request payload keys: %s", sorted(payload.keys()))
        schema = payload.get("schema_name", "public")
        table = payload.get("table_name")
        column = payload.get("column_name")
        data_type = payload.get("data_type", "unknown")
        config_path, config, router, data_reader_url = _get_runtime_dependencies(payload)

        if not table or not column:
            return jsonify({"error": "table_name and column_name required"}), 400

        # Fetch samples from data reader
        try:
            logger.debug(
                "Calling data reader sample endpoint: url=%s schema=%s table=%s column=%s limit=%d config=%s",
                data_reader_url,
                schema,
                table,
                column,
                config.sample_size,
                config_path,
            )
            resp = requests.get(
                f"{data_reader_url}/sample/{schema}/{table}/{column}",
                params={
                    "limit": config.sample_size,
                    "config_path": config_path,
                },
                timeout=10,
            )
            logger.debug("Data reader response status: %d", resp.status_code)
            resp.raise_for_status()
            sample_payload = resp.json() or {}
            logger.debug("Data reader payload keys: %s", sorted(sample_payload.keys()))
            sample_error = sample_payload.get("error")
            if sample_error:
                logger.error(
                    "Data reader reported sample error for %s.%s.%s: %s",
                    schema,
                    table,
                    column,
                    sample_error,
                )
                error_result = ClassificationResult(
                    schema_name=schema,
                    table_name=table,
                    column_name=column,
                    data_type=data_type,
                    status="ERROR",
                    category="UNKNOWN",
                    confidence=0.0,
                    sensitive=False,
                    masking_method="",
                    decided_by=DECIDED_BY_DATA_READER,
                    notes="Column classification skipped due to sample retrieval error.",
                    error=str(sample_error),
                )
                logger.debug("Returning ERROR classification due to data reader sample error")
                return jsonify(error_result.to_dict()), 200
            samples = sample_payload.get("samples", [])
            logger.debug("Received %d samples for %s.%s.%s", len(samples), schema, table, column)
        except Exception:
            logger.exception("Failed to fetch samples from data reader")
            samples = []
            logger.debug("Proceeding with empty samples after data reader fetch failure")

        # Classify
        col = ColumnMetadata(
            schema_name=schema,
            table_name=table,
            column_name=column,
            data_type=data_type,
        )
        result = router.classify(col, samples)
        logger.debug(
            "Router classification result: status=%s category=%s confidence=%.4f decided_by=%s",
            result.status,
            result.category,
            result.confidence,
            result.decided_by,
        )
        logger.info(
            "Classified %s.%s.%s -> %s (confidence=%.4f) using config %s",
            schema,
            table,
            column,
            result.category,
            result.confidence,
            config_path,
        )

        return jsonify(result.to_dict()), 200

    except FileNotFoundError as e:
        logger.exception("Classifier config file not found")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Classification failed")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    _configure_logger(args.debug)
    app.config["CONFIG_PATH"] = args.config_path
    logger.info("Starting Data Classifier Service on port %d", args.port)
    logger.info("Using default config path %s", args.config_path)
    logger.info("Debug mode enabled: %s", args.debug)
    app.run(host="0.0.0.0", port=args.port, debug=args.debug, use_reloader=False)
