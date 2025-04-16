"""
Type definitions for vibectl.

Contains common type definitions used across the application.
"""

from dataclasses import dataclass
from typing import Any, Union


@dataclass
class OutputFlags:
    """Configuration for output display flags."""

    show_raw: bool
    show_vibe: bool
    warn_no_output: bool
    model_name: str
    show_kubectl: bool = False  # Flag to control showing kubectl commands
    warn_no_proxy: bool = (
        True  # Flag to control warnings about missing proxy configuration
    )

# Structured result types for subcommands
@dataclass
class Success:
    message: str = ""
    data: Any | None = None

@dataclass
class Error:
    error: str
    exception: Exception | None = None

Result = Union[Success, Error]

def handle_result(result: Result) -> None:
    """
    Handle a Result (Success or Error): print errors and exit with the correct code.
    Use in CLI handlers to reduce boilerplate.
    """
    import sys

    from vibectl.console import console_manager
    if isinstance(result, Success):
        sys.exit(0)
    elif isinstance(result, Error):
        if result.error:
            console_manager.print_error(result.error)
        sys.exit(1)

def ResultType() -> Success | Error:
    return None
