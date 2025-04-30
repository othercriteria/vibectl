"""Tests for command output handling functionality."""

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    Error,
    OutputFlags,
    configure_output_flags,
    handle_command_output,
)
from vibectl.config import DEFAULT_CONFIG
from vibectl.types import Success, Truncation

# Ensure DEFAULT_MODEL is always a string for use in OutputFlags
DEFAULT_MODEL = str(DEFAULT_CONFIG["model"])


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
        model_name=DEFAULT_MODEL,
    )

    # Call the function with only raw output enabled
    handle_command_output(
        output="test output",
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler._get_llm_summary")
def test_handle_command_output_with_vibe_only(
    mock_get_summary: MagicMock, mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with vibe output only."""
    # Configure mock LLM response
    mock_get_summary.return_value = "Test response"

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
        model_name=DEFAULT_MODEL,
    )

    # Mock output processor to avoid any real processing
    with (
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.output_processor") as mock_processor,
        patch("vibectl.command_handler.update_memory"),
    ):
        # Configure output processor mock
        mock_processor.process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )

        # Call the function with vibe enabled
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )

    mock_get_summary.assert_called_once()


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler._get_llm_summary")
def test_handle_command_output_both_outputs(
    mock_get_summary: MagicMock, mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with both outputs."""
    # Configure mock LLM response
    mock_get_summary.return_value = "Test response"

    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags with both outputs enabled
    output_flags = OutputFlags(
        show_raw=True, show_vibe=True, warn_no_output=True, model_name=DEFAULT_MODEL
    )

    # Mock output processor to avoid any real processing
    with (
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.output_processor") as mock_processor,
        patch("vibectl.command_handler.update_memory"),
    ):
        # Configure output processor mock
        mock_processor.process_auto.return_value = Truncation(
            original="test output", truncated="processed test output"
        )

        # Call the function with both outputs enabled
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )

    mock_get_summary.assert_called_once()


def test_handle_command_output_no_output(
    prevent_exit: MagicMock, default_summary_prompt: Callable[[], str]
) -> None:
    """Test handle_command_output with no outputs enabled."""
    # Create output flags with no outputs
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
    )

    # Call the function with no outputs enabled and warning enabled
    # Using patch but not capturing the mock since we're not inspecting its calls
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler._get_llm_summary")
def test_handle_command_output_empty_response(
    mock_get_summary: MagicMock,
    mock_processor: MagicMock,
    prevent_exit: MagicMock,
) -> None:
    """Test handle_command_output with empty LLM response."""
    # Configure mock LLM response
    mock_get_summary.return_value = ""

    # Set up processor mock
    mock_processor.process_auto.return_value = Truncation(
        original="test output", truncated="test output"
    )

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
    )

    # Call the function with vibe enabled - mock everything
    with (
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter,
        patch("vibectl.command_handler.update_memory"),
    ):
        # Configure model adapter
        mock_adapter = Mock()
        mock_adapter.get_model.return_value = Mock()
        mock_adapter.execute.return_value = ""
        mock_get_adapter.return_value = mock_adapter

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "empty response test",
        )

    mock_get_summary.assert_called_once()


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler._get_llm_summary")
def test_handle_command_output_with_command(
    mock_get_summary: MagicMock,
    mock_processor: MagicMock,
    mock_llm: MagicMock,
    prevent_exit: MagicMock,
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
        model_name=DEFAULT_MODEL,
    )

    # Call the function with command parameter
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.command_handler._get_llm_summary") as mock_get_summary,
        patch("vibectl.command_handler.output_processor") as mock_processor,
    ):
        # Set up output processor mock to return Truncation
        mock_processor.process_auto.return_value = Truncation(
            original="test output", truncated="test output"
        )
        # Mock the summary call directly
        mock_get_summary.return_value = "Test response"

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: (
                "Summarize this command with output: {output}"
            ),
            command="get pods",
        )

        # Verify output was displayed
        mock_console.print_vibe.assert_called_once_with("Test response")
        # Verify memory was updated
        mock_update_memory.assert_called_once_with(
            command="get pods",
            command_output="test output",
            vibe_output="Test response",
            model_name=DEFAULT_MODEL,
        )
        # Verify LLM summary call was mocked correctly
        mock_get_summary.assert_called_once()


def test_configure_output_flags_no_flags() -> None:
    """Test configure_output_flags with no flags."""
    # Run without flags
    output_flags = configure_output_flags()

    # Verify defaults
    assert output_flags.show_raw == DEFAULT_CONFIG["show_raw_output"]
    assert output_flags.show_vibe == DEFAULT_CONFIG["show_vibe"]
    assert output_flags.warn_no_output == DEFAULT_CONFIG["warn_no_output"]
    assert output_flags.model_name == DEFAULT_MODEL


def test_configure_output_flags_raw_only() -> None:
    """Test configure_output_flags with raw flag only."""
    # Run with raw flag only
    output_flags = configure_output_flags(
        show_raw_output=True, show_vibe=False, model=DEFAULT_MODEL
    )

    # Verify flags
    assert output_flags.show_raw is True
    assert output_flags.show_vibe is False
    assert output_flags.warn_no_output == DEFAULT_CONFIG["warn_no_output"]
    assert output_flags.model_name == DEFAULT_MODEL


