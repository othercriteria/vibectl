"""Tests for command output handling functionality."""

from collections.abc import AsyncIterator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch

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
            LLMMetrics(token_input=1, token_output=1),
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
        show_streaming=True,
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
    # console_manager.stop_live_vibe_panel() should be called to end the live session.
    mock_console_manager.stop_live_vibe_panel.assert_called_once()
    # print_vibe (final panel display *after* streaming) should be called even if empty.
    mock_console_manager.print_vibe.assert_called_once_with(
        expected_llm_response_text, use_panel=True
    )
    mock_update_memory.assert_called_once()


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
    """Test handle_command_output with a command and streaming enabled."""
    expected_llm_response_text = "LLM response with command: `kubectl get pods`"

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield expected_llm_response_text
        if False:
            yield  # Keep linter happy

    # Mock stream_execute for the streaming path
    mock_get_adapter.stream_execute = MagicMock(return_value=mock_stream_return_async())
    # Mock execute_and_log_metrics for the non-streaming path (should not be called)
    # Provide a distinct response to ensure it's not what we see.
    mock_get_adapter.execute_and_log_metrics = MagicMock(
        return_value=(
            "Non-streamed fallback response",
            LLMMetrics(token_input=1, token_output=1),
        )
    )

    mock_output_processor.process_auto.return_value = Truncation(
        original="test output", truncated="processed test output"
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
        show_streaming=True,  # Explicitly testing streaming path
    )
    command_name = "get pods"

    await handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
        command=command_name,
    )

    # Assertions
    mock_get_adapter.stream_execute.assert_called_once()
    mock_get_adapter.execute_and_log_metrics.assert_not_called()

    # Check console manager calls for streaming
    mock_console_manager.start_live_vibe_panel.assert_called_once()
    mock_console_manager.update_live_vibe_panel.assert_called_once_with(
        expected_llm_response_text
    )
    mock_console_manager.stop_live_vibe_panel.assert_called_once()
    mock_console_manager.print_vibe.assert_called_once_with(
        expected_llm_response_text, use_panel=True
    )

    # Check update_memory call
    # Metrics for update_memory in streaming path might be a default LLMMetrics()
    # or not passed. If metrics are critical, this part of the code/test needs review.
    # For now, asserting it's called with the Vibe output.
    mock_update_memory.assert_called_once()
    called_args, called_kwargs = mock_update_memory.call_args
    assert called_kwargs.get("vibe_output") == expected_llm_response_text
    assert called_kwargs.get("command_message") == command_name
    # Optional: More detailed check for metrics passed to update_memory if relevant
    # assert isinstance(called_kwargs.get("metrics"), LLMMetrics)


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
    """Test handle_command_output uses default model when model_name is None."""
    expected_llm_response_text = "LLM response using default model"

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield expected_llm_response_text
        if False:
            yield

    # Mock the adapter instance that the get_model_adapter fixture yields
    mock_adapter_instance = mock_get_adapter
    mock_adapter_instance.stream_execute = MagicMock(
        return_value=mock_stream_return_async()
    )
    mock_adapter_instance.execute_and_log_metrics = MagicMock(
        return_value=("Non-streamed fallback", LLMMetrics())
    )
    # Mock get_model to check it's called with the default model name
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model = MagicMock(return_value=mock_model_instance)

    mock_output_processor.process_auto.return_value = Truncation(
        original="test output", truncated="processed test output"
    )

    # OutputFlags should represent the state where no specific model was requested,
    # so it defaults to DEFAULT_MODEL (as configure_output_flags would do).
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name=DEFAULT_MODEL,
        show_metrics=True,
        show_streaming=True,  # Test streaming path
    )

    await handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )

    # Assertions
    # Check that get_model was called with the DEFAULT_MODEL
    mock_adapter_instance.get_model.assert_called_once_with(DEFAULT_MODEL)
    # Check that stream_execute was called (and not execute_and_log_metrics)
    mock_adapter_instance.stream_execute.assert_called_once_with(
        model=mock_model_instance,  # Check it used the model from get_model
        system_fragments=ANY,  # Or more specific if prompts are stable
        user_fragments=ANY,
    )
    mock_adapter_instance.execute_and_log_metrics.assert_not_called()

    # Console manager calls for streaming
    mock_console_manager.start_live_vibe_panel.assert_called_once()
    mock_console_manager.update_live_vibe_panel.assert_called_once_with(
        expected_llm_response_text
    )
    mock_console_manager.stop_live_vibe_panel.assert_called_once()
    mock_console_manager.print_vibe.assert_called_once_with(
        expected_llm_response_text, use_panel=True
    )

    # Update memory call
    mock_update_memory.assert_called_once()
    called_args, called_kwargs = mock_update_memory.call_args
    assert called_kwargs.get("vibe_output") == expected_llm_response_text
    assert called_kwargs.get("model_name") == DEFAULT_MODEL


