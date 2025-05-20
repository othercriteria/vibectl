"""
Type definitions for vibectl.

Contains common type definitions used across the application.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    NewType,
    Protocol,
    runtime_checkable,
)

# Import Config for type hinting
from .config import Config

# Type alias for the structure of examples used in format_ml_examples
MLExampleItem = tuple[str, str, dict[str, Any]]

# For prompt construction
Examples = NewType("Examples", list[tuple[str, dict[str, Any]]])
Fragment = NewType("Fragment", str)
SystemFragments = NewType("SystemFragments", list[Fragment])
UserFragments = NewType("UserFragments", list[Fragment])
PromptFragments = NewType("PromptFragments", tuple[SystemFragments, UserFragments])

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


class PredicateCheckExitCode(int, Enum):
    """Exit codes for the 'vibectl check' command."""

    TRUE = 0  # Predicate is TRUE
    FALSE = 1  # Predicate is FALSE
    POORLY_POSED = 2  # Predicate is poorly posed or ambiguous
    CANNOT_DETERMINE = 3  # Cannot determine predicate truthiness


@dataclass
class OutputFlags:
    """Configuration for output display flags."""

    show_raw: bool
    show_vibe: bool
    warn_no_output: bool
    model_name: str
    show_metrics: bool  # Added flag for controlling metrics display
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
        show_metrics = self.show_metrics
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
            elif key == "show_metrics":
                show_metrics = value
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
            show_metrics=show_metrics,
            show_kubectl=show_kubectl,
            warn_no_proxy=warn_no_proxy,
        )


# Structured result types for subcommands
@dataclass
class Success:
    message: str = ""
    data: Any | None = None
    original_exit_code: int | None = None
    continue_execution: bool = True  # Flag to control if execution flow should continue
    # When False, indicates a normal termination of a command sequence (like exit)
    metrics: "LLMMetrics | None" = None


@dataclass
class Error:
    error: str
    exception: Exception | None = None
    recovery_suggestions: str | None = None
    # If False, auto command will continue processing after this error
    # Default True to maintain current behavior
    halt_auto_loop: bool = True
    metrics: "LLMMetrics | None" = None
    original_exit_code: int | None = None


# Union type for command results
Result = Success | Error


# --- Type Hints for Functions ---
SummaryPromptFragmentFunc = Callable[[Config | None, str | None], PromptFragments]
# -----------------------------


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


@dataclass
class LLMMetrics:
    """Stores metrics related to LLM calls."""

    token_input: int = 0
    token_output: int = 0
    latency_ms: float = (
        0.0  # Latency for the main LLM provider call (e.g., response_obj.text())
    )
    total_processing_duration_ms: float | None = None
    fragments_used: list[str] | None = None  # Track fragments if used
    call_count: int = 0

    def __add__(self, other: "LLMMetrics") -> "LLMMetrics":
        """Allows adding metrics together, useful for aggregation."""
        if not isinstance(other, LLMMetrics):
            return NotImplemented

        self_total_duration = self.total_processing_duration_ms or 0.0
        other_total_duration = other.total_processing_duration_ms or 0.0
        summed_total_duration = self_total_duration + other_total_duration
        final_summed_total_duration: float | None
        if (
            self.total_processing_duration_ms is None
            and other.total_processing_duration_ms is None
        ):
            final_summed_total_duration = None
        else:
            final_summed_total_duration = summed_total_duration

        return LLMMetrics(
            token_input=self.token_input + other.token_input,
            token_output=self.token_output + other.token_output,
            latency_ms=self.latency_ms + other.latency_ms,
            total_processing_duration_ms=final_summed_total_duration,
            call_count=self.call_count + other.call_count,
        )


# --- Kubectl Command Types ---


@runtime_checkable
class StatsProtocol(Protocol):
    """Protocol for tracking connection statistics."""

    bytes_sent: int
    bytes_received: int
    last_activity: float


# For LLM command generation schema
class ActionType(str, Enum):
    """Enum for LLM action types."""

    THOUGHT = "THOUGHT"
    COMMAND = "COMMAND"
    WAIT = "WAIT"
    ERROR = "ERROR"
    FEEDBACK = "FEEDBACK"
    DONE = "DONE"


@runtime_checkable
class ModelResponse(Protocol):
    """Protocol defining the expected interface for model responses."""

    def text(self) -> str:
        """Get the text content of the response.

        Returns:
            str: The text content of the response
        """
        ...

    def usage(self) -> Any:
        """Get token usage information from the response.

        Returns:
            Any: Usage object (structure may vary by model/library version)
        """
        ...


class ErrorSeverity(str, Enum):
    # Add any necessary error severity definitions here
    pass
