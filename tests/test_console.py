"""Tests for the console module."""

from unittest.mock import Mock

import pytest
from rich.console import Console
from rich.errors import MarkupError
from rich.theme import Theme

from vibectl.console import ConsoleManager


def test_console_initialization() -> None:
    """Test ConsoleManager initialization with default theme."""
    console_manager = ConsoleManager()
    assert console_manager.theme_name == "default"
    assert isinstance(console_manager.console, Console)
    assert isinstance(console_manager.error_console, Console)
    assert isinstance(console_manager._theme, Theme)


def test_console_set_theme() -> None:
    """Test setting different themes."""
    console_manager = ConsoleManager()

    # Test all available themes
    for theme_name in ["default", "dark", "light", "accessible"]:
        console_manager.set_theme(theme_name)
        assert console_manager.theme_name == theme_name
        assert isinstance(console_manager._theme, Theme)


def test_console_set_invalid_theme() -> None:
    """Test setting invalid theme."""
    console_manager = ConsoleManager()

    with pytest.raises(ValueError, match="Invalid theme name"):
        console_manager.set_theme("nonexistent_theme")


def test_console_get_available_themes() -> None:
    """Test getting available themes."""
    console_manager = ConsoleManager()
    themes = console_manager.get_available_themes()

    assert isinstance(themes, list)
    assert all(isinstance(theme, str) for theme in themes)
    assert "default" in themes
    assert "dark" in themes
    assert "light" in themes
    assert "accessible" in themes


def test_console_print_methods(test_console: ConsoleManager) -> None:
    """Test various print methods."""
    # Regular print
    test_console.print("Test message")
    assert "Test message" in test_console.console.export_text()

    # Raw print
    test_console.print_raw("Raw message")
    assert "Raw message" in test_console.console.export_text()

    # Error print
    test_console.print_error("Error message")
    assert "Error: Error message" in test_console.error_console.export_text()

    # Warning print
    test_console.print_warning("Warning message")
    assert "Warning: Warning message" in test_console.error_console.export_text()

    # Note print
    test_console.print_note("Note message")
    assert "Note: Note message" in test_console.error_console.export_text()

    # Success print
    test_console.print_success("Success message")
    assert "Success message" in test_console.console.export_text()


def test_console_print_note_with_error(test_console: ConsoleManager) -> None:
    """Test printing note with error."""
    error = ValueError("Test error")
    test_console.print_note("Note message", error=error)
    output = test_console.error_console.export_text()
    assert "Note: Note message" in output
    assert "Test error" in output


def test_console_print_vibe(test_console: ConsoleManager) -> None:
    """Test vibe-related print methods."""
    # Vibe header
    test_console.print_vibe_header()
    assert "✨ Vibe check:" in test_console.console.export_text()

    # Vibe summary
    test_console.print_vibe("Test vibe summary")
    output = test_console.console.export_text()
    assert "✨ Vibe check:" in output
    assert "Test vibe summary" in output


def test_console_print_warnings(test_console: ConsoleManager) -> None:
    """Test warning-related print methods."""
    # No output warning
    test_console.print_no_output_warning()
    warning_text = test_console.error_console.export_text()
    assert "Warning: No output will be displayed" in warning_text
    assert "--show-raw-output" in warning_text
    assert "--show-vibe" in warning_text

    # Reset the console output
    test_console.error_console = Console(
        stderr=True, record=True, theme=test_console._theme
    )

    # Truncation warning
    test_console.print_truncation_warning()
    assert "Warning: Output was truncated" in test_console.error_console.export_text()


def test_console_print_config_table(test_console: ConsoleManager) -> None:
    """Test printing configuration table."""
    config_data = {
        "theme": "dark",
        "kubeconfig": "/test/path",
        "show_raw_output": True,
    }

    test_console.print_config_table(config_data)
    output = test_console.console.export_text()

    assert "Configuration" in output
    assert "theme" in output
    assert "dark" in output
    assert "kubeconfig" in output
    assert "/test/path" in output


def test_console_handle_vibe_output(test_console: ConsoleManager) -> None:
    """Test handling vibe output with different settings."""
    output = "Test output"
    summary = "Test summary"

    # Test with both outputs enabled
    test_console.handle_vibe_output(output, True, True, summary)
    console_output = test_console.console.export_text()
    assert output in console_output
    assert summary in console_output

    # Test with only raw output
    test_console = ConsoleManager()  # Reset console
    theme = test_console.themes["default"]
    test_console.console = Console(record=True, theme=theme)
    test_console.error_console = Console(stderr=True, record=True, theme=theme)
    test_console.handle_vibe_output(output, True, False)
    assert output in test_console.console.export_text()

    # Test with only vibe output
    test_console = ConsoleManager()  # Reset console
    theme = test_console.themes["default"]
    test_console.console = Console(record=True, theme=theme)
    test_console.error_console = Console(stderr=True, record=True, theme=theme)
    test_console.handle_vibe_output(output, False, True, summary)
    console_output = test_console.console.export_text()
    assert output not in console_output
    assert summary in console_output

    # Test with no output enabled
    test_console = ConsoleManager()  # Reset console
    theme = test_console.themes["default"]
    test_console.console = Console(record=True, theme=theme)
    test_console.error_console = Console(stderr=True, record=True, theme=theme)
    test_console.handle_vibe_output(output, False, False)
    assert not test_console.console.export_text()  # No output should be printed


