from __future__ import annotations

import logging
import sys
from pathlib import Path


def _ensure_delphix_path() -> None:
    wheel_path = (
        Path(__file__).resolve().parent
        / "packages"
        / "delphix_ps_utilities-3-py3-none-any.whl"
    )
    if wheel_path.exists() and str(wheel_path) not in sys.path:
        sys.path.insert(0, str(wheel_path))


def _create_with_config_and_log_utilities(service_name: str, debug: bool) -> logging.Logger | None:
    try:
        from delphix_ps_utilities.config_and_log_utilities import ConfigAndLogUtilities
    except ModuleNotFoundError:
        return None

    utility = ConfigAndLogUtilities(
        {
            "debug_mode": debug,
            "log_mode": "console",
            "log_format_specification": {
                "format_type": "json",
                "timestamp_format": "%Y-%m-%dT%H:%M:%SZ",
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
                "module": "module",
                "lineno": "line",
                "message": "message",
            },
            "log_setup": {
                "logger_name_prefix": service_name,
            },
        }
    )
    _, logger, _ = utility.create_logger(
        log_mode="console",
        log_setup={"logger_name_prefix": service_name},
    )
    # PowerShell wraps stderr from native commands as error records ("python : ...").
    # Route console logger handlers to stdout so JSON logs remain clean.
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.stream = sys.stdout
    logger.propagate = False
    return logger


def _create_with_log_manager(service_name: str, debug: bool) -> logging.Logger:
    from delphix_ps_utilities.log_manager.log_config import LogConfig

    config = LogConfig(
        debug=debug,
        log_mode="console",
        log_format_specification={
            "format_type": "json",
            "timestamp_format": "%Y-%m-%dT%H:%M:%SZ",
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger",
            "module": "module",
            "lineno": "line",
            "message": "message",
        },
        log_setup={"logger_name_prefix": service_name},
    )
    logger, _ = config.setup_logging()
    # PowerShell wraps stderr from native commands as error records ("python : ...").
    # Route console logger handlers to stdout so JSON logs remain clean.
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.stream = sys.stdout
    logger.propagate = False
    return logger


def create_json_logger(service_name: str, debug: bool = False) -> logging.Logger:
    """Create a JSON logger using delphix_ps_utilities logging components."""
    _ensure_delphix_path()

    logger = _create_with_config_and_log_utilities(service_name, debug)
    if logger is not None:
        return logger

    return _create_with_log_manager(service_name, debug)
