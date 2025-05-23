import logging

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

    # Check if a ConsoleManagerHandler is already present or if we need to add one
    # Also, ensure not to add duplicate StreamHandlers if one was added above.
    # This logic can be refined to ensure only one appropriate handler is active.
    has_console_manager_handler = any(
        isinstance(h, ConsoleManagerHandler) for h in logger.handlers
    )

    if not has_console_manager_handler:
        # Add ConsoleManagerHandler if not already present
        # This handler will use the imported console_manager for its output.
        cm_handler = ConsoleManagerHandler()
        cm_handler.setFormatter(
            logging.Formatter("%(message)s")
        )  # User-facing messages typically don't need [LEVELNAME]
        logger.addHandler(cm_handler)

        # Optional: Remove the basic StreamHandler if ConsoleManagerHandler is added
        # to avoid duplicate console output for warnings/errors.
        # This depends on desired behavior for INFO/DEBUG logs.
        # --- DO NOT REMOVE THE DEFAULT STREAM HANDLER ---
        # for h in list(logger.handlers):  # Iterate over a copy
        #     if isinstance(h, logging.StreamHandler) and not isinstance(
        #         h, ConsoleManagerHandler
        #     ):
        #         logger.removeHandler(h)
        #         logger.debug(
        #             "Removed default StreamHandler; ConsoleManagerHandler was added."
        #         )
