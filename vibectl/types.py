"""
Type definitions for vibectl.

Contains common type definitions used across the application.
"""

from dataclasses import dataclass


@dataclass
class OutputFlags:
    """Configuration for output display flags."""

    show_raw: bool
    show_vibe: bool
    warn_no_output: bool
    model_name: str
    show_kubectl: bool = False  # Flag to control showing kubectl commands