def test_console_print_error_methods(test_console: ConsoleManager) -> None:
    """Test specific error print methods."""
    # Test printing missing API key error
    test_console.print_missing_api_key_error()
    assert "Error: Missing API key" in test_console.error_console.export_text()

    # Test printing missing request error
    test_console.print_missing_request_error()
    assert "Error: Missing request" in test_console.error_console.export_text()

    # Test printing empty output message
    test_console.print_empty_output_message()
    assert "Note: No output to display" in test_console.error_console.export_text()

    # Test printing keyboard interrupt
    test_console.print_keyboard_interrupt()
    assert "Error: Keyboard interrupt" in test_console.error_console.export_text()


def test_console_print_vibe_with_markup_errors(test_console: ConsoleManager) -> None:
    """Test print_vibe handling of content with malformed Rich markup.

    This tests that our safe_print handler correctly handles malformed markup
    by falling back to non-markup mode.
    """
    # This is the problematic content, as seen in the error message
    text_with_malformed_markup = (
        "The Kubernetes cluster consists of:\n"
        "- Control Plane components running on master node\n"
        "- Worker nodes running in separate [/yellow] pods"
    )

    # Our implementation now handles this gracefully without raising exceptions
    test_console.print_vibe(text_with_malformed_markup)

    # Verify that the output was printed (with markup stripped)
    output = test_console.console.export_text()
    assert "✨ Vibe check:" in output
    assert "- Worker nodes running in separate [/yellow] pods" in output


def test_console_print_error_with_markup_errors(test_console: ConsoleManager) -> None:
    """Test print_error handling of content with malformed Rich markup.

    This test verifies that our console manager now properly handles malformed
    markup by falling back to non-markup mode.
    """
    # This is similar to the problematic content seen in the real error
    error_with_malformed_markup = (
        "Some Kubernetes components are [yellow]highlighted but[/yellow] others have "
        "broken [blue]formatting [/yellow] which causes errors"
    )

    # The implementation should now handle this without raising exceptions
    test_console.print_error(error_with_malformed_markup)

    # Verify that the output was printed (without handling markup)
    output = test_console.error_console.export_text()
    assert "Error: Some Kubernetes components are" in output
    assert "broken [blue]formatting [/yellow] which causes errors" in output


def test_logging_handler_with_markup_errors(
    test_console: ConsoleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that logging errors with malformed markup are handled gracefully.

    This test simulates what's happening in the real-world scenario, where
    logging sends a message with malformed markup to the console handler.
    """
    import logging

    from vibectl.logutil import ConsoleManagerHandler

    # Create a mock logger
    logger = logging.getLogger("test")
    logger.setLevel(logging.ERROR)

    # Clear any existing handlers
    for handler in logger.handlers:
        logger.removeHandler(handler)

    # Add our console handler that will forward to print_error
    handler = ConsoleManagerHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    # Monkeypatch the console_manager used by ConsoleManagerHandler
    # to use our test console
    monkeypatch.setattr("vibectl.logutil.console_manager", test_console)

    # Create a message with problematic markup similar to what an LLM might generate
    error_message = (
        "Error in Kubernetes [yellow]configuration:\n"
        "- Missing service account\n"
        "- Invalid [/yellow] permissions"
    )

    # This should no longer raise an exception
    logger.error(error_message)

    # Verify that the output was printed (with markup stripped)
    output = test_console.error_console.export_text()
    # When markup fails, Rich renders the text without processing the markup tags
    assert "Error: Error in Kubernetes configuration:" in output
    assert (
        "- Invalid  permissions" in output
    )  # Notice the two spaces between "Invalid" and "permissions"


def test_stack_trace_reproduction(
    test_console: ConsoleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that directly reproduces the error seen in the stack trace.

    This test uses the exact error pattern from the real-world issue, with a closing
    [/yellow] tag that doesn't match any open tag.
    """
    import logging

    from vibectl.logutil import ConsoleManagerHandler

    # Create logger with our handler
    logger = logging.getLogger("reproduction_test")
    logger.setLevel(logging.ERROR)

    # Clear existing handlers
    for handler in logger.handlers:
        logger.removeHandler(handler)

    # Add our console handler
    handler = ConsoleManagerHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    # Monkeypatch the console_manager
    monkeypatch.setattr("vibectl.logutil.console_manager", test_console)

    # This is the exact problematic pattern from the stack trace
    error_message = (
        "Some cluster information with a closing tag [/yellow] "
        "that doesn't match any open tag"
    )

    # This should no longer raise a MarkupError
    logger.error(error_message)

    # Verify output was printed - check for parts of the message
    # since formatting may vary
    output = test_console.error_console.export_text()

    # Success is just that we didn't raise an exception
    # The exact formatting is not critical, but we should have the main content
    assert "Error:" in output
    assert "cluster information" in output
    assert "closing tag" in output
    assert "open tag" in output


def test_safe_print_handles_markup_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Test safe_print handles markup errors gracefully."""
    # Create a mock Console with a print method that raises MarkupError
    mock_console = Mock(spec=Console)
    mock_console.print.side_effect = [
        MarkupError("Invalid markup"),  # First call raises error
        None,  # Second call succeeds
    ]

    console_manager = ConsoleManager()

    # Call safe_print with markup that would cause an error
    message = "Message [with] broken [markup"
    console_manager.safe_print(mock_console, message, style="test")

    # Verify it called print twice - once with markup, once without
    assert mock_console.print.call_count == 2
    # First call with markup=True
    mock_console.print.assert_any_call(message, style="test", markup=True)
    # Second call with markup=False
    mock_console.print.assert_any_call(message, style="test", markup=False)