def test_configure_output_flags_vibe_only() -> None:
    """Test configure_output_flags with vibe flag only."""
    # Run with vibe flag only
    output_flags = configure_output_flags(
        show_raw_output=False, show_vibe=True, model=DEFAULT_MODEL
    )

    # Verify flags
    assert output_flags.show_raw is False
    assert output_flags.show_vibe is True
    assert output_flags.warn_no_output == DEFAULT_CONFIG["warn_no_output"]
    assert output_flags.model_name == DEFAULT_MODEL


def test_configure_output_flags_both_flags() -> None:
    """Test configure_output_flags with both flags enabled."""
    # Run with both flags
    output_flags = configure_output_flags(
        show_raw_output=True, show_vibe=True, model=DEFAULT_MODEL
    )

    # Verify flags
    assert output_flags.show_raw is True
    assert output_flags.show_vibe is True
    assert output_flags.warn_no_output == DEFAULT_CONFIG["warn_no_output"]
    assert output_flags.model_name == DEFAULT_MODEL


def test_configure_output_flags_with_show_kubectl() -> None:
    """Test configure_output_flags with show_kubectl flag."""
    # Test with show_kubectl set to True
    output_flags = configure_output_flags(show_kubectl=True)
    assert output_flags.show_kubectl is True

    # Test with show_kubectl set to False
    output_flags = configure_output_flags(show_kubectl=False)
    assert output_flags.show_kubectl is False


@patch("vibectl.command_handler.Config")
def test_configure_output_flags_with_show_kubectl_from_config(
    mock_config_class: MagicMock,
) -> None:
    """Test configure_output_flags uses show_kubectl from config when not specified."""
    # Mock Config to return True for show_kubectl
    mock_config = Mock()
    mock_config.get.side_effect = (
        lambda key, default: True if key == "show_kubectl" else default
    )
    mock_config_class.return_value = mock_config

    # Call with no show_kubectl flag - should use config value
    output_flags = configure_output_flags()
    assert output_flags.show_kubectl is True
    mock_config.get.assert_any_call("show_kubectl", DEFAULT_CONFIG["show_kubectl"])

    # Reset mock
    mock_config.reset_mock()

    # Call with explicit show_kubectl flag - should override config
    output_flags = configure_output_flags(show_kubectl=False)
    assert output_flags.show_kubectl is False


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


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler._get_llm_summary")
def test_handle_command_output_model_name_from_default(
    mock_get_summary: MagicMock, mock_processor: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output using default model name."""
    # Configure the mock
    mock_get_summary.return_value = "Test summary"

    # Set up processor mock
    mock_processor.process_auto.return_value = Truncation(
        original="test output", truncated="test output"
    )

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
    )

    # Call the function with vibe enabled - ensure complete mocking
    with (
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter,
        patch("vibectl.command_handler.update_memory"),
    ):
        # Configure model adapter
        mock_adapter = Mock()
        mock_adapter.get_model.return_value = Mock()
        mock_adapter.execute.return_value = "Test response"
        mock_get_adapter.return_value = mock_adapter

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )

    # Verify summary was called with correct arguments
    mock_get_summary.assert_called_once_with(
        "test output", DEFAULT_MODEL, "Summarize this: {output}"
    )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler._get_llm_summary")
def test_handle_command_output_basic(
    mock_get_summary: MagicMock, mock_processor: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test basic handle_command_output functionality."""
    # Configure the mock
    mock_get_summary.return_value = "Test summary"

    # Set up processor mock
    mock_processor.process_auto.return_value = Truncation(
        original="test output", truncated="test output"
    )

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
    )

    # Call the function with vibe enabled - ensure complete mocking
    with (
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter,
        patch("vibectl.command_handler.update_memory"),
    ):
        # Configure model adapter
        mock_adapter = Mock()
        mock_adapter.get_model.return_value = Mock()
        mock_adapter.execute.return_value = "Test response"
        mock_get_adapter.return_value = mock_adapter

        result = handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )

    # Check that correct parameters were passed
    mock_get_summary.assert_called_once_with(
        "test output", "test-model", "Summarize this: {output}"
    )

    # Check return value
    assert isinstance(result, Success)
    assert result.message == "Test summary"


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
        model_name=DEFAULT_MODEL,
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
        model_name=DEFAULT_MODEL,
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


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler._get_llm_summary")
def test_handle_command_output_llm_error(
    mock_get_summary: MagicMock,
    mock_processor: MagicMock,
    mock_llm: MagicMock,
    prevent_exit: MagicMock,
) -> None:
    """Test handle_command_output when LLM call raises an error."""
    # Configure mock LLM to raise an exception
    mock_get_summary.side_effect = Exception("LLM API Error")

    # Set up adapter mock to return an error
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = Error("Test error")
    mock_llm.return_value = mock_adapter

    # Create output flags with both outputs enabled
    output_flags = OutputFlags(
        show_raw=True, show_vibe=True, warn_no_output=True, model_name=DEFAULT_MODEL
    )

    # Call the function with both outputs enabled
    with patch("vibectl.command_handler.console_manager") as mock_console:
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Summarize this: {output}",
        )

        # Verify the error was logged and printed
        mock_console.print_error.assert_any_call(
            "Error getting Vibe summary: LLM API Error"
        )