@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.console_manager")
async def test_handle_command_output_basic(
    mock_console_manager: MagicMock,
    mock_output_processor: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test basic vibe summarization with streaming."""
    expected_llm_response_text = "Basic LLM Summary"

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield expected_llm_response_text
        if False:
            yield

    mock_adapter_instance = mock_get_adapter  # Use the fixtured adapter
    mock_adapter_instance.stream_execute = MagicMock(
        return_value=mock_stream_return_async()
    )
    mock_adapter_instance.execute_and_log_metrics = MagicMock(
        return_value=("Non-streamed fallback", LLMMetrics())
    )
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model = MagicMock(return_value=mock_model_instance)

    mock_output_processor.process_auto.return_value = Truncation(
        original="test output", truncated="processed test output"
    )
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=False,  # Test with metrics off for this basic case
        show_streaming=True,
    )

    with patch("vibectl.command_handler.update_memory") as mock_update_memory:
        await handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )

        # Assertions
        mock_adapter_instance.get_model.assert_called_once_with("test-model")
        mock_adapter_instance.stream_execute.assert_called_once_with(
            model=mock_model_instance,
            system_fragments=ANY,
            user_fragments=ANY,
        )
        mock_adapter_instance.execute_and_log_metrics.assert_not_called()

        # Console manager calls
        mock_console_manager.start_live_vibe_panel.assert_called_once()
        mock_console_manager.update_live_vibe_panel.assert_called_once_with(
            expected_llm_response_text
        )
        mock_console_manager.stop_live_vibe_panel.assert_called_once()
        mock_console_manager.print_vibe.assert_called_once_with(
            expected_llm_response_text, use_panel=True
        )
        mock_console_manager.print_metrics.assert_not_called()  # show_metrics is False

        # Update memory
        mock_update_memory.assert_called_once()
        called_args, called_kwargs = mock_update_memory.call_args
        assert called_kwargs.get("vibe_output") == expected_llm_response_text
        assert called_kwargs.get("model_name") == "test-model"


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
        show_streaming=True,
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
        show_streaming=True,
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
    """Test _process_vibe_output with autonomous prompt doesn't cause IndexError
    when format string for {output} is not present, using streaming.
    """
    original_output_data = "Original command output data"
    # Autonomous prompt does not use {output}
    system_fragments, user_fragments = vibe_autonomous_prompt(
        current_memory="Test memory"
    )
    expected_llm_response_text = "Autonomous LLM response, no original output needed."

    async def mock_stream_execute_return_async() -> AsyncIterator[str]:
        yield expected_llm_response_text
        if False:
            yield

    mock_adapter_instance = mock_get_adapter
    mock_adapter_instance.stream_execute = MagicMock(
        return_value=mock_stream_execute_return_async()
    )
    mock_adapter_instance.execute_and_log_metrics = MagicMock(
        return_value=("Non-streamed fallback", LLMMetrics())
    )
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model = MagicMock(return_value=mock_model_instance)

    mock_output_processor.process_auto.return_value = Truncation(
        original=original_output_data,
        truncated=original_output_data,  # No truncation
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="auton-model",
        show_metrics=False,
        show_streaming=True,  # Test streaming path
    )

    # Directly call _process_vibe_output as it's the unit under test here
    result = await _process_vibe_output(
        output_message="Some message",  # Not directly used by autonomous prompt
        output_data=original_output_data,
        output_flags=output_flags,
        summary_system_fragments=system_fragments,
        summary_user_fragments=user_fragments,
        command="autonomous_command",
    )

    assert isinstance(result, Success)
    assert result.message == expected_llm_response_text
    # Metrics from streaming can be None if the adapter doesn't update them
    assert result.metrics is None or isinstance(result.metrics, LLMMetrics)

    # Prepare expected formatted fragments for assertion
    output_data_for_llm = (
        original_output_data if original_output_data is not None else ""
    )

    expected_formatted_system_fragments = SystemFragments(
        [Fragment(frag.format(output=output_data_for_llm)) for frag in system_fragments]
    )
    expected_formatted_user_fragments = UserFragments(
        [Fragment(frag.format(output=output_data_for_llm)) for frag in user_fragments]
    )

    # Assertions
    mock_adapter_instance.get_model.assert_called_once_with("auton-model")
    mock_adapter_instance.stream_execute.assert_called_once_with(
        model=mock_model_instance,
        system_fragments=expected_formatted_system_fragments,
        user_fragments=expected_formatted_user_fragments,
    )
    mock_adapter_instance.execute_and_log_metrics.assert_not_called()

    # Console manager calls for streaming
    mock_console_manager.start_live_vibe_panel.assert_called_once()
    mock_console_manager.update_live_vibe_panel.assert_called_once_with(
        expected_llm_response_text
    )
    mock_console_manager.stop_live_vibe_panel.assert_called_once()
    mock_console_manager.print_vibe.assert_called_once_with(
        expected_llm_response_text, use_panel=True
    )

    # Update memory call
    mock_update_memory.assert_called_once()
    called_args, called_kwargs = mock_update_memory.call_args
    assert called_kwargs.get("vibe_output") == expected_llm_response_text
    assert called_kwargs.get("model_name") == "auton-model"
    assert called_kwargs.get("command_message") == "autonomous_command"
    assert called_kwargs.get("command_output") == original_output_data


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

    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield error_message_from_llm
        if False:
            yield

    mock_adapter_instance = mock_get_adapter
    mock_adapter_instance.stream_execute = MagicMock(
        return_value=mock_stream_return_async()
    )
    mock_adapter_instance.execute_and_log_metrics = MagicMock(
        return_value=("Non-streamed fallback", LLMMetrics())
    )
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model = MagicMock(return_value=mock_model_instance)

    mock_output_processor.process_auto.return_value = Truncation(
        original="test output", truncated="processed test output"
    )

    output_flags = OutputFlags(
        show_raw=True,  # Keep raw output for context if Vibe fails
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model-llm-error",
        show_metrics=True,
        show_streaming=True,
    )

    # Call the SUT
    result = await handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=default_summary_prompt,
    )

    # Assertions
    assert isinstance(result, Error)  # Should return an Error object
    # _process_vibe_output calls create_api_error with the stripped message
    expected_stripped_error = error_message_from_llm.replace("ERROR: ", "")
    assert result.error == expected_stripped_error

    mock_adapter_instance.get_model.assert_called_once_with("test-model-llm-error")
    mock_adapter_instance.stream_execute.assert_called_once()
    mock_adapter_instance.execute_and_log_metrics.assert_not_called()

    # Console manager calls for streaming
    mock_console_manager.start_live_vibe_panel.assert_called_once()
    mock_console_manager.update_live_vibe_panel.assert_called_once_with(
        error_message_from_llm
    )
    mock_console_manager.stop_live_vibe_panel.assert_called_once()
    # print_vibe shows the final live panel content, which is the error message
    mock_console_manager.print_vibe.assert_called_once_with(
        error_message_from_llm, use_panel=True
    )

    # print_error should NOT be called in this path, as the error is from the
    # LLM summarization of a successful command, and the error message is
    # displayed via print_vibe.
    mock_console_manager.print_error.assert_not_called()

    # Update memory should be called with the error message as vibe_output
    mock_update_memory.assert_called_once()
    called_args, called_kwargs = mock_update_memory.call_args
    assert called_kwargs.get("vibe_output") == error_message_from_llm
    assert called_kwargs.get("model_name") == "test-model-llm-error"
    assert (
        called_kwargs.get("command_output") == "test output"
    )  # Should be original output, not processed


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
        show_streaming=True,
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


@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.output_processor")
async def test_handle_command_output_error_input_with_vibe_recovery(
    mock_output_processor: MagicMock,
    mock_update_memory: MagicMock,
    mock_console_manager: MagicMock,
    prevent_exit: MagicMock,
    default_summary_prompt: SummaryPromptFragmentFunc,
    mock_get_adapter: MagicMock,
) -> None:
    """Test handle_command_output with error input but vibe recovery."""
    error_message = "Original error message"
    expected_recovery_suggestion_text = "Recovered: New command suggestion"
    original_error = Error(error=error_message, exception=ValueError(error_message))
    recovery_metrics = LLMMetrics(
        token_input=5, token_output=15, latency_ms=50, total_processing_duration_ms=60
    )

    # Configure mock adapter for recovery (uses execute_and_log_metrics)
    mock_adapter_instance = mock_get_adapter

    # Make the mock return an awaitable that resolves to the tuple
    async def mock_execute_and_log_metrics_return_val() -> tuple[str, LLMMetrics]:
        return (expected_recovery_suggestion_text, recovery_metrics)

    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(expected_recovery_suggestion_text, recovery_metrics)
    )
    # Mock get_model for the recovery call
    mock_model_instance_recovery = MagicMock()
    mock_adapter_instance.get_model = MagicMock(
        return_value=mock_model_instance_recovery
    )

    # Mock stream_execute to ensure it's NOT called during recovery path
    async def mock_stream_return_async() -> AsyncIterator[str]:
        yield "This stream should not be consumed in recovery path"
        if False:
            yield

    mock_adapter_instance.stream_execute = MagicMock(
        return_value=mock_stream_return_async()
    )

    # Configure output_processor mock
    mock_output_processor.process_auto.return_value = Truncation(
        original=error_message, truncated=error_message
    )

    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,  # Vibe is on to allow recovery
        warn_no_output=False,
        model_name="test-model-recovery",
        show_metrics=True,
        show_streaming=True,  # Even if true, recovery path is non-streaming
        show_kubectl=True,  # For command context in recovery prompt
    )
    command_name_for_recovery = "test-recovery-command"

    with patch("vibectl.command_handler.recovery_prompt") as mock_recovery_prompt_func:
        mock_recovery_prompt_func.return_value = (
            SystemFragments([Fragment("System Prompt for Recovery")]),
            UserFragments(
                [Fragment("User Prompt for Recovery with {command} and {error}")]
            ),
        )

        result = await handle_command_output(
            output=original_error,
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,  # Not used for recovery path
            command=command_name_for_recovery,
        )

    assert isinstance(result, Error)
    assert result.error == error_message  # Original error message is preserved
    assert result.recovery_suggestions == expected_recovery_suggestion_text
    # Metrics from recovery should be on the result object
    assert result.metrics == recovery_metrics

    # LLM is called ONCE for recovery suggestion via execute_and_log_metrics
    mock_adapter_instance.get_model.assert_called_once_with("test-model-recovery")
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()
    # stream_execute should NOT be called in the error recovery path
    mock_adapter_instance.stream_execute.assert_not_called()

    # Console manager calls for recovery (non-streaming)
    mock_console_manager.print_error.assert_called_once_with(error_message)
    # The plain text recovery suggestion is printed by print_vibe
    mock_console_manager.print_vibe.assert_any_call(expected_recovery_suggestion_text)
    mock_console_manager.start_live_vibe_panel.assert_not_called()
    mock_console_manager.stop_live_vibe_panel.assert_not_called()

    # update_memory (mock_update_memory) should be called with recovery_metrics
    mock_update_memory.assert_called_once_with(
        command_message=command_name_for_recovery,
        command_output=original_error.error,
        vibe_output=expected_recovery_suggestion_text,
        model_name="test-model-recovery",
        config=ANY,  # Config is instantiated within handle_command_output
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
        show_streaming=True,
    )

    # Call the function with model name from config
    with patch("vibectl.command_handler.console_manager"):
        await handle_command_output(
            output=Success(data="test output"),
            output_flags=output_flags,
            summary_prompt_func=default_summary_prompt,
        )
