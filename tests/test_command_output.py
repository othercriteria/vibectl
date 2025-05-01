"""Tests for command output handling functionality."""

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    Error,
    OutputFlags,
    _process_vibe_output,
    configure_output_flags,
    handle_command_output,
)
from vibectl.config import DEFAULT_CONFIG
from vibectl.prompt import vibe_autonomous_prompt
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
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.update_memory")
def test_process_vibe_output_with_autonomous_prompt_no_index_error(
    mock_update_memory: MagicMock,
    mock_output_processor: MagicMock,
    mock_console_manager: MagicMock,
    mock_get_model_adapter: MagicMock,
    prevent_exit: MagicMock,
) -> None:
    """
    Test that _process_vibe_output doesn't raise IndexError when using
    vibe_autonomous_prompt due to incorrect placeholder formatting (`{{output}}`).

    This test verifies that the prompt string generated by vibe_autonomous_prompt
    can be correctly formatted with the 'output' keyword argument later in the
    _get_llm_summary function, which is called by _process_vibe_output.
    """
    output_str = "Sample kubectl output"
    # Provide all required args for OutputFlags
    output_flags = OutputFlags(
        show_raw=False,  # Don't need raw output for this test
        show_vibe=True,  # Need vibe to trigger the code path
        warn_no_output=True,  # Standard default
        model_name="test-model",
    )
    # Use the actual vibe_autonomous_prompt function
    summary_prompt_func = vibe_autonomous_prompt
    # Get the prompt string template - this is where the fix needs to be correct
    # If the original bug ({{output}}) exists, the .format call inside
    # _get_llm_summary will fail later.
    summary_prompt_str = summary_prompt_func()

    # Mock the LLM call part
    mock_model_adapter = MagicMock()
    mock_model = MagicMock()
    mock_get_model_adapter.return_value = mock_model_adapter
    mock_model_adapter.get_model.return_value = mock_model
    mock_model_adapter.execute.return_value = (
        "Mocked LLM Summary"  # This is returned by _get_llm_summary
    )

    # Mock the output processor return value
    mock_output_processor.process_auto.return_value = Truncation(
        original=output_str, truncated=output_str
    )

    try:
        # Call the function that internally calls _get_llm_summary
        # _get_llm_summary contains the failing .format(output=...) call if prompt wrong
        result = _process_vibe_output(
            output=output_str,
            output_flags=output_flags,
            # Pass the potentially problematic string
            summary_prompt_str=summary_prompt_str,
            command="get pods",  # Example command context
            original_error_object=None,
        )

        # Assertions to ensure the flow completed correctly
        assert isinstance(result, Success)
        assert result.message == "Mocked LLM Summary"

        # Verify the LLM execute was called (meaning formatting succeeded)
        mock_model_adapter.execute.assert_called_once()
        # Check the formatted prompt passed to the LLM execute call
        call_args, _ = mock_model_adapter.execute.call_args
        final_prompt_used = call_args[1]  # Second argument is the prompt text

        # Check that the output was correctly inserted
        assert output_str in final_prompt_used
        # Check that the literal placeholder {output} is NOT present
        assert "{output}" not in final_prompt_used
        # Check that the double braces {{}} used for escaping are NOT present
        assert "{{" not in final_prompt_used
        # Check that formatting instructions were included
        # (implicitly tested by presence of output_str)

    except IndexError as e:
        # This block will be hit if the original buggy code (`{{output}}`) is present
        # in vibe_autonomous_prompt, because .format(output=...) will fail.
        pytest.fail(
            f"IndexError raised during prompt formatting in _get_llm_summary: {e}. "
            "Check vibe_autonomous_prompt in prompt.py for {{output}} vs {output}."
        )
    except Exception as e:
        # Catch any other unexpected errors
        pytest.fail(f"An unexpected error occurred: {e}")


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


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_error_input_no_vibe(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: Callable[[], str],
) -> None:
    """Test handle_command_output with Error input and show_vibe=False."""
    test_exception = RuntimeError("Original Error")
    error_input = Error(error="Command failed", exception=test_exception)
    output_flags = OutputFlags(
        show_raw=False,  # Doesn't matter for this test
        show_vibe=False,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
    )

    result = handle_command_output(
        output=error_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )

    # Verify the original error object is returned directly
    assert result is error_input
    # Verify no LLM calls were made
    mock_get_adapter.assert_not_called()
    # Verify no memory update
    mock_update_memory.assert_not_called()
    # Verify error was printed
    mock_console.print_error.assert_called_with(error_input.error)


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_error_input_with_vibe_recovery(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: Callable[[], str],
) -> None:
    """Test handle_command_output with Error input, show_vibe=True, and
    successful recovery."""
    test_exception = RuntimeError("Original Error")
    error_input = Error(error="Command failed badly", exception=test_exception)
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
    )

    # Mock the LLM call for recovery
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute.return_value = "Try restarting the pod."

    result = handle_command_output(
        output=error_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,  # Not used for recovery path
        command="test-command",
    )

    # Verify the result is the original Error object, but modified
    assert isinstance(result, Error)
    assert result is error_input
    assert result.recovery_suggestions == "Try restarting the pod."
    # Verify LLM was called (for recovery)
    mock_adapter.execute.assert_called_once()
    # Verify memory was updated with error and suggestion
    mock_update_memory.assert_called_once_with(
        command="test-command",
        command_output="Command failed badly",
        vibe_output="Try restarting the pod.",
        model_name=DEFAULT_MODEL,
    )
    # Verify original error and suggestion were printed
    mock_console.print_error.assert_called_with(error_input.error)
    mock_console.print_vibe.assert_called_with("Try restarting the pod.")


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_error_input_with_vibe_recoverable_api_error(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: Callable[[], str],
) -> None:
    """Test handle_command_output with Error input, show_vibe=True, and
    RecoverableApiError during recovery."""
    from vibectl.model_adapter import RecoverableApiError

    test_exception = RuntimeError("Original Error")
    error_input = Error(error="Command failed badly", exception=test_exception)
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
    )

    # Mock the LLM call for recovery to raise RecoverableApiError
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    api_error = RecoverableApiError("API Overloaded")
    mock_adapter.execute.side_effect = api_error

    result = handle_command_output(
        output=error_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="test-command",
    )

    # Verify the result is a *new* Error object representing the API error
    assert isinstance(result, Error)
    assert result is not error_input
    assert result.error == "API Error: API Overloaded"
    assert result.exception == api_error
    assert result.halt_auto_loop is False  # Key check for recoverable errors
    # Verify LLM was called
    mock_adapter.execute.assert_called_once()
    # Verify memory was NOT updated because Vibe failed
    mock_update_memory.assert_not_called()
    # Verify original error and API error were printed
    mock_console.print_error.assert_any_call(error_input.error)
    mock_console.print_error.assert_any_call("API Error: API Overloaded")


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_error_input_with_vibe_generic_error(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: Callable[[], str],
) -> None:
    """Test handle_command_output with Error input, show_vibe=True, and generic
    Exception during recovery."""
    test_exception = RuntimeError("Original Error")
    error_input = Error(error="Command failed badly", exception=test_exception)
    generic_exception = TimeoutError("LLM timed out")
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
    )

    # Mock the LLM call for recovery to raise generic Exception
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute.side_effect = generic_exception

    result = handle_command_output(
        output=error_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="test-command",
    )

    # Verify the result is a new Error combining original and Vibe error
    assert isinstance(result, Error)
    assert result is not error_input
    expected_error_msg = (
        f"Original Error: {error_input.error}\n"
        f"Vibe Failure: Error getting Vibe summary: {generic_exception}"
    )
    assert result.error == expected_error_msg
    # Exception should be the original one if present, otherwise the vibe one
    assert result.exception == test_exception
    assert result.halt_auto_loop is True  # Should be halting
    # Verify LLM was called
    mock_adapter.execute.assert_called_once()
    # Verify memory was NOT updated
    mock_update_memory.assert_not_called()
    # Verify original error and Vibe failure error were printed
    mock_console.print_error.assert_any_call(error_input.error)
    mock_console.print_error.assert_any_call(
        f"Error getting Vibe summary: {generic_exception}"
    )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler._get_llm_summary")  # Mock the summary function directly
