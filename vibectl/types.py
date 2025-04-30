"""
Type definitions for vibectl.

Contains common type definitions used across the application.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# Keywords indicating potentially recoverable API errors
# Used to identify transient issues that shouldn't halt autonomous loops
RECOVERABLE_API_ERROR_KEYWORDS = [
    "overloaded",
    "rate_limit",
    "rate limit",
    "capacity",
    "unavailable",
    "retry",
    "throttled",
    "server error",  # Generic but often transient
    "service_unavailable",
    # Add specific provider error codes/types if known and helpful
    # e.g., "insufficient_quota", "503 Service Unavailable"
]


class RecoverableApiError(ValueError):
    """Custom exception for potentially recoverable API errors (e.g., rate limits)."""

    pass


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

    def replace(self, **kwargs: Any) -> "OutputFlags":
        """Create a new OutputFlags instance with specified fields replaced.

        Similar to dataclasses.replace(), this allows creating a modified copy
        with only specific fields changed.

        Args:
            **kwargs: Field values to change in the new instance

        Returns:
            A new OutputFlags instance with the specified changes
        """
        # Start with current values
        show_raw = self.show_raw
        show_vibe = self.show_vibe
        warn_no_output = self.warn_no_output
        model_name = self.model_name
        show_kubectl = self.show_kubectl
        warn_no_proxy = self.warn_no_proxy

        # Update with any provided values
        for key, value in kwargs.items():
            if key == "show_raw":
                show_raw = value
            elif key == "show_vibe":
                show_vibe = value
            elif key == "warn_no_output":
                warn_no_output = value
            elif key == "model_name":
                model_name = value
            elif key == "show_kubectl":
                show_kubectl = value
            elif key == "warn_no_proxy":
                warn_no_proxy = value

        # Create new instance with updated values
        return OutputFlags(
            show_raw=show_raw,
            show_vibe=show_vibe,
            warn_no_output=warn_no_output,
            model_name=model_name,
            show_kubectl=show_kubectl,
            warn_no_proxy=warn_no_proxy,
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
    # If False, auto command will continue processing after this error
    # Default True to maintain current behavior
    halt_auto_loop: bool = True


# Union type for command results
Result = Success | Error


@dataclass
class InvalidOutput:
    """Represents an input that is fundamentally invalid for processing."""

    original: Any
    reason: str

    def __str__(self) -> str:
        orig_repr = str(self.original)[:50]
        return f"InvalidOutput(reason='{self.reason}', original={orig_repr}...)"


@dataclass
class Truncation:
    """Represents the result of a truncation operation."""

    original: str
    truncated: str
    original_type: str | None = None
    plug: str | None = None

    def __str__(self) -> str:
        return (
            f"Truncation(original=<len {len(self.original)}>, "
            f"truncated=<len {len(self.truncated)}>, type={self.original_type})"
        )


# Type alias for processing result before final truncation
Output = Truncation | InvalidOutput

# Type alias for YAML sections dictionary
YamlSections = dict[str, str]

# --- Kubectl Command Types ---


@runtime_checkable
class StatsProtocol(Protocol):
    """Protocol for tracking connection statistics."""

    bytes_sent: int
    bytes_received: int
    last_activity: float


# For LLM command generation schema
class ActionType(Enum):
    COMMAND = "COMMAND"
    ERROR = "ERROR"
    WAIT = "WAIT"
    FEEDBACK = "FEEDBACK"
