"""Logging configuration for rotating file + console output."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging():
    """Configure global logging handlers (idempotent)."""
    logs_dir = Path("Data") / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "monitor.log"

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
