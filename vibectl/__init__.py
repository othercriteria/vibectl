"""
vibectl - A vibes-based alternative to kubectl
"""

__version__ = "0.3.1"

# These imports are needed for the tests to run properly
# by making the modules accessible via vibectl.module_name
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
