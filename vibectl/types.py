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


@dataclass
class Error:
    error: str
    exception: Exception | None = None


Result = Success | Error
