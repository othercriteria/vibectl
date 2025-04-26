"""
vibectl - A vibes-based alternative to kubectl
"""

__version__ = "0.5.2"

# These imports are needed for the tests to run properly
# by making the modules accessible via vibectl.module_name
import logging

from . import (
    cli,
    command_handler,
    config,
    console,
    memory,
    output_processor,
    prompt,
    utils,
)

# Initialize package-level logger
logger = logging.getLogger("vibectl")
logger.setLevel(logging.INFO)  # Default level, can be overridden by config or CLI
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)

__all__ = [
    "cli",
    "command_handler",
    "config",
    "console",
    "memory",
    "output_processor",
    "prompt",
    "utils",
]
