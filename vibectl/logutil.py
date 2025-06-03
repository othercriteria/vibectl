import logging
import os

from .config import Config


class ConsoleManagerHandler(logging.Handler):
    """Custom logging handler to forward WARNING/ERROR logs to console_manager."""

    def emit(self, record: logging.LogRecord) -> None:
        from .console import console_manager

        msg = self.format(record)
        if record.levelno >= logging.ERROR:
            console_manager.print_error(msg)
        elif record.levelno == logging.WARNING:
            console_manager.print_warning(msg)
        # INFO/DEBUG are not shown to user unless in verbose mode (future extension)


# Shared logger instance
logger = logging.getLogger("vibectl")


def not_error(record: logging.LogRecord) -> bool:
    """Filter out ERROR level messages, but allow WARNING and below."""
    return record.levelno < logging.ERROR


def init_logging() -> None:
    """Initialize logging with proper configuration to avoid duplicate output."""
    cfg = Config()
    log_level = os.environ.get("VIBECTL_LOG_LEVEL")
    if not log_level:
        log_level = cfg.get("system.log_level", "INFO")
    level = getattr(logging, str(log_level).upper(), logging.INFO)

    # Clear any existing handlers to prevent duplicates
    logger.handlers.clear()
    logger.setLevel(level)

    # Only add StreamHandler for INFO/DEBUG messages
    # Errors and warnings will be handled by console_manager via handle_exception
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)  # Use the same level as the logger
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    stream_handler.setFormatter(formatter)

    # Add filter to only show INFO/DEBUG through StreamHandler
    stream_handler.addFilter(not_error)
    logger.addHandler(stream_handler)

    logger.debug(f"Logging initialized at level: {log_level}")
