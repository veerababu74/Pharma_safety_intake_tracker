"""Centralized structured logging."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog

from app.core.config import BACKEND_ROOT, get_settings


def setup_logging() -> None:
    settings = get_settings()
    log_file = BACKEND_ROOT / "logs" / "app.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG if settings.app_env == "development" else logging.INFO,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app"):
    return structlog.get_logger(name)
