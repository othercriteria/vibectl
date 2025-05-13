"""Tests for command output handling functionality."""

from collections.abc import Generator
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
from vibectl.config import DEFAULT_CONFIG, Config
from vibectl.prompt import vibe_autonomous_prompt
from vibectl.types import (
    Fragment,
    PromptFragments,
    Success,
    SummaryPromptFragmentFunc,
    SystemFragments,
    Truncation,
    UserFragments,
)

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
def default_summary_prompt() -> SummaryPromptFragmentFunc:
    """Create a default summary prompt function that returns fragments."""

    def summary_prompt_fragments(
        config: Config | None = None,
    ) -> PromptFragments:
        return PromptFragments(
            (
                SystemFragments([Fragment("System: Summarize this with {output}")]),
                UserFragments([Fragment("User: {output}")]),
            )
        )

    return summary_prompt_fragments


def test_handle_command_output_with_raw_output_only(
    prevent_exit: MagicMock, default_summary_prompt: SummaryPromptFragmentFunc
) -> None:
    """Test handle_command_output with raw output only."""
    # Create output flags with raw output only
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
    )

    # Call the function with only raw output enabled
    handle_command_output(
        output="test output",
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_with_vibe_only(
    mock_llm: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with vibe output only."""
    # Configure mock LLM response
    mock_get_summary = MagicMock()
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
        show_metrics=True,
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
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_both_outputs(
    mock_llm: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with both outputs."""
    # Configure mock LLM response
    mock_get_summary = MagicMock()
    mock_get_summary.return_value = "Test response"

    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_llm.return_value = mock_adapter

    # Create output flags with both outputs enabled
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
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
            summary_prompt_func=default_summary_prompt,
        )


def test_handle_command_output_no_output(
    prevent_exit: MagicMock, default_summary_prompt: SummaryPromptFragmentFunc
) -> None:
    """Test handle_command_output with no outputs enabled."""
    # Create output flags with no outputs
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
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
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_command_output_empty_response(
    mock_console_manager: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with empty LLM response."""
    # Configure mock LLM response
    mock_get_summary = MagicMock()
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
        show_metrics=True,
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
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_with_command(
    mock_processor: MagicMock,
    mock_llm: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with command parameter."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute_and_log_metrics.return_value = ("Test response", None)
    mock_llm.return_value = mock_adapter

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
    )

    # Call the function with command parameter
    with (
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
    ):
        # Configure processor mock
        mock_processor.process_auto.return_value = Truncation(
            original="test output", truncated="test output"
        )

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
            command="get pods",
        )

        # Verify mocks
        mock_update_memory.assert_called_once()
        # Assert print_vibe was called on the console manager mock
        mock_console.print_vibe.assert_called_once_with("Test response")


def test_configure_output_flags_no_flags() -> None:
    """Test configure_output_flags with no flags."""
    # Run without flags
    output_flags = configure_output_flags()

    # Verify defaults
    assert output_flags.show_raw == DEFAULT_CONFIG["show_raw_output"]
    assert output_flags.show_vibe == DEFAULT_CONFIG["show_vibe"]
    assert output_flags.warn_no_output == DEFAULT_CONFIG["warn_no_output"]
    assert output_flags.model_name == DEFAULT_MODEL
    assert output_flags.show_metrics == DEFAULT_CONFIG["show_metrics"]


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
    assert output_flags.show_metrics == DEFAULT_CONFIG["show_metrics"]


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
    assert output_flags.show_metrics == DEFAULT_CONFIG["show_metrics"]


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
    assert output_flags.show_metrics == DEFAULT_CONFIG["show_metrics"]


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
    mock_llm: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
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
        show_metrics=True,
    )

    # Call the function with model name from config
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_model_name_from_env(
    mock_llm: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
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
        show_metrics=True,
    )

    # Call the function with model name from env
    with patch("vibectl.command_handler.console_manager"):
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.console_manager")
def test_handle_command_output_model_name_from_default(
    mock_console_manager: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output using default model name."""
    # Configure the mock
    # mock_get_summary = MagicMock() # Removed unused mock
    # mock_get_summary.return_value = "Test summary" # Removed unused mock

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
        show_metrics=True,
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
        # Ensure execute_and_log_metrics returns a tuple (text, metrics)
        mock_adapter.execute_and_log_metrics.return_value = ("Test response", None)
        # mock_adapter.execute.return_value = "Test response" # Old mock setup
        mock_get_adapter.return_value = mock_adapter

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )

        # Verify summary was called with correct arguments
        # mock_get_summary.assert_called_once_with( # Removed assertion on unused mock
        #     "test output", DEFAULT_MODEL, "Summarize this: {output}"
        # )
        # Assert that the correct adapter method was called
        mock_adapter.execute_and_log_metrics.assert_called_once()


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_basic(
    mock_get_adapter: MagicMock,
    mock_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test basic handle_command_output functionality."""
    # Configure the mock adapter instance provided by the mock_get_adapter fixture
    mock_adapter_instance = mock_get_adapter.return_value
    mock_adapter_instance.get_model.return_value = MagicMock()
    mock_adapter_instance.execute_and_log_metrics.return_value = ("Test summary", None)

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
        show_metrics=True,
    )

    # Call the function with vibe enabled - mock console and memory update
    with (
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.update_memory"),
    ):
        result = handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )

    # Check that execute_and_log_metrics was called on the adapter instance
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()

    # Check return value
    assert isinstance(result, Success)
    assert result.message == "Test summary"


# Helper function for dummy prompt fragments
def get_dummy_prompt_fragments(config: Config | None = None) -> PromptFragments:
    """Returns a dummy PromptFragments object for testing."""
    # The actual content doesn't matter much for these tests,
    # as long as the type is correct.
    return PromptFragments(
        (
            SystemFragments([Fragment("System dummy")]),
            UserFragments([Fragment("User dummy: {output}")]),
        )
    )


@patch("vibectl.command_handler.get_model_adapter")
def test_handle_command_output_raw(
    mock_llm: MagicMock, prevent_exit: MagicMock
) -> None:
    """Test handle_command_output with raw output enabled."""
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,  # Corrected: test for raw output, vibe should be False
        # initially for this specific test's original intent
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
    )
    with (
        patch("vibectl.command_handler.output_processor") as mock_processor,
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch("vibectl.command_handler.update_memory"),  # Mock update_memory
    ):
        # Set up output processor mock
        mock_processor.process_auto.return_value = ("processed output", False)

        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=get_dummy_prompt_fragments,
        )

        # Verify raw output was shown
        mock_console.print_raw.assert_called_once_with("test output")
        # Verify Vibe related mocks NOT called when show_vibe=False
        mock_llm.assert_not_called()


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
        show_metrics=True,
    )

    # Call the function
    with patch("vibectl.command_handler.console_manager") as mock_console:
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=get_dummy_prompt_fragments,
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
        show_metrics=True,
    )
    # Use the actual vibe_autonomous_prompt function
    summary_prompt_func = vibe_autonomous_prompt
    # Get the prompt fragments - THIS is where the fix happens
    summary_system_fragments, summary_user_fragments = summary_prompt_func(config=None)

    # Mock the LLM call part
    mock_model_adapter = MagicMock()
    mock_model = MagicMock()
    mock_get_model_adapter.return_value = mock_model_adapter
    mock_model_adapter.get_model.return_value = mock_model
    mock_model_adapter.execute_and_log_metrics.return_value = (
        "Mocked LLM Summary",
        None,
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
            # Pass the fragments instead of the string
            summary_system_fragments=summary_system_fragments,
            summary_user_fragments=summary_user_fragments,
            command="get pods",  # Example command context
            original_error_object=None,
        )

        # Assertions to ensure the flow completed correctly
        assert isinstance(result, Success)
        assert result.message == "Mocked LLM Summary"

        # Verify the LLM execute_and_log_metrics was called
        mock_model_adapter.execute_and_log_metrics.assert_called_once()
        # Check the formatted prompt passed to the LLM execute call
        # Arguments are (self, model, system_fragments, user_fragments, response_model)
        # Passed as kwargs, so check call_kwargs
        _, call_kwargs = mock_model_adapter.execute_and_log_metrics.call_args
        # final_prompt_used = call_args[1]  # Old check assuming positional args

        # Reconstruct the prompt from fragments for checking content
        system_fragments_used = call_kwargs.get("system_fragments", [])
        user_fragments_used = call_kwargs.get("user_fragments", [])
        full_prompt_text_simulated = "\\n".join(
            system_fragments_used + user_fragments_used
        )

        # Check that the output was correctly inserted
        assert output_str in full_prompt_text_simulated
        # Check that the literal placeholder {output} is NOT present
        assert "{output}" not in full_prompt_text_simulated
        # Check that the double braces {{}} used for escaping are NOT present
        assert "{{" not in full_prompt_text_simulated
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
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_llm_error(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output when LLM call raises an error."""
    # Configure mock LLM to raise an exception
    # mock_get_summary = MagicMock() # Removed unused mock
    # mock_get_summary.side_effect = Exception("LLM API Error") # Removed unused mock

    # Set up adapter mock to raise the exception
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    # Set side_effect on the correct method
    llm_exception = Exception("LLM API Error")
    mock_adapter.execute_and_log_metrics.side_effect = llm_exception
    # mock_adapter.execute.return_value = Error("Test error") # Old/incorrect mock setup
    mock_get_adapter.return_value = mock_adapter

    # Create output flags with both outputs enabled
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
    )

    # Call the function with both outputs enabled
    with patch("vibectl.command_handler.console_manager") as mock_console:
        handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda config_param: PromptFragments(
                (
                    SystemFragments([]),
                    UserFragments(
                        [Fragment("Error getting Vibe summary: LLM API Error")]
                    ),
                )
            )
            if config_param is None or isinstance(config_param, Config)
            else PromptFragments((SystemFragments([]), UserFragments([]))),
        )

        # Verify the error was logged and printed
        mock_console.print_error.assert_any_call(
            f"Error getting Vibe summary: {llm_exception}"
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
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with Error input and show_vibe=False."""
    test_exception = RuntimeError("Original Error")
    error_input = Error(error="Command failed", exception=test_exception)
    output_flags = OutputFlags(
        show_raw=False,  # Doesn't matter for this test
        show_vibe=False,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
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
    default_summary_prompt: SummaryPromptFragmentFunc,
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
        show_metrics=True,
    )

    # Mock the LLM call for recovery
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute_and_log_metrics.return_value = (
        "Try restarting the pod.",
        None,
    )

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
    mock_adapter.execute_and_log_metrics.assert_called_once()
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
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_error_input_with_vibe_recoverable_api_error(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
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
        show_metrics=True,
    )

    # Mock the LLM call for recovery to raise RecoverableApiError
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    api_error = RecoverableApiError("API Overloaded")
    mock_adapter.execute_and_log_metrics.side_effect = api_error

    result = handle_command_output(
        output=error_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="test-command",
    )

    # Verify the result is the *original* Error object, modified
    assert isinstance(result, Error)
    assert result is error_input  # Should return the same object instance
    assert "API Overloaded" in (result.recovery_suggestions or "")
    assert result.halt_auto_loop is True  # Recovery failed, should still halt

    # Verify console output
    mock_console.print_error.assert_any_call("Command failed badly")
    mock_console.print_vibe.assert_called_once_with(
        "Failed to get recovery suggestions: API Overloaded"
    )
    # Verify memory update called with failure
    mock_output_processor.assert_called_once()
    # mem_kwargs = mock_update_memory.call_args.kwargs
    # assert mem_kwargs["command_output"] == "Command failed badly"


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_error_input_with_vibe_generic_error(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
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
        show_metrics=True,
    )

    # Mock the LLM call for recovery to raise generic Exception
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute_and_log_metrics.side_effect = generic_exception

    result = handle_command_output(
        output=error_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="test-command",
    )

    # Verify the result is the *original* Error object, modified
    assert isinstance(result, Error)
    assert result is error_input  # Should return the same object instance
    assert "LLM timed out" in (result.recovery_suggestions or "")
    assert result.halt_auto_loop is True  # Recovery failed, should still halt

    # Verify console output
    mock_console.print_error.assert_any_call("Command failed badly")
    mock_console.print_vibe.assert_called_once_with(
        f"Failed to get recovery suggestions: {generic_exception}"
    )

    # Verify memory update called with failure
    mock_output_processor.assert_called_once()
    # mem_kwargs = mock_update_memory.call_args.kwargs
    # assert mem_kwargs["command_output"] == "Command failed badly"


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_success_input_with_vibe_recoverable_api_error(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
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
        show_metrics=True,
    )
    mock_output_processor.process_auto.return_value = Truncation(
        original="Good output", truncated="Processed good output"
    )

    # Mock the LLM summary call to raise RecoverableApiError
    api_error = RecoverableApiError("API Key Invalid")
    # mock_get_summary = MagicMock() # Removed unused mock
    # mock_get_summary.side_effect = api_error # Removed unused mock

    # Call the function within the patch context to ensure mocks are active
    with patch("vibectl.command_handler.console_manager") as mock_console:
        # Set up adapter mock inside the context
        mock_adapter = Mock()
        mock_model = Mock()
        mock_get_adapter.return_value = mock_adapter
        mock_adapter.get_model.return_value = mock_model
        mock_adapter.execute_and_log_metrics.side_effect = (
            api_error  # Set side_effect here
        )

        result = handle_command_output(
            output=success_input,
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
            command="test-command",
        )

    # Verify the result is an Error object representing the API error
    assert isinstance(result, Error)
    assert (
        result.error == "Recoverable API error during Vibe processing: API Key Invalid"
    )
    assert result.exception == api_error
    assert result.halt_auto_loop is False
    # Verify LLM summary func was called
    mock_adapter.execute_and_log_metrics.assert_called_once()
    # Verify memory was NOT updated
    mock_update_memory.assert_not_called()
    # Verify API error was printed
    mock_console.print_error.assert_called_with(f"API Error: {api_error}")


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_success_input_with_vibe_generic_error(
    mock_output_processor: MagicMock,
    mock_console: MagicMock,
    mock_update_memory: MagicMock,
    mock_get_adapter: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
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
        show_metrics=True,
    )
    mock_output_processor.process_auto.return_value = Truncation(
        original="Good output", truncated="Processed good output"
    )

    # Mock the LLM summary call to raise generic Exception
    # mock_get_summary = MagicMock() # Removed unused mock
    # mock_get_summary.side_effect = generic_exception # Removed unused mock

    # Call the function within the patch context
    with patch("vibectl.command_handler.console_manager") as mock_console:
        # Set up adapter mock inside the context
        mock_adapter = Mock()
        mock_model = Mock()
        mock_get_adapter.return_value = mock_adapter
        mock_adapter.get_model.return_value = mock_model
        mock_adapter.execute_and_log_metrics.side_effect = (
            generic_exception  # Set side_effect here
        )

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
    mock_adapter.execute_and_log_metrics.assert_called_once()
    # Verify memory was NOT updated
    mock_update_memory.assert_not_called()
    # Verify Vibe failure error was printed
    mock_console.print_error.assert_called_with(expected_error_msg)
