"""Tests for the console module."""

import pytest
from rich.console import Console
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
    assert "Warning: No output to process" in test_console.error_console.export_text()

    # Truncation warning
    test_console.print_truncation_warning()
    assert (
        "Warning: Output was truncated for processing"
        in test_console.error_console.export_text()
    )


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


def test_console_process_output_for_vibe(test_console: ConsoleManager) -> None:
    """Test processing output for vibe with token limits."""
    # Test short output (no truncation needed)
    short_output = "Short test output"
    processed, truncated = test_console.process_output_for_vibe(short_output)
    assert processed == short_output
    assert not truncated

    # Test long output (needs truncation)
    long_output = "x" * 2000
    processed, truncated = test_console.process_output_for_vibe(long_output)
    assert len(processed) < len(long_output)
    assert truncated


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
