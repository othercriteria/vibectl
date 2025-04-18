import logging

from .config import Config
from .console import console_manager


class ConsoleManagerHandler(logging.Handler):
    """Custom logging handler to forward WARNING/ERROR logs to console_manager."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        if record.levelno >= logging.ERROR:
            console_manager.print_error(msg)
        elif record.levelno == logging.WARNING:
            console_manager.print_warning(msg)
        # INFO/DEBUG are not shown to user unless in verbose mode (future extension)


# Shared logger instance
logger = logging.getLogger("vibectl")
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Logging initialization function


def init_logging() -> None:
    import os

    cfg = Config()
    log_level = os.environ.get("VIBECTL_LOG_LEVEL")
    if not log_level:
        log_level = getattr(cfg, "get", lambda k, d=None: None)("log_level", "INFO")
    level = getattr(logging, str(log_level).upper(), logging.INFO)
    logger.setLevel(level)
    logger.debug(f"Logging initialized at level: {log_level}")
    # Attach custom handler for user-facing logs
    if not any(isinstance(h, ConsoleManagerHandler) for h in logger.handlers):
        handler = ConsoleManagerHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
