"""
Console UI for vibectl.

This module provides console UI functionality for vibectl.
"""

from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.errors import MarkupError
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from .logutil import logger

# Import types only for type hints to avoid circular imports
if TYPE_CHECKING:
    from .types import LLMMetrics, OutputFlags


class ConsoleManager:
    """Manage console output for vibectl."""

    def __init__(self) -> None:
        """Initialize the console manager."""
        self.theme_name = "default"
        self._theme = Theme(
            {
                "error": "red",
                "warning": "yellow",
                "info": "blue",
                "success": "green",
                "vibe": "magenta",
                "key": "cyan",
                "value": "white",
            }
        )
        self.themes = {
            "default": Theme(
                {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                    "success": "green",
                    "vibe": "magenta",
                    "key": "cyan",
                    "value": "white",
                }
            ),
            "dark": Theme(
                {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                    "success": "green",
                    "vibe": "magenta",
                    "key": "cyan",
                    "value": "white",
                }
            ),
            "light": Theme(
                {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                    "success": "green",
                    "vibe": "magenta",
                    "key": "cyan",
                    "value": "black",
                }
            ),
            "accessible": Theme(
                {
                    "error": "red",
                    "warning": "blue",
                    "info": "cyan",
                    "success": "green",
                    "vibe": "magenta",
                    "key": "yellow",
                    "value": "white",
                }
            ),
        }
        self.console = Console(theme=self._theme)
        self.error_console = Console(stderr=True, theme=self._theme)
        self._live_vibe_display: Live | None = None
        self._live_vibe_text_content: Text | None = None
        self._accumulated_vibe_stream: str = ""

    def get_available_themes(self) -> list[str]:
        """Get list of available theme names.

        Returns:
            List[str]: List of available theme names
        """
        return list(self.themes.keys())

    def set_theme(self, theme_name: str) -> None:
        """Set the console theme."""
        if theme_name not in self.themes:
            raise ValueError("Invalid theme name")

        self.theme_name = theme_name
        self._theme = self.themes[theme_name]
        self.console = Console(theme=self._theme)
        self.error_console = Console(stderr=True, theme=self._theme)

    def print(self, message: str, style: str | None = None) -> None:
        """Print a message with optional style."""
        self.safe_print(self.console, message, style=style)

    def print_raw(self, message: str) -> None:
        """Print raw output."""
        self.safe_print(self.console, message, markup=False)

    def safe_print(
        self,
        console: Console,
        message: str | Table | Any,
        style: str | None = None,
        markup: bool = True,
        **kwargs: Any,
    ) -> None:
        """Print a message safely, handling malformed markup gracefully.

        If Rich markup parsing fails, fall back to printing without markup.

        Args:
            console: The console to print to
            message: The message to print
            style: Optional style to apply
            markup: Whether to enable markup parsing (default: True)
            **kwargs: Additional keyword arguments to pass to console.print
        """
        try:
            console.print(message, style=style, markup=markup, **kwargs)
        except MarkupError:
            # If markup parsing fails, try again with markup disabled
            console.print(message, style=style, markup=False, **kwargs)

    def print_error(self, message: str) -> None:
        """Print an error message."""
        self.safe_print(self.error_console, f"Error: {message}", style="error")

    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        self.safe_print(self.error_console, f"Warning: {message}", style="warning")

    def print_note(self, message: str, error: Exception | None = None) -> None:
        """Print a note message with optional error."""
        if error:
            self.safe_print(
                self.error_console, f"Note: {message} ({error!s})", style="info"
            )
        else:
            self.safe_print(self.error_console, f"Note: {message}", style="info")

    def print_success(self, message: str) -> None:
        """Print a success message."""
        self.safe_print(self.console, message, style="success")

    def start_live_vibe_panel(self) -> None:
        """Start a live-updating panel for streaming Vibe output."""
        if self._live_vibe_display is not None:
            self.stop_live_vibe_panel()

        self._accumulated_vibe_stream = ""
        self._live_vibe_text_content = Text("", no_wrap=False)
        panel_title = Text("✨ Vibe (streaming...)", style="bold magenta")
        live_panel = Panel(
            self._live_vibe_text_content, title=panel_title, expand=False
        )

        self._live_vibe_display = Live(
            live_panel, console=self.console, refresh_per_second=10, transient=True
        )
        self._live_vibe_display.start(refresh=True)

    def update_live_vibe_panel(self, chunk: str) -> None:
        """Update the content of the live Vibe panel with a new chunk of text."""
        if self._live_vibe_display and self._live_vibe_text_content is not None:
            self._accumulated_vibe_stream += chunk
            self._live_vibe_text_content.plain = self._accumulated_vibe_stream
        else:
            self.console.print(chunk, end="", highlight=False, markup=False)
            if hasattr(self.console.file, "flush"):
                self.console.file.flush()

    def stop_live_vibe_panel(self) -> str:
        """Stop the live-updating Vibe panel and return the accumulated text."""
        accumulated_text = self._accumulated_vibe_stream
        if self._live_vibe_display:
            self._live_vibe_display.stop()

        self._live_vibe_display = None
        self._live_vibe_text_content = None
        self._accumulated_vibe_stream = ""
        return accumulated_text

    def print_vibe(
        self, vibe_output: str, is_stream_chunk: bool = False, use_panel: bool = True
    ) -> None:
        """Print Vibe output using Rich Console, handling streaming.

        Args:
            vibe_output: The Vibe output text to print.
            is_stream_chunk: True if this is a chunk of a streaming response.
            use_panel: Whether to wrap the output in a Rich Panel.
        """
        if self._live_vibe_display and is_stream_chunk:
            self.update_live_vibe_panel(vibe_output)
        else:
            if use_panel:
                panel_title = Text("✨ Vibe", style="bold magenta")
                try:
                    self.console.print(
                        Panel(vibe_output, title=panel_title, expand=False)
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to print Vibe output with Rich Panel due to: {e}. "
                        "Falling back to plain text."
                    )
                    self.console.print("[bold magenta]✨ Vibe[/bold magenta]")
                    self.console.print(vibe_output, markup=False, highlight=False)
            else:
                # Print without panel, but still with Vibe header for context if
                # it's not a stream chunk
                if (
                    not is_stream_chunk
                ):  # Avoid header for every non-paneled chunk if that case arises
                    self.console.print("[bold magenta]✨ Vibe[/bold magenta]")
                self.console.print(vibe_output)  # Allows Rich markup in vibe_output

    def print_vibe_header(self) -> None:
        """Print vibe header."""
        self.safe_print(self.console, "✨ Vibe check:", style="vibe")

    def print_no_output_warning(self) -> None:
        """Print warning about no output."""
        self.print_warning(
            "No output will be displayed. "
            "Use --show-raw-output to see raw kubectl output or "
            "--show-vibe to see the vibe check summary."
        )

    def print_no_proxy_warning(self) -> None:
        """Print information about missing proxy configuration."""
        self.print_warning(
            "Traffic monitoring disabled. To enable statistics and monitoring:\n"
            "1. Set intermediate_port_range in your config:\n"
            "   vibectl config set intermediate_port_range 10000-11000\n"
            "2. Use port-forward with a port mapping (e.g., 8080:80)\n"
            "\nTo suppress this message: vibectl config set warn_no_proxy false"
        )

    def print_truncation_warning(self) -> None:
        """Print warning about output truncation."""
        self.print_warning("Output was truncated for processing")

    def print_missing_api_key_error(self) -> None:
        """Print error about missing API key."""
        self.print_error(
            "Missing API key. Please set OPENAI_API_KEY environment variable."
        )

    def print_missing_request_error(self) -> None:
        """Print error about missing request."""
        self.print_error("Missing request after 'vibe' command")

    def print_empty_output_message(self) -> None:
        """Print message about empty output."""
        self.print_note("No output to display")

    def print_keyboard_interrupt(self) -> None:
        """Print keyboard interrupt message."""
        self.print_error("Keyboard interrupt")

    def print_cancelled(self) -> None:
        """Print command cancellation message."""
        self.print_warning("Command cancelled")

    def print_processing(self, message: str) -> None:
        """Print a processing message.

        Args:
            message: The message to display indicating processing status.
        """
        self.safe_print(self.console, f"🔄 {message}", style="info")

    def print_proposal(self, message: str) -> None:
        """Print a proposal message."""
        self.safe_print(self.console, f"💡 {message}", style="vibe")

    def print_vibe_welcome(self) -> None:
        """Print vibe welcome message."""
        self.safe_print(
            self.console, "🔮 Welcome to vibectl - vibes-based kubectl", style="vibe"
        )
        self.safe_print(
            self.console,
            "Use 'vibe' commands to get AI-powered insights about your cluster",
        )

    def print_config_table(self, config_data: dict[str, Any]) -> None:
        """Print configuration data in a table.

        Args:
            config_data: Configuration data to display.
        """
        table = Table(title="Configuration")
        table.add_column("Setting", style="key")
        table.add_column("Value", style="value")

        for key, value in sorted(config_data.items()):
            table.add_row(str(key), str(value))

        self.safe_print(self.console, table)

    def handle_vibe_output(
        self,
        output: str,
        show_raw_output: bool,
        show_vibe: bool,
        vibe_output: str | None = None,
    ) -> None:
        """Handle displaying command output in both raw and vibe formats.

        Args:
            output: Raw command output.
            show_raw_output: Whether to show raw output.
            show_vibe: Whether to show vibe output.
            vibe_output: Optional vibe output to display.
        """
        if show_raw_output:
            self.print_raw(output)

        if show_vibe and vibe_output:
            self.print_vibe(vibe_output)

    def print_metrics(
        self,
        latency_ms: float | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        source: str | None = None,
        total_duration: float | None = None,
    ) -> None:
        """Display LLM metrics in a formatted way."""
        items = []
        if source:
            items.append(f"[dim]Source:[/] {source}")
        if latency_ms is not None:
            items.append(f"[dim]Latency:[/] {latency_ms:.2f} ms")
        if total_duration is not None:
            items.append(f"[dim]Total Duration:[/] {total_duration:.2f} ms")
        if tokens_in is not None and tokens_out is not None:
            items.append(f"[dim]Tokens:[/] {tokens_in} in, {tokens_out} out")

        if items:
            self.safe_print(
                self.console, f"📊 [bold cyan]Metrics:[/bold cyan] {' | '.join(items)}"
            )

    def print_waiting(self, message: str = "Waiting...") -> None:
        """Display a waiting message."""
        self.safe_print(self.console, message, style="info")