def test_handle_command_output_success_input_with_vibe_recoverable_api_error(
    mock_get_llm_summary: MagicMock,
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: Callable[[], str],
) -> None:
    """Test handle_command_output with success input, show_vibe=True, and
    RecoverableApiError during summary."""
    from vibectl.model_adapter import RecoverableApiError

    success_input = Success(data="Good output")
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
    )
    mock_output_processor.process_auto.return_value = Truncation(
        original="Good output", truncated="Processed good output"
    )

    # Mock the LLM summary call to raise RecoverableApiError
    api_error = RecoverableApiError("API Key Invalid")
    mock_get_llm_summary.side_effect = api_error

    result = handle_command_output(
        output=success_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="test-command",
    )

    # Verify the result is an Error object representing the API error
    assert isinstance(result, Error)
    assert result.error == "API Error: API Key Invalid"
    assert result.exception == api_error
    assert result.halt_auto_loop is False
    # Verify LLM summary func was called
    mock_get_llm_summary.assert_called_once()
    # Verify memory was NOT updated
    mock_update_memory.assert_not_called()
    # Verify API error was printed
    mock_console.print_error.assert_called_with("API Error: API Key Invalid")


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler._get_llm_summary")  # Mock the summary function directly
def test_handle_command_output_success_input_with_vibe_generic_error(
    mock_get_llm_summary: MagicMock,
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: Callable[[], str],
) -> None:
    """Test handle_command_output with success input, show_vibe=True, and generic
    Exception during summary."""
    success_input = Success(data="Good output")
    generic_exception = ValueError("Something went wrong during summary")
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
    )
    mock_output_processor.process_auto.return_value = Truncation(
        original="Good output", truncated="Processed good output"
    )

    # Mock the LLM summary call to raise generic Exception
    mock_get_llm_summary.side_effect = generic_exception

    result = handle_command_output(
        output=success_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="test-command",
    )

    # Verify the result is an Error object representing the Vibe summary failure
    assert isinstance(result, Error)
    expected_error_msg = f"Error getting Vibe summary: {generic_exception}"
    assert result.error == expected_error_msg
    assert result.exception == generic_exception
    assert result.halt_auto_loop is True  # Should be halting
    # Verify LLM summary func was called
    mock_get_llm_summary.assert_called_once()
    # Verify memory was NOT updated
    mock_update_memory.assert_not_called()
    # Verify Vibe failure error was printed
    mock_console.print_error.assert_called_with(expected_error_msg)
