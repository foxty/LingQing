"""Shared logging configuration for agents, api, and agent-ui.

This module provides a centralized logging setup that can be used across
all components of the application.

Usage:
        from apps.shared.utils.logger import get_logger

        logger = get_logger(__name__)
        logger.info("This is an info message")
        logger.error("This is an error message")

        # With context
        logger = get_logger(__name__, context="user_id=123")
        logger.info("This is an info message with context")
"""

import logging
import sys
from typing import Any, MutableMapping

# Log format: timestamp - level - [file:line] - context - message
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] %(message)s"
LOG_FORMAT_W_CONTEXT = "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d][%(context)s] %(message)s"

# Initialize flag to prevent duplicate setup
_initialized = False


class ContextFormatter(logging.Formatter):
    """Custom formatter that conditionally selects format based on context."""

    def __init__(self, fmt: str, fmt_with_context: str, *args: Any, **kwargs: Any) -> None:
        """Initialize with two format strings."""
        super().__init__(fmt, *args, **kwargs)
        self._fmt_with_context = fmt_with_context
        self._fmt_without_context = fmt

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record, selecting format based on context presence."""
        has_context = hasattr(record, "context") and record.context

        if has_context:
            self._style._fmt = self._fmt_with_context
        else:
            self._style._fmt = self._fmt_without_context
            record.context = ""

        return super().format(record)


def _setup_logging() -> None:
    """Initialize logging configuration once."""
    global _initialized

    if _initialized:
        return

    # Import here to avoid circular dependency
    from apps.config import EnvConfig

    # Get log level from config or environment or default to INFO
    level = EnvConfig.LOG_LEVEL
    log_level = getattr(logging, level, logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler with formatted output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ContextFormatter(LOG_FORMAT, LOG_FORMAT_W_CONTEXT))
    root_logger.addHandler(console_handler)

    _configure_uvicorn_loggers(console_handler)

    # Keep app logs at LOG_LEVEL while reducing verbose third-party request chatter.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    _initialized = True


def _configure_uvicorn_loggers(console_handler: logging.Handler) -> None:
    """Route uvicorn loggers through the shared formatter."""
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.addHandler(console_handler)
        uv_logger.propagate = False


class ContextLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds contextual information to log records."""

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[str, MutableMapping[str, Any]]:
        """Process the logging message and keyword arguments."""
        context = self.extra.get("context", "") if self.extra else ""
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"]["context"] = context
        return msg, kwargs


def get_logger(name: str, context: str | None = None) -> logging.Logger | logging.LoggerAdapter:
    """Get a logger with the given name and optional context.

    Args:
        name: The name of the logger (typically __name__)
        context: Optional context string to include in all log messages

    Returns:
        A Logger or LoggerAdapter that includes contextual information in log messages
    """
    _setup_logging()
    logger = logging.getLogger(name)
    if context:
        return ContextLoggerAdapter(logger, {"context": context})
    return logger
