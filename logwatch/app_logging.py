"""Zentrales Logging der App selbst (eigene Logdatei zur Fehlernachverfolgung)."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from .config import get_app_log_path

_LOGGER_NAME = "logwatch"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(level)

    try:
        path = get_app_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    except OSError:
        pass

    # Zusätzlich auf die Konsole (im Script-Modus hilfreich)
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(stream)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
