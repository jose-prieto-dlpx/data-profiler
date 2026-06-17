from __future__ import annotations

import argparse
import logging
import sys

import requests
from flask import Flask, jsonify, request

from config_loader import ConfigLoader
from layer_router import LayerRouter
from models import ClassificationResult, ColumnMetadata

DECIDED_BY_DATA_READER = "Data Reader - Sample Retrieval"

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

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
    return parser.parse_args(argv)


def _resolve_config_path(payload: dict) -> str:
    return str(payload.get("config_path") or app.config["CONFIG_PATH"])


def _get_runtime_dependencies(payload: dict) -> tuple[str, object, LayerRouter, str]:
    config_path = _resolve_config_path(payload)
    config = ConfigLoader.load(config_path)

    router = router_cache.get(config_path)
    if router is None:
        router = LayerRouter(config, logger=logger)
        router_cache[config_path] = router
        logger.info("Data classifier initialized for config %s", config_path)

    return config_path, config, router, config.services.data_reader_url


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/classify", methods=["POST"])
def classify_column():
    try:
        payload = request.get_json() or {}
        schema = payload.get("schema_name", "public")
        table = payload.get("table_name")
        column = payload.get("column_name")
        data_type = payload.get("data_type", "unknown")
        config_path, config, router, data_reader_url = _get_runtime_dependencies(payload)

        if not table or not column:
            return jsonify({"error": "table_name and column_name required"}), 400

        # Fetch samples from data reader
        try:
            resp = requests.get(
                f"{data_reader_url}/sample/{schema}/{table}/{column}",
                params={
                    "limit": config.sample_size,
                    "config_path": config_path,
                },
                timeout=10,
            )
            resp.raise_for_status()
            sample_payload = resp.json() or {}
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
                return jsonify(error_result.to_dict()), 200
            samples = sample_payload.get("samples", [])
        except Exception:
            logger.exception("Failed to fetch samples from data reader")
            samples = []

        # Classify
        col = ColumnMetadata(
            schema_name=schema,
            table_name=table,
            column_name=column,
            data_type=data_type,
        )
        result = router.classify(col, samples)
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
    app.config["CONFIG_PATH"] = args.config_path
    logger.info("Starting Data Classifier Service on port %d", args.port)
    logger.info("Using default config path %s", args.config_path)
    app.run(host="0.0.0.0", port=args.port, debug=False)
