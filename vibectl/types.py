"""
Type definitions for vibectl.

Contains common type definitions used across the application.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    NewType,
    Protocol,
    runtime_checkable,
)

# Import Config for type hinting only when needed
if TYPE_CHECKING:
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


@runtime_checkable
class LLMUsage(Protocol):
    """Protocol defining the expected interface for model usage details."""

    input: int
    output: int
    details: dict[str, Any] | None


class PredicateCheckExitCode(int, Enum):
    """Exit codes for the 'vibectl check' command."""

    TRUE = 0  # Predicate is TRUE
    FALSE = 1  # Predicate is FALSE
    POORLY_POSED = 2  # Predicate is poorly posed or ambiguous
    CANNOT_DETERMINE = 3  # Cannot determine predicate truthiness


class MetricsDisplayMode(str, Enum):
    """Enumeration for different metrics display modes."""

    NONE = "none"  # Show no metrics
    TOTAL = "total"  # Show only total/accumulated metrics
    SUB = "sub"  # Show only individual sub-metrics
    ALL = "all"  # Show both sub-metrics and totals

    @classmethod
    def from_value(cls, value: str | None) -> "MetricsDisplayMode":
        """Convert string input to MetricsDisplayMode."""
        if value is None:
            return cls.NONE
        elif isinstance(value, str):
            try:
                return cls(value.lower())
            except ValueError:
                # Invalid string value, default to NONE
                return cls.NONE
        else:
            # Unknown type, default to NONE
            return cls.NONE

    @classmethod
    def from_config(cls, config: "Config") -> "MetricsDisplayMode":
        """Create MetricsDisplayMode from config, with fallback to default."""
        config_value = config.get("display.show_metrics", "none")
        return cls.from_value(config_value)

    def should_show_sub_metrics(self) -> bool:
        """Whether individual LLM call metrics should be displayed."""
        return self in (self.SUB, self.ALL)

    def should_show_total_metrics(self) -> bool:
        """Whether accumulated/total metrics should be displayed."""
        return self in (self.TOTAL, self.ALL)


@dataclass
class OutputFlags:
    """Flags that control command output behavior."""

    model_name: str
    show_raw_output: bool
    show_vibe: bool
    show_kubectl: bool = False  # Default value
    show_metrics: MetricsDisplayMode = MetricsDisplayMode.NONE  # Default value
    show_streaming: bool = False  # Default value
    warn_no_output: bool = True  # Default value
    warn_no_proxy: bool = True  # Default value
    freeze_memory: bool = False  # Default value
    unfreeze_memory: bool = False  # Default value

    def with_updates(self, **updates: Any) -> "OutputFlags":
        """Create a new OutputFlags instance with specified updates."""
        # No conversion needed - all inputs should already be correct types
        return replace(self, **updates)

    @classmethod
    def from_args(
        cls,
        model: str | None = None,
        show_raw_output: bool | None = None,
        show_vibe: bool | None = None,
        show_kubectl: bool | None = None,
        show_metrics: MetricsDisplayMode
        | None = None,  # Only support MetricsDisplayMode now
        show_streaming: bool | None = None,
        warn_no_output: bool | None = None,
        warn_no_proxy: bool | None = None,
        freeze_memory: bool = False,
        unfreeze_memory: bool = False,
        config: "Config | None" = None,
    ) -> "OutputFlags":
        """Create OutputFlags from command arguments with config fallbacks."""
        # Import only once at runtime to avoid circular imports
        from .config import Config

        if config is None:
            config = Config()

        return cls(
            model_name=model or config.get("llm.model", "claude-3.7-sonnet"),
            show_raw_output=show_raw_output
            if show_raw_output is not None
            else config.get("display.show_raw_output", False),
            show_vibe=show_vibe
            if show_vibe is not None
            else config.get("display.show_vibe", True),
            show_kubectl=show_kubectl
            if show_kubectl is not None
            else config.get("display.show_kubectl", False),
            show_metrics=show_metrics or MetricsDisplayMode.from_config(config),
            show_streaming=show_streaming
            if show_streaming is not None
            else config.get("display.show_streaming", True),
            warn_no_output=warn_no_output
            if warn_no_output is not None
            else config.get("warnings.warn_no_output", True),
            warn_no_proxy=warn_no_proxy
            if warn_no_proxy is not None
            else config.get("warnings.warn_no_proxy", True),
            freeze_memory=freeze_memory,
            unfreeze_memory=unfreeze_memory,
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
SummaryPromptFragmentFunc = Callable[["Config | None", str | None], PromptFragments]
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
    cost_usd: float | None = None  # Cost in USD for the LLM call

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

        # Sum costs if both are available
        summed_cost: float | None = None
        if self.cost_usd is not None and other.cost_usd is not None:
            summed_cost = self.cost_usd + other.cost_usd
        elif self.cost_usd is not None:
            summed_cost = self.cost_usd
        elif other.cost_usd is not None:
            summed_cost = other.cost_usd

        return LLMMetrics(
            token_input=self.token_input + other.token_input,
            token_output=self.token_output + other.token_output,
            latency_ms=self.latency_ms + other.latency_ms,
            total_processing_duration_ms=final_summed_total_duration,
            call_count=self.call_count + other.call_count,
            cost_usd=summed_cost,
        )


def _get_proxy_aware_source_name(source: str) -> str:
    """Add proxy indication to source name if using proxy adapter.

    Args:
        source: Original source name

    Returns:
        Source name with "Proxy" prefix if using proxy, otherwise unchanged
    """
    try:
        # Import here to avoid circular import
        from .model_adapter import _default_adapter

        # Check if we're using proxy adapter
        if _default_adapter is not None:
            # Import here to avoid circular import at module level
            from .proxy_model_adapter import ProxyModelAdapter

            if isinstance(_default_adapter, ProxyModelAdapter):
                return f"LLM Proxy {source.replace('LLM ', '')}"

        return source
    except ImportError:
        # If proxy adapter isn't available, return original source
        return source


class LLMMetricsAccumulator:
    """
    Helper class to accumulate LLM metrics across multiple calls.

    This reduces boilerplate when accumulating metrics in commands that
    make multiple LLM calls (like the check command). It handles both
    accumulation and immediate display of sub-metrics.
    """

    def __init__(self, output_flags: "OutputFlags") -> None:
        self.accumulated_metrics = LLMMetrics()
        self.output_flags = output_flags

    def add_metrics(self, metrics: "LLMMetrics | None", source: str) -> None:
        """Add metrics from LLM call to accumulator; display sub-metrics if enabled."""
        if metrics:
            self.accumulated_metrics += metrics
            # Import here to avoid circular import
            from .console import print_sub_metrics_if_enabled

            # Modify source name to indicate proxy usage if applicable
            proxy_aware_source = _get_proxy_aware_source_name(source)
            print_sub_metrics_if_enabled(metrics, self.output_flags, proxy_aware_source)

    def print_total_if_enabled(self, source: str) -> None:
        """Print accumulated metrics if total metrics are enabled."""
        # Import here to avoid circular import
        from .console import print_total_metrics_if_enabled

        # Modify source name to indicate proxy usage if applicable
        proxy_aware_source = _get_proxy_aware_source_name(source)
        print_total_metrics_if_enabled(
            self.accumulated_metrics, self.output_flags, proxy_aware_source
        )

    def get_metrics(self) -> "LLMMetrics":
        """Get the accumulated metrics."""
        return self.accumulated_metrics


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
    """Protocol defining the expected interface for model responses from the
    llm library, covering sync, async, and streaming."""

    async def text(self) -> str:
        """Get the text content of the response. Awaited for async responses."""
        ...

    async def json(self) -> dict[str, Any]:
        """Get the JSON content of the response. Awaited for async responses."""
        ...

    async def usage(self) -> LLMUsage:
        """Get the token usage information. Awaited for async responses."""
        ...

    def __aiter__(self) -> AsyncIterator[str]:
        """Enable `async for chunk in response:` for streaming."""
        ...

    async def on_done(
        self, callback: Callable[["ModelResponse"], Awaitable[None]]
    ) -> None:
        """Register a callback to be executed when the response is complete."""
        ...

    # For synchronous, non-streaming calls, these might be available.
    # However, the adapter will primarily use the async versions for streaming.
    # If a sync version of these is needed by the protocol for other reasons,
    # they would need to be added. For now, focusing on async streaming path.


class ErrorSeverity(str, Enum):
    # Add any necessary error severity definitions here
    pass
