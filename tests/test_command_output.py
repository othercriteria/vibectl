"""Tests for command output handling functionality."""

from collections.abc import AsyncIterator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

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


async def test_handle_command_output_with_raw_output_only(
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
    await handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )


async def test_handle_command_output_with_vibe_only(
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
        await handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


async def test_handle_command_output_both_outputs(
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
        await handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )


@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.output_processor")
async def test_handle_command_output_empty_response(
    mock_output_processor: MagicMock,
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_get_adapter: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
) -> None:
    """Test handle_command_output with empty LLM response when streaming."""

    expected_llm_response_text = ""
    # In the current streaming path of _process_vibe_output, metrics are initialized
    # as LLMMetrics() and not updated from the stream itself for update_memory.
    # expected_metrics_for_update_memory = LLMMetrics()

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield expected_llm_response_text
        # Keep Pyright happy about yielding
        if False:
            yield

    # Mock stream_execute as this is the expected path now
    mock_get_adapter.stream_execute = MagicMock(return_value=mock_stream_return_async())
    # Also mock execute_and_log_metrics to assert it's NOT called
    mock_get_adapter.execute_and_log_metrics = MagicMock(
        return_value=(
            "Non-streamed response",
            LLMMetrics(token_input=1, token_output=1, latency_ms=1),
        )
    )  # Provide a default return for it, though it shouldn't be called.

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
    await handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )

    # Assertions
    mock_get_adapter.stream_execute.assert_called_once()
    mock_get_adapter.execute_and_log_metrics.assert_not_called()
    # For an empty LLM response, the live vibe panel might start but
    # then stop with empty content.
    # print_vibe (final panel) should not be called if the response is empty.
    mock_console_manager.print_vibe.assert_not_called()

    # update_memory is called once from _process_vibe_output without a metrics arg
    mock_update_memory.assert_called_once_with(
        command_output="test output",
        vibe_output=expected_llm_response_text,  # which is ""
        model_name=DEFAULT_MODEL,
        command_message="Unknown",
    )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
