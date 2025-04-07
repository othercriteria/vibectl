"""
vibectl - A vibes-based alternative to kubectl
"""

__version__ = "0.1.0"

# These imports are needed for the tests to run properly
# by making the modules accessible via vibectl.module_name
from . import cli
from . import command_handler
from . import config
from . import console
from . import output_processor
from . import prompt
from . import utils

__all__ = [
    "cli",
    "command_handler",
    "config",
    "console",
    "output_processor",
    "prompt",
    "utils",
]