def should_show_sub_metrics(output_flags: "OutputFlags") -> bool:
    """Determine if individual LLM call metrics should be displayed."""
    return output_flags.show_metrics.should_show_sub_metrics()


def should_show_total_metrics(output_flags: "OutputFlags") -> bool:
    """Determine if accumulated/total metrics should be displayed."""
    return output_flags.show_metrics.should_show_total_metrics()


def print_sub_metrics_if_enabled(
    metrics: "LLMMetrics | None",
    output_flags: "OutputFlags",
    source: str,
) -> None:
    """Print individual LLM call metrics if sub-metrics are enabled."""
    if metrics and should_show_sub_metrics(output_flags):
        console_manager.print_metrics(
            latency_ms=metrics.latency_ms,
            tokens_in=metrics.token_input,
            tokens_out=metrics.token_output,
            source=source,
            total_duration=metrics.total_processing_duration_ms,
        )


def print_total_metrics_if_enabled(
    metrics: "LLMMetrics | None",
    output_flags: "OutputFlags",
    source: str,
) -> None:
    """Print accumulated/total metrics if total metrics are enabled."""
    if metrics and should_show_total_metrics(output_flags) and metrics.call_count > 0:
        console_manager.print_metrics(
            latency_ms=metrics.latency_ms,
            tokens_in=metrics.token_input,
            tokens_out=metrics.token_output,
            source=source,
            total_duration=metrics.total_processing_duration_ms,
        )


# Create global instance for easy import
console_manager = ConsoleManager()
