"""
Type definitions for vibectl.

Contains common type definitions used across the application.
"""

from dataclasses import dataclass
from typing import Any


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
    continue_execution: bool = True  # Flag to control if execution flow should continue
    # When False, indicates a normal termination of a command sequence (like exit)


@dataclass
class Error:
    error: str
    exception: Exception | None = None
    recovery_suggestions: str | None = None


# Union type for command results
Result = Success | Error
