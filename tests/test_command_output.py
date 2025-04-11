"""Tests for command output handling functionality."""

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    DEFAULT_MODEL,
    DEFAULT_SHOW_RAW_OUTPUT,
    DEFAULT_SHOW_VIBE,
    DEFAULT_WARN_NO_OUTPUT,
    OutputFlags,
    configure_output_flags,
    handle_command_output,
)


@pytest.fixture
def test_config(tmp_path: Path) -> Any:
    """Create a test configuration instance."""
    from vibectl.config import Config

    return Config(base_dir=tmp_path)


@pytest.fixture
def prevent_exit() -> Generator[MagicMock, None, None]:
    """Prevent sys.exit from exiting the tests."""
    with patch("sys.exit") as mock_exit:
        yield mock_exit


@pytest.fixture
def default_summary_prompt() -> Callable[[], str]:
    """Create a default summary prompt function."""

    def summary_prompt() -> str:
        return "Summarize this: {output}"

    return summary_prompt


def test_handle_command_output_with_raw_output_only(
    prevent_exit: MagicMock, default_summary_prompt: Callable[[], str]
) -> None:
    """Test handle_command_output with raw output only."""
    # Create output flags with raw output only
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Call the function with only raw output enabled
    handle_command_output(
        output="test output",
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_with_vibe_only(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with vibe output only."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags with vibe output only
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Call the function with vibe enabled
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_both_outputs(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with both outputs."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags with both outputs enabled
    output_flags = OutputFlags(
        show_raw=True, show_vibe=True, warn_no_output=True, model_name="model-xyz-1.2.3"
    )

    # Call the function with both outputs enabled
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )


def test_handle_command_output_no_output(
    prevent_exit: MagicMock, default_summary_prompt: Callable[[], str]
) -> None:
    """Test handle_command_output with no outputs enabled."""
    # Create output flags with no outputs
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Call the function with no outputs enabled and warning enabled
    # Using patch but not capturing the mock since we're not inspecting its calls
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_llm_error(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with LLM error."""
    # Set up adapter mock to return an error
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "ERROR: Test error"
    mock_llm.return_value = mock_adapter

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Call the function and check for error handling
    with patch("vibectl.command_handler.handle_exception"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "error test",  # Trigger error response
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_empty_response(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with empty LLM response."""
    # Set up adapter mock to return empty response
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = ""
    mock_llm.return_value = mock_adapter

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Call the function with vibe enabled
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "empty response test",  # Trigger empty response
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_with_command(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with command parameter."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Call the function with command parameter
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.command_handler.output_processor") as mock_processor,
    ):
        # Set up output processor mock
        mock_processor.process_auto.return_value = ("test output", False)

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: (
                "Summarize this command {command} with output: {output}"
            ),
            command="get pods",
        )

        # Verify output was displayed
        mock_console.print_vibe.assert_called_once_with("Test response")
        # Verify memory was updated
        mock_update_memory.assert_called_once_with(
            "get pods", "test output", "Test response", "model-xyz-1.2.3"
        )
        # Verify adapter was called with correct prompt
        mock_adapter.execute.assert_called_once_with(
            mock_adapter.get_model.return_value,
            "Summarize this command get pods with output: test output",
        )


def test_configure_output_flags_no_flags() -> None:
    """Test configure_output_flags with no flags."""
    # Run without flags
    output_flags = configure_output_flags()

    # Verify defaults
    assert output_flags.show_raw == DEFAULT_SHOW_RAW_OUTPUT
    assert output_flags.show_vibe == DEFAULT_SHOW_VIBE
    assert output_flags.warn_no_output == DEFAULT_WARN_NO_OUTPUT
    assert output_flags.model_name == DEFAULT_MODEL


def test_configure_output_flags_raw_only() -> None:
    """Test configure_output_flags with raw flag only."""
    # Run with raw flag only
    output_flags = configure_output_flags(
        show_raw_output=True, show_vibe=False, model="model-xyz-1.2.3"
    )

    # Verify flags
    assert output_flags.show_raw is True
    assert output_flags.show_vibe is False
    assert output_flags.warn_no_output == DEFAULT_WARN_NO_OUTPUT
    assert output_flags.model_name == "model-xyz-1.2.3"


def test_configure_output_flags_vibe_only() -> None:
    """Test configure_output_flags with vibe flag only."""
    # Run with vibe flag only
    output_flags = configure_output_flags(
        show_raw_output=False, show_vibe=True, model="model-xyz-1.2.3"
    )

    # Verify flags
    assert output_flags.show_raw is False
    assert output_flags.show_vibe is True
    assert output_flags.warn_no_output == DEFAULT_WARN_NO_OUTPUT
    assert output_flags.model_name == "model-xyz-1.2.3"


def test_configure_output_flags_both_flags() -> None:
    """Test configure_output_flags with both flags."""
    # Run with both flags
    output_flags = configure_output_flags(
        show_raw_output=True, show_vibe=True, model="model-xyz-1.2.3"
    )

    # Verify flags
    assert output_flags.show_raw is True
    assert output_flags.show_vibe is True
    assert output_flags.warn_no_output == DEFAULT_WARN_NO_OUTPUT
    assert output_flags.model_name == "model-xyz-1.2.3"


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_model_name_from_config(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with model name from config."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags with model name from config
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="model-from-config",
    )

    # Call the function with model name from config
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_model_name_from_env(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with model name from environment."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags with model name from env
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="model-from-env",
    )

    # Call the function with model name from env
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_model_name_from_default(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with model name from default."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags with model name from default
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
    )

    # Call the function with model name from default
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_basic(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with basic configuration."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags with both outputs enabled
    output_flags = OutputFlags(
        show_raw=True, show_vibe=True, warn_no_output=True, model_name="model-xyz-1.2.3"
    )

    # Call the function with both outputs enabled and processor
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.output_processor") as mock_processor,
    ):
        # Set up output processor mock
        mock_processor.process_auto.return_value = ("test output", False)

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )

        # Verify raw output was shown and proper function was called
        mock_console.print_raw.assert_called_once_with("test output")


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_raw(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with raw output only."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_llm.return_value = mock_adapter

    # Create output flags with raw only
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Call the function with raw only and processor
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.output_processor") as mock_processor,
    ):
        # Set up output processor mock
        mock_processor.process_auto.return_value = ("processed output", False)

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )

        # Verify raw output was shown
        mock_console.print_raw.assert_called_once_with("test output")


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_no_vibe(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with vibe disabled."""
    # Create output flags with vibe disabled
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Call the function
    with patch("vibectl.command_handler.console_manager") as mock_console:
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "This should not be used",
        )

        # Verify only raw output was shown
        mock_console.print_raw.assert_called_once_with("test output")
        # Verify vibe was not shown (model never used)
        mock_llm.assert_not_called()