async def test_handle_command_output_with_command(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output with vibe when a command is provided and streaming."""
    expected_llm_response_text = "Vibe summary of the command."
    # Metrics will be default LLMMetrics() due to current streaming path logic
    # expected_metrics_for_update_memory = LLMMetrics()

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield expected_llm_response_text
        if False:
            yield  # Keep linter happy

    mock_get_adapter.stream_execute = MagicMock(return_value=mock_stream_return_async())
    mock_get_adapter.execute_and_log_metrics = MagicMock(
        return_value=(
            "Non-streamed response",
            LLMMetrics(token_input=1, token_output=1, latency_ms=1),
        )
    )  # Mock for assert_not_called

    # Set up output_processor mock
    mock_output_processor.process_auto.return_value = Truncation(
        original="test output", truncated="test output"
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
    )

    await handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command="get pods",
    )

    # Assertions
    mock_get_adapter.stream_execute.assert_called_once()
    mock_get_adapter.execute_and_log_metrics.assert_not_called()

    mock_update_memory.assert_called_once_with(
        command_message="get pods",
        command_output="test output",
        vibe_output=expected_llm_response_text,
        model_name=DEFAULT_MODEL,
    )
    mock_console_manager.print_vibe.assert_called_once_with(expected_llm_response_text)


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


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
async def test_handle_command_output_model_name_from_default(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output using default model name (streaming path)."""
    expected_llm_response_text = "LLM Summary"
    # expected_metrics_for_update_memory = LLMMetrics()  # Default metrics for streaming

    mock_get_adapter.stream_execute.reset_mock()  # Reset mock before reassigning

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield expected_llm_response_text
        if False:
            yield  # Keep linter happy

    mock_get_adapter.stream_execute = MagicMock(return_value=mock_stream_return_async())

    mock_get_adapter.execute_and_log_metrics.reset_mock()  # Reset this too
    mock_get_adapter.execute_and_log_metrics = MagicMock(
        return_value=(
            "Fallback non-streamed",
            LLMMetrics(token_input=1, token_output=1, latency_ms=1),
        )
    )  # For assert_not_called

    mock_output_processor.process_auto.return_value = Truncation(
        original="test output", truncated="test output"
    )

    # Call the SUT first
    await handle_command_output(
        output=Success(data="test output"),
        output_flags=OutputFlags(
            show_raw=False,
            show_vibe=True,
            warn_no_output=True,
            model_name=DEFAULT_MODEL,
            show_metrics=True,
        ),
        summary_prompt_func=default_summary_prompt,
    )

    # Verify summary was called with correct arguments including the default model name
    mock_get_adapter.stream_execute.assert_called_once()
    mock_get_adapter.execute_and_log_metrics.assert_not_called()
    # Check that get_model was called with the default model name
    mock_get_adapter.get_model.assert_called_with(DEFAULT_MODEL)
    mock_console_manager.print_vibe.assert_called_once_with(expected_llm_response_text)
    mock_update_memory.assert_called_once_with(
        command_output="test output",
        vibe_output=expected_llm_response_text,
        model_name=DEFAULT_MODEL,
        command_message="Unknown",  # Default when command is not passed
    )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
async def test_handle_command_output_basic(
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test basic functioning of handle_command_output with vibe enabled (streaming)."""
    expected_llm_response_text = "LLM Summary"
    # expected_metrics_for_update_memory = LLMMetrics()  # Default for streaming

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield expected_llm_response_text
        if False:
            yield  # Keep linter happy

    mock_get_adapter.stream_execute = MagicMock(return_value=mock_stream_return_async())
    mock_get_adapter.execute_and_log_metrics = MagicMock(
        return_value=(
            "Fallback non-streamed",
            LLMMetrics(token_input=1, token_output=1, latency_ms=1),
        )
    )  # For assert_not_called

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_metrics=True,
    )
    with patch("vibectl.command_handler.update_memory") as mock_update_memory:
        mock_output_processor.process_auto.return_value = Truncation("output", "output")
        await handle_command_output(
            output=Success(data="output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )
        mock_get_adapter.stream_execute.assert_called_once()
        mock_get_adapter.execute_and_log_metrics.assert_not_called()
        mock_update_memory.assert_called_once_with(
            command_output="output",
            vibe_output=expected_llm_response_text,
            model_name="test-model",  # From output_flags
            command_message="Unknown",
        )
        mock_console_manager.print_vibe.assert_called_once_with(
            expected_llm_response_text
        )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
async def test_handle_command_output_raw(
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
        await handle_command_output(
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
async def test_handle_command_output_no_vibe(
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
        await handle_command_output(
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
async def test_process_vibe_output_with_autonomous_prompt_no_index_error(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test _process_vibe_output with autonomous prompt does not cause IndexError."""
    output_data = "Sample kubectl output"  # Original test data
    output_message = "Vibe summary based on output:"  # Original message
    # If show_vibe is True, it will take the streaming path.
    # The mock_get_adapter.stream_execute is set up to yield this.
    expected_llm_response_text = (
        "This stream should not be consumed for autonomous prompt"
    )
    model_name = "test-model"  # Original model name

    # Configure adapter mock
    mock_model_instance = MagicMock()
    mock_get_adapter.get_model.return_value = mock_model_instance

    async def mock_execute_log_metrics_return_async() -> tuple[str, LLMMetrics | None]:
        return expected_llm_response_text, None

    async def mock_stream_execute_return_async() -> AsyncIterator[str]:
        yield "This stream should not be consumed for autonomous prompt"
        # Keep Pyright happy about yielding
        if False:
            yield

    mock_get_adapter.execute_and_log_metrics = MagicMock(
        return_value=mock_execute_log_metrics_return_async()
    )
    mock_get_adapter.stream_execute = MagicMock(
        return_value=mock_stream_execute_return_async()
    )

    # Configure output_processor mock
    mock_output_processor.process_auto.return_value = Truncation(
        original=output_data, truncated=output_data
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,  # Original value
        model_name=model_name,
        show_metrics=True,
    )

    # Get autonomous prompt fragments
    system_fragments, user_fragments = vibe_autonomous_prompt(
        config=None  # Corrected: Pass config=None or actual Config
    )

    # Call _process_vibe_output (the function under test)
    result = await _process_vibe_output(
        output_message=output_message,
        output_data=output_data,
        output_flags=output_flags,
        summary_system_fragments=system_fragments,
        summary_user_fragments=user_fragments,
        command="get pods",  # Original command
    )

    # Assertions
    assert isinstance(result, Success)
    assert result.message == expected_llm_response_text
    # Since it streams, execute_and_log_metrics (non-streaming) should not be called
    mock_get_adapter.execute_and_log_metrics.assert_not_called()
    # stream_execute should be called
    mock_get_adapter.stream_execute.assert_called_once()

    # Check update_memory call (this part might need adjustment based on
    # actual call counts)
    # For now, let's assume one call from _process_vibe_output
    # The vibe_output should be the streamed text
    actual_call_args = mock_update_memory.call_args_list[0]

    expected_call_obj = call(
        command_message=output_message,
        command_output=output_data,
        vibe_output=expected_llm_response_text,
        model_name=model_name,
    )
    assert actual_call_args == expected_call_obj
    # Ensure console manager's print_vibe was called with the streamed content
    mock_console_manager.print_vibe.assert_called_once_with(expected_llm_response_text)


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
async def test_handle_command_output_llm_error(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output when LLM summarization fails (streaming path)."""
    error_message_from_llm = "ERROR: LLM failed to summarize"
    # Even if LLM returns an error text, the streaming path in _process_vibe_output
    # will associate default LLMMetrics() with it for the update_memory call.
    # expected_metrics_for_update_memory = LLMMetrics()

    mock_get_adapter.stream_execute.reset_mock()  # Reset mock before reassigning

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield error_message_from_llm
        if False:
            yield  # Keep linter happy

    mock_get_adapter.stream_execute = MagicMock(return_value=mock_stream_return_async())

    mock_get_adapter.execute_and_log_metrics.reset_mock()  # Reset this too
    mock_get_adapter.execute_and_log_metrics = MagicMock(
        return_value=(
            "Fallback non-streamed",
            LLMMetrics(token_input=1, token_output=1, latency_ms=1),
        )
    )  # For assert_not_called

    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_metrics=True,
    )

    # Call the SUT first
    await handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )

    mock_get_adapter.stream_execute.assert_called_once()
    mock_get_adapter.execute_and_log_metrics.assert_not_called()

    mock_console_manager.print_error.assert_any_call(error_message_from_llm)
    # In this specific error path (streaming an "ERROR:" message from LLM),
    # _process_vibe_output *does* call update_memory with the error.
    mock_update_memory.assert_called_once_with(
        command_message="Unknown",  # Default if not passed
        command_output="test output",
        vibe_output=error_message_from_llm,  # The "ERROR: ..." string
        model_name=output_flags.model_name,
        # config and summary_prompt_func are not passed by handle_command_output
        # when _process_vibe_output returns an error. They default in update_memory.
    )


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
async def test_handle_command_output_error_input_no_vibe(
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

    result = await handle_command_output(
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
async def test_handle_command_output_error_input_with_vibe_recovery(
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output with error input but vibe recovery."""
    error_message = "Original error message"
    expected_recovery_suggestion_text = "Recovered: New command suggestion"
    original_error = Error(error=error_message, exception=ValueError(error_message))
    # expected_recovery_metrics = LLMMetrics(
    #     token_input=10, token_output=20, latency_ms=100
    # )

    # Configure mock adapter for recovery (uses execute_and_log_metrics)
    async def mock_execute_return() -> tuple[str, LLMMetrics | None]:
        return (
            expected_recovery_suggestion_text,
            None,
        )

    mock_get_adapter.execute_and_log_metrics.return_value = mock_execute_return()

    # Mock stream_execute to ensure it's NOT called during recovery path
    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield "This stream should not be consumed in recovery path"
        if False:
            yield  # Keep linter happy

    mock_get_adapter.stream_execute = MagicMock(return_value=mock_stream_return_async())

    # Configure output_processor mock
    mock_output_processor.process_auto.return_value = Truncation(
        original=error_message, truncated=error_message
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
        show_kubectl=True,
    )

    with patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt_func:
        mock_recovery_prompt_func.return_value = (
            SystemFragments([Fragment("System Prompt")]),
            UserFragments([Fragment("User Prompt")]),
        )

        result = await handle_command_output(
            output=original_error,
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
            command="test-recovery-command",
        )

    assert isinstance(result, Error)
    assert result.error == error_message
    # recovery_suggestions should now be the plain text from the LLM
    assert result.recovery_suggestions == expected_recovery_suggestion_text

    # LLM is called ONCE for recovery suggestion.
    assert mock_get_adapter.execute_and_log_metrics.call_count == 1
    # stream_execute should NOT be called in the error recovery path
    mock_get_adapter.stream_execute.assert_not_called()

    mock_console_manager.print_error.assert_called_once_with(error_message)
    # The plain text recovery suggestion is printed by print_vibe
    mock_console_manager.print_vibe.assert_any_call(expected_recovery_suggestion_text)

    # update_memory is called with the error_data and the plain text recovery_suggestion
    mock_update_memory.assert_called_once_with(
        command_output=error_message,
        vibe_output=expected_recovery_suggestion_text,
        model_name="test-model",
        command_message="test-recovery-command",
    )


@patch("vibectl.command_handler.Config")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
async def test_handle_command_output_model_name_from_config(
    mock_console_manager: MagicMock,  # Patches .console_manager
    mock_output_processor: MagicMock,  # Patches .output_processor
    mock_get_memory_func: MagicMock,  # Patches .get_memory
    mock_config_class: MagicMock,  # Patches .Config
    mock_get_adapter: MagicMock,  # Fixture from conftest.py
    prevent_exit: MagicMock,  # Fixture
    default_summary_prompt: SummaryPromptFragmentFunc,  # Fixture
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
        await handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )
