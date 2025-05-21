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
    LLMMetrics,
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
        current_memory: str | None = None,
    ) -> PromptFragments:
        return PromptFragments(
            (
                SystemFragments([Fragment("System: Summarize this with {output}")]),
                UserFragments([Fragment("User: {output}")]),
            )
        )

    return summary_prompt_fragments


@pytest.fixture
def mock_get_adapter() -> Generator[MagicMock, None, None]:
    """Mock LLMModelAdapter for command handling by mocking get_model_adapter."""
    mock_adapter_instance = MagicMock()

    with patch(
        "vibectl.command_handler.get_model_adapter", return_value=mock_adapter_instance
    ):
        yield mock_adapter_instance


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
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )


def test_handle_command_output_with_vibe_only(
    mock_get_adapter: MagicMock,
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
    mock_get_adapter.return_value = mock_adapter

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
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


def test_handle_command_output_both_outputs(
    mock_get_adapter: MagicMock,
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
    mock_get_adapter.return_value = mock_adapter

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
            output=Success(data="test output"),
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
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.output_processor")
def test_handle_command_output_empty_response(
    mock_output_processor: MagicMock,
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_get_adapter: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with empty LLM response."""
    # Explicitly configure the mock adapter for this test case
    mock_get_adapter.execute_and_log_metrics.return_value = (
        "",  # Empty string response from LLM
        LLMMetrics(token_input=1, token_output=1, latency_ms=10),  # Dummy metrics
    )

    # Set up output_processor mock
    mock_output_processor.process_auto.return_value = Truncation(
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

    # Call the function with vibe enabled
    handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )

    # Assertions
    mock_get_adapter.execute_and_log_metrics.assert_called_once()
    mock_console_manager.print_vibe.assert_not_called()

    mock_update_memory.assert_called_once_with(
        command_output="test output",
        vibe_output="",
        model_name=DEFAULT_MODEL,
        command_message="Unknown",
    )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_with_command(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output with vibe when a command is provided."""
    # mock_get_adapter IS the adapter instance from the fixture.
    # Configure its execute_and_log_metrics method directly.
    mock_get_adapter.execute_and_log_metrics.return_value = (
        "Vibe summary of the command.",
        LLMMetrics(
            token_input=5, token_output=10, latency_ms=50
        ),  # Return an LLMMetrics instance
    )

    # Set up output_processor mock
    mock_output_processor.process_auto.return_value = Truncation(
        original="test output", truncated="test output"
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,  # Vibe is enabled
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
        show_kubectl=True,
    )

    handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="get pods",
    )

    # Assertions
    mock_get_adapter.execute_and_log_metrics.assert_called_once()
    mock_update_memory.assert_called_once_with(
        command_message="get pods",
        command_output="test output",
        vibe_output="Vibe summary of the command.",
        model_name=DEFAULT_MODEL,
    )
    mock_console_manager.print_vibe.assert_called_once_with(
        "Vibe summary of the command."
    )


@patch("vibectl.command_handler.logger")
def test_configure_output_flags_no_flags(mock_config_constructor: MagicMock) -> None:
    """Test configure_output_flags with no flags, ensuring defaults are used."""

    mock_config_instance = MagicMock()
    # Make get_typed return the default value passed to it, simulating
    # config not having the key
    mock_config_instance.get_typed.side_effect = lambda key, default: default
    mock_config_constructor.return_value = mock_config_instance

    # Run without flags, should use internal Config() instance which is now mocked
    output_flags = configure_output_flags()

    # Verify defaults from DEFAULT_CONFIG are used
    assert output_flags.show_raw == DEFAULT_CONFIG["show_raw_output"]
    assert output_flags.show_vibe == DEFAULT_CONFIG["show_vibe"]
    assert output_flags.warn_no_output == DEFAULT_CONFIG["warn_no_output"]
    assert output_flags.model_name == DEFAULT_CONFIG["model"]
    assert output_flags.show_metrics == DEFAULT_CONFIG["show_metrics"]
    assert output_flags.show_kubectl == DEFAULT_CONFIG["show_kubectl"]
    assert output_flags.warn_no_proxy == DEFAULT_CONFIG["warn_no_proxy"]


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


def test_handle_command_output_model_name_from_config(
    mock_get_adapter: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with model name from config."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_get_adapter.return_value = mock_adapter

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
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


def test_handle_command_output_model_name_from_env(
    mock_get_adapter: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with model name from environment."""
    # Set up adapter mock
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = Mock()
    mock_adapter.execute.return_value = "Test response"
    mock_get_adapter.return_value = mock_adapter

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
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_model_name_from_default(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output using default model name."""
    # Explicitly configure the mock adapter for this test case
    mock_get_adapter.execute_and_log_metrics.return_value = (
        "LLM Summary",
        LLMMetrics(token_input=5, token_output=10, latency_ms=20),  # Dummy metrics
    )

    mock_output_processor.process_auto.return_value = Truncation(
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

    handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )

    # Verify summary was called with correct arguments including the default model name
    mock_get_adapter.execute_and_log_metrics.assert_called_once()
    # Check that get_model was called with the default model name
    mock_get_adapter.get_model.assert_called_with(DEFAULT_MODEL)
    mock_console_manager.print_vibe.assert_called_once_with("LLM Summary")
    mock_update_memory.assert_called_once()


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
def test_handle_command_output_basic(
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test basic functioning of handle_command_output with vibe enabled."""
    # Explicitly configure the mock adapter for this test case
    mock_get_adapter.execute_and_log_metrics.return_value = (
        "LLM Summary",
        LLMMetrics(token_input=7, token_output=15, latency_ms=25),  # Dummy metrics
    )

    output_flags = OutputFlags(
        show_vibe=True,
        model_name="test-model",
        show_raw=False,
        warn_no_output=True,
        show_metrics=True,
    )
    with patch("vibectl.command_handler.update_memory") as mock_update_memory:
        mock_output_processor.process_auto.return_value = Truncation("output", "output")
        handle_command_output(
            output=Success(data="output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )
        mock_get_adapter.execute_and_log_metrics.assert_called_once()
        mock_update_memory.assert_called_once()
        mock_console_manager.print_vibe.assert_called_once_with("LLM Summary")


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
def test_handle_command_output_raw(
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output with raw output only: no vibe memory update."""
    # Setup mock adapter for memory update summary
    mock_adapter_instance = MagicMock()
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model.return_value = mock_model_instance
    mock_adapter_instance.execute_and_log_metrics.return_value = (
        "LLM Summary for memory",
        None,
    )
    mock_get_adapter.return_value = mock_adapter_instance

    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=False,
        model_name="test-model",
        warn_no_output=True,
        show_metrics=True,
    )
    with patch("vibectl.command_handler.update_memory") as mock_update_memory:
        mock_output_processor.process_auto.return_value = Truncation("output", "output")
        handle_command_output(
            output=Success(data="output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )
        # If show_vibe is False, no LLM call for summarization occurs
        # in handle_command_output
        mock_get_adapter.execute_and_log_metrics.assert_not_called()
        # If show_vibe is False, update_memory is also not called by
        # handle_command_output
        mock_update_memory.assert_not_called()
        mock_console_manager.print_raw.assert_called_once_with("output")


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
def test_handle_command_output_no_vibe(
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output with show_vibe=False (memory update still happens)."""
    # Setup mock adapter for memory update summary
    mock_adapter_instance = MagicMock()
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model.return_value = mock_model_instance
    mock_adapter_instance.execute_and_log_metrics.return_value = (
        "LLM Summary for memory",
        None,
    )
    mock_get_adapter.return_value = mock_adapter_instance

    output_flags = OutputFlags(
        show_vibe=False,
        model_name="test-model",
        show_raw=True,
        warn_no_output=True,
        show_metrics=True,
    )
    with patch("vibectl.command_handler.update_memory") as mock_update_memory:
        mock_output_processor.process_auto.return_value = Truncation("output", "output")
        handle_command_output(
            output=Success(data="output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )
        # If show_vibe is False, no LLM call for summarization occurs
        # in handle_command_output
        mock_get_adapter.execute_and_log_metrics.assert_not_called()
        # If show_vibe is False, update_memory is also not called by
        # handle_command_output
        mock_update_memory.assert_not_called()
        mock_console_manager.print_raw.assert_called_once_with("output")


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_process_vibe_output_with_autonomous_prompt_no_index_error(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test _process_vibe_output with autonomous prompt does not cause IndexError."""
    # Explicitly configure the mock adapter for this test case
    mock_get_adapter.execute_and_log_metrics.return_value = (
        "Autonomous Action Executed",
        LLMMetrics(token_input=10, token_output=30, latency_ms=50),  # Dummy metrics
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_metrics=True,
    )

    summary_system_fragments, summary_user_fragments = vibe_autonomous_prompt(
        config=None
    )

    mock_output_processor.process_auto.return_value = Truncation(
        original="Sample kubectl output", truncated="Sample kubectl output"
    )

    try:
        result = _process_vibe_output(
            output_message="Vibe summary based on output:",
            output_data="Sample kubectl output",
            output_flags=output_flags,
            summary_system_fragments=summary_system_fragments,
            summary_user_fragments=summary_user_fragments,
            command="get pods",
        )
        assert isinstance(result, Success)
        assert result.message == "Autonomous Action Executed"
        assert result.data is None
        mock_get_adapter.execute_and_log_metrics.assert_called_once()
        _, call_kwargs = mock_get_adapter.execute_and_log_metrics.call_args

        # SystemFragments and UserFragments are NewTypes wrapping list[Fragment]
        # Fragment is TypeAlias = str. So these are effectively list[str].
        assert isinstance(call_kwargs.get("system_fragments"), list)
        assert isinstance(call_kwargs.get("user_fragments"), list)

        # The fragments passed to execute_and_log_metrics should have
        # {output} formatted.
        # vibe_autonomous_prompt defines the templates.
        # _process_vibe_output applies .format(output=processed_output)
        # to these templates.

        formatted_user_fragments_received = call_kwargs.get("user_fragments", [])

        # Check if the actual output string is present in any of the
        # received user fragments.
        assert any(
            "Sample kubectl output" in frag
            for frag in formatted_user_fragments_received
        ), "Expected 'Sample kubectl output' to be in the formatted user fragments."

        # Check that the placeholder {output} is no longer present.
        assert not any(
            "{output}" in frag for frag in formatted_user_fragments_received
        ), "Placeholder '{output}' should have been replaced in user fragments."

        # Similarly for system fragments, if {output} could be there.
        # vibe_autonomous_prompt typically doesn't put {output} in system fragments.
        formatted_system_fragments_received = call_kwargs.get("system_fragments", [])
        assert not any(
            "{output}" in frag for frag in formatted_system_fragments_received
        ), (
            "Placeholder '{output}' should not be in system fragments or "
            "have been replaced."
        )

    except IndexError as e:
        pytest.fail(f"_process_vibe_output raised an IndexError: {e}")


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_llm_error(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output when LLM summarization fails."""
    # mock_get_adapter is the adapter instance. Configure it directly.
    error_message = "ERROR: LLM failed to summarize"
    mock_get_adapter.execute_and_log_metrics.return_value = (error_message, None)

    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_metrics=True,
    )
    mock_output_processor.process_auto.return_value = Truncation(
        original="test output", truncated="test output"
    )

    handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )

    mock_get_adapter.execute_and_log_metrics.assert_called_once()
    # _process_vibe_output directly prints the LLM's error string
    # if it starts with "ERROR:"
    mock_console_manager.print_error.assert_any_call(
        error_message  # Expecting the raw "ERROR: LLM failed to summarize"
    )
    # If _process_vibe_output encounters an "ERROR:" string from the LLM,
    # it returns an Error object and does NOT call update_memory.
    mock_update_memory.assert_not_called()


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_error_input_no_vibe(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output with error input and show_vibe=False."""
    # If show_vibe is False, no LLM calls will be made by handle_command_output
    # directly, and update_memory will also not be called from within
    # handle_command_output. So, mock_get_adapter.execute_and_log_metrics
    # should not be configured or asserted here.

    error_data = "Error: Something went wrong."
    error_input = Error(error=error_data, exception=RuntimeError(error_data))
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
    )
    mock_output_processor.process_auto.return_value = Truncation(
        original=error_data, truncated=error_data
    )

    result = handle_command_output(
        output=error_input,
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="test-error-command",
    )

    assert isinstance(result, Error)
    assert result.error == error_data
    mock_console_manager.print_error.assert_called_with(error_data)

    # Assert that no LLM call for vibe/recovery or memory update happened
    # because show_vibe=False
    mock_get_adapter.execute_and_log_metrics.assert_not_called()
    mock_update_memory.assert_not_called()


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
def test_handle_command_output_error_input_with_vibe_recovery(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output with error input and vibe recovery."""
    # mock_get_adapter is the adapter instance. Configure it directly.

    expected_recovery_suggestion_text = "Checking events."  # Plain text suggestion
    # LLM is called once for recovery suggestion.
    # Metrics are associated with this recovery call.
    mock_get_adapter.execute_and_log_metrics.return_value = (
        expected_recovery_suggestion_text,
        LLMMetrics(token_input=10, token_output=20, latency_ms=100),
    )

    error_data = "Error: Pod not found."
    error_input = Error(error=error_data, exception=RuntimeError(error_data))
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
        show_kubectl=True,
    )
    mock_output_processor.process_auto.return_value = Truncation(
        original=error_data, truncated=error_data
    )

    with patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt_func:
        mock_recovery_prompt_func.return_value = (
            SystemFragments([Fragment("System Prompt")]),
            UserFragments([Fragment("User Prompt")]),
        )

        result = handle_command_output(
            output=error_input,
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
            command="test-recovery-command",
        )

    assert isinstance(result, Error)
    assert result.error == error_data
    # recovery_suggestions should now be the plain text from the LLM
    assert result.recovery_suggestions == expected_recovery_suggestion_text

    # LLM is called ONCE for recovery suggestion.
    assert mock_get_adapter.execute_and_log_metrics.call_count == 1

    mock_console_manager.print_error.assert_called_once_with(error_data)
    # The plain text recovery suggestion is printed by print_vibe
    mock_console_manager.print_vibe.assert_any_call(expected_recovery_suggestion_text)

    # update_memory is called with the error_data and the plain text recovery_suggestion
    mock_update_memory.assert_called_once_with(
        command_output=error_data,
        vibe_output=expected_recovery_suggestion_text,
        model_name="test-model",
        command_message="test-recovery-command",
    )
