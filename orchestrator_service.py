from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, jsonify, request

from config_loader import ConfigLoader
from logging_setup import create_json_logger
from models import ClassificationResult
from results_exporter import ResultsExporter

app = Flask(__name__)
logger = create_json_logger("orchestrator_service")

DEFAULT_CONFIG_PATH = "config/sample_healthcare.yaml"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the orchestrator service.")
    parser.add_argument("port", nargs="?", type=int, default=5000)
    parser.add_argument(
        "--config",
        dest="config_path",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the orchestrator configuration YAML file.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and Flask debug mode.",
    )
    return parser.parse_args(argv)


def _configure_logger(debug: bool) -> None:
    global logger
    logger = create_json_logger("orchestrator_service", debug=debug)


def _resolve_config_path(payload: dict) -> str:
    config_path = str(payload.get("config_path") or app.config["CONFIG_PATH"])
    logger.debug("Resolved orchestrator config path: %s", config_path)
    return config_path


def _load_runtime_settings(payload: dict):
    config_path = _resolve_config_path(payload)
    logger.debug("Loading orchestrator runtime settings from config %s", config_path)
    config = ConfigLoader.load(config_path)
    return config_path, config, config.services.data_reader_url, config.services.classifiers


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        payload = request.get_json() or {}
        logger.debug("Analyze request payload keys: %s", sorted(payload.keys()))
        schema = payload.get("schema", "public")
        output_file = payload.get("output_file", "classification_output.csv")

        config_path, config, data_reader_url, classifiers = _load_runtime_settings(payload)
        logger.info("Starting analysis for schema %s using config %s", schema, config_path)
        logger.debug("Runtime endpoints: data_reader_url=%s classifiers=%s", data_reader_url, classifiers)

        # Fetch schema metadata from data reader
        try:
            logger.debug("Calling data reader schema endpoint: url=%s schema=%s", data_reader_url, schema)
            resp = requests.get(
                f"{data_reader_url}/schema/{schema}",
                timeout=30,
            )
            logger.debug("Data reader schema response status: %d", resp.status_code)
            resp.raise_for_status()
            columns = resp.json().get("columns", [])
            logger.info("Fetched %d columns from data reader", len(columns))
            logger.debug("First 3 columns preview: %s", columns[:3])
        except Exception as e:
            logger.exception("Failed to fetch schema from data reader")
            return jsonify({"error": f"Data reader error: {e}"}), 500

        if not columns:
            return jsonify({"columns": 0, "classified": 0, "results": []}), 200

        # Classify columns in parallel using thread pool
        results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            logger.debug("Submitting %d columns for parallel classification", len(columns))
            futures = {
                executor.submit(_classify_column, col, classifiers): col
                for col in columns
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(_to_classification_result(result))
                        logger.debug("Classification future completed successfully")
                except Exception as e:
                    col = futures[future]
                    logger.exception("Failed to classify %s.%s", col["table_name"], col["column_name"])

        # Export results
        try:
            logger.debug("Exporting %d classification results to %s", len(results), output_file)
            ResultsExporter.to_file(results, output_file)
            logger.info("Results written to %s", output_file)
        except Exception as e:
            logger.exception("Failed to export results")

        # Build response
        pretty = ResultsExporter.to_pretty_table(results)
        return jsonify({
            "total_columns": len(columns),
            "classified": len(results),
            "output_file": output_file,
            "config_path": config_path,
            "data_reader_url": data_reader_url,
            "classifiers": classifiers,
            "results_preview": pretty,
        }), 200

    except FileNotFoundError as e:
        logger.exception("Config file not found")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Analysis failed")
        return jsonify({"error": str(e)}), 500


def _classify_column(col: dict, classifiers: list[str]) -> dict | None:
    """Call a classifier service to classify a single column."""
    try:
        classifier_url = classifiers[hash((col["table_name"], col["column_name"])) % len(classifiers)]
        logger.debug(
            "Calling classifier endpoint: url=%s table=%s column=%s",
            classifier_url,
            col["table_name"],
            col["column_name"],
        )
        resp = requests.post(
            f"{classifier_url}/classify",
            json=col,
            timeout=30,
        )
        logger.debug("Classifier response status for %s.%s: %d", col["table_name"], col["column_name"], resp.status_code)
        resp.raise_for_status()
        body = resp.json()
        logger.debug("Classifier response keys for %s.%s: %s", col["table_name"], col["column_name"], sorted(body.keys()))
        return body
    except Exception as e:
        logger.exception("Classifier call failed for %s.%s", col["table_name"], col["column_name"])
        return None


def _to_classification_result(result: dict) -> ClassificationResult:
    """Convert classifier JSON response to ClassificationResult model."""
    return ClassificationResult(
        schema_name=str(result.get("schema_name", "")),
        table_name=str(result.get("table_name", "")),
        column_name=str(result.get("column_name", "")),
        data_type=str(result.get("data_type", "unknown")),
        status=str(result.get("status", "UNCLASSIFIED")),
        category=str(result.get("category", "UNKNOWN")),
        confidence=float(result.get("confidence", 0.0)),
        sensitive=bool(result.get("sensitive", False)),
        masking_method=str(result.get("masking_method", "")),
        decided_by=str(result.get("decided_by", "")),
        notes=str(result.get("notes", "")),
        reasoning=str(result.get("reasoning", "")),
        error=str(result.get("error", "")),
    )


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    _configure_logger(args.debug)
    app.config["CONFIG_PATH"] = args.config_path
    logger.info("Starting Orchestrator Service on port %d", args.port)
    logger.info("Using default config path %s", args.config_path)
    logger.info("Debug mode enabled: %s", args.debug)
    app.run(host="0.0.0.0", port=args.port, debug=args.debug, use_reloader=False)
