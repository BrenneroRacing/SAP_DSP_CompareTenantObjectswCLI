"""Logging helpers for Datasphere comparison runs.

Provides centralized logger configuration for console output and
per-run file logging.
"""

import logging
import sys
from pathlib import Path


def configure_logging(logger: logging.Logger, log_file: Path) -> None:
    """Configure console and log file handlers for a single run."""

    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
