from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.cli import cli
from vibectl.config import DEFAULT_CONFIG
from vibectl.prompts.events import events_plan_prompt, events_prompt
from vibectl.types import Error, MetricsDisplayMode, OutputFlags, Success


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@pytest.mark.asyncio
async def test_events_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test error handling in events command."""
    mock_run_kubectl.return_value = Error(error="Test error")
    # Mock handle_command_output to return the same error with recovery suggestions
    mock_handle_output.return_value = Error(
        error="Test error", recovery_suggestions="Try checking the resource name"
    )

    events_command = cli.commands.get("events")
    assert events_command is not None, "'events' command not found in CLI"

    with pytest.raises(SystemExit) as exc_info:
        # Remove --show-streaming since it's now a global flag
        await events_command.main(["pods"], standalone_mode=False)

    assert exc_info.value.code != 0

    mock_run_kubectl.assert_called_once()
    # Args check can be tricky due to how click processes them.
    # A simple check that "pods" is in the command list.
    called_args, _ = mock_run_kubectl.call_args
    assert "events" in called_args[0]  # Base command
    assert "pods" in called_args[0]
    # Verify that the kubectl command doesn't contain vibectl-specific flags
    assert called_args[0] == ["events", "pods"]

    # Now expect handle_command_output to be called since show_vibe=True by default
    # and errors go through recovery suggestion flow
    mock_handle_output.assert_called_once()


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@pytest.mark.asyncio
async def test_events_output_processing(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
) -> None:
    """Test events command output processing."""

    mock_run_kubectl.return_value = Success(data="Event data")

    events_command = cli.commands.get("events")
    assert events_command is not None, "'events' command not found in CLI"

    with pytest.raises(SystemExit) as exc_info:
        # Remove --show-streaming since it's now a global flag
        await events_command.main(["pods"], standalone_mode=False)

    assert exc_info.value.code == 0

    mock_run_kubectl.assert_called_once()
    called_args, _ = mock_run_kubectl.call_args
    assert "events" in called_args[0]  # Base command
    assert "pods" in called_args[0]
    # Verify vibectl flags don't leak into kubectl command
    assert called_args[0] == ["events", "pods"]

    mock_handle_output.assert_called_once()
    # Example: Assert specific properties of OutputFlags if crucial
    ho_args, _ = mock_handle_output.call_args  # Get positional arguments
    assert len(ho_args) > 1, "handle_command_output not called with enough arguments"
    actual_output_flags = ho_args[1]  # output_flags is the second positional argument
    assert actual_output_flags is not None
    # Since --show-streaming is no longer passed as a parameter, streaming behavior
    # is controlled by ContextVar overrides set at the CLI level
    assert actual_output_flags.show_vibe is True  # Default or from CLI setup
    assert actual_output_flags.model_name == str(DEFAULT_CONFIG["llm"]["model"])


@patch("vibectl.subcommands.events_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.subcommands.events_cmd.configure_memory_flags")
@patch("vibectl.subcommands.events_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_events_vibe_path(
    mock_configure_output_flags: Mock,
    mock_configure_memory_flags: Mock,
    mock_handle_vibe_request: AsyncMock,
) -> None:
    """Test the 'vibe' path in the events command."""
    dummy_output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        model_name="test_model_vibe",
        warn_no_output=False,
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=False,
    )
    mock_configure_output_flags.return_value = dummy_output_flags
    mock_handle_vibe_request.return_value = Success(data="vibe action successful")

    events_command = cli.commands.get("events")
    assert events_command is not None, "'events' command not found in CLI"

    # When --freeze-memory or --unfreeze-memory are not passed to the CLI command,
    # their values will be None when run_events_command receives them,
    # due to click.option's default=None in common_command_options.
    expected_freeze_memory_arg = None
    expected_unfreeze_memory_arg = None

    with pytest.raises(SystemExit) as exc_info:
        await events_command.main(
            ["vibe", "my", "custom", "request"], standalone_mode=False
        )

    assert exc_info.value.code == 0

    mock_configure_output_flags.assert_called_once()
    cof_kwargs = mock_configure_output_flags.call_args.kwargs
    assert cof_kwargs.get("show_raw_output") is None
    assert cof_kwargs.get("show_vibe") is None
    # show_streaming is no longer a parameter passed to configure_output_flags
    # since it's handled via ContextVar overrides at the CLI level

    mock_configure_memory_flags.assert_called_once_with(
        expected_freeze_memory_arg, expected_unfreeze_memory_arg
    )

    mock_handle_vibe_request.assert_called_once()
    hvr_call_args, hvr_call_kwargs = mock_handle_vibe_request.call_args
    assert hvr_call_kwargs.get("request") == "my custom request"
    assert hvr_call_kwargs.get("command") == "events"
    assert hvr_call_kwargs.get("output_flags") == dummy_output_flags
    # Check that the correct prompt functions are passed
    # The plan_prompt_func is a lambda, so we call it to check its return value
    assert hvr_call_kwargs.get("plan_prompt_func") is not None
    assert hvr_call_kwargs.get("plan_prompt_func")() == events_plan_prompt()
    assert hvr_call_kwargs.get("summary_prompt_func") == events_prompt


@patch("vibectl.subcommands.events_cmd.handle_watch_with_live_display")
@patch("vibectl.subcommands.events_cmd.configure_memory_flags")
@patch("vibectl.subcommands.events_cmd.configure_output_flags")
@pytest.mark.asyncio
@pytest.mark.parametrize("watch_flag", ["--watch", "-w"])
async def test_events_watch_path(
    mock_configure_output_flags: Mock,
    mock_configure_memory_flags: Mock,
    mock_handle_watch_with_live_display: Mock,
    watch_flag: str,
) -> None:
    """Test the '--watch' / '-w' path in the events command."""
    dummy_output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        model_name="test_model_watch",
        warn_no_output=False,
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=False,
    )
    mock_configure_output_flags.return_value = dummy_output_flags

    # Configure as a simple async mock that returns a Success object
    async def mock_async_return(*args: Any, **kwargs: Any) -> Success:
        return Success(data="watch data successful")

    mock_handle_watch_with_live_display.side_effect = mock_async_return

    events_command = cli.commands.get("events")
    assert events_command is not None, "'events' command not found in CLI"

    # Similar to vibe_path, expect None if flags not explicitly passed.
    expected_freeze_memory_arg = None
    expected_unfreeze_memory_arg = None

    cli_args = [watch_flag, "pods", "a-specific-pod"]

    with pytest.raises(SystemExit) as exc_info:
        await events_command.main(cli_args, standalone_mode=False)

    assert exc_info.value.code == 0

    mock_configure_output_flags.assert_called_once()
    # Defaults from common_command_options for events
    cof_kwargs = mock_configure_output_flags.call_args.kwargs
    assert cof_kwargs.get("show_raw_output") is None
    assert cof_kwargs.get("show_vibe") is None
    # show_streaming is no longer a parameter since it's handled via ContextVar

    mock_configure_memory_flags.assert_called_once_with(
        expected_freeze_memory_arg, expected_unfreeze_memory_arg
    )

    mock_handle_watch_with_live_display.assert_called_once()
    hwd_call_args, hwd_call_kwargs = mock_handle_watch_with_live_display.call_args
    assert hwd_call_kwargs.get("command") == "events"
    assert hwd_call_kwargs.get("resource") == ""
    assert hwd_call_kwargs.get("args") == tuple(
        cli_args
    )  # e.g. ("--watch", "pods", "a-specific-pod")
    assert hwd_call_kwargs.get("output_flags") == dummy_output_flags
    assert hwd_call_kwargs.get("summary_prompt_func") == events_prompt


@patch("vibectl.subcommands.events_cmd.configure_output_flags")
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@pytest.mark.asyncio
async def test_events_with_streaming_contextvar(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_output_flags: Mock,
) -> None:
    """Test events command with streaming enabled via ContextVar override.

    This test demonstrates how vibectl flags (like --show-streaming) are handled
    properly via ContextVar overrides and don't leak into kubectl commands.
    """
    from vibectl.overrides import set_override

    # Set up streaming via ContextVar override (simulating global --show-streaming flag)
    set_override("display.show_streaming", True)

    # Configure mocks
    mock_run_kubectl.return_value = Success(data="Event data")
    mock_handle_output.return_value = Success(data="Processed event data")

    streaming_output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        model_name="default",
        warn_no_output=False,
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,  # Should reflect the ContextVar override
    )
    mock_configure_output_flags.return_value = streaming_output_flags

    events_command = cli.commands.get("events")
    assert events_command is not None, "'events' command not found in CLI"

    try:
        with pytest.raises(SystemExit) as exc_info:
            await events_command.main(["pods"], standalone_mode=False)

        assert exc_info.value.code == 0

        # Verify kubectl doesn't receive vibectl-specific flags
        mock_run_kubectl.assert_called_once()
        called_args, _ = mock_run_kubectl.call_args
        kubectl_command = called_args[0]
        assert kubectl_command == ["events", "pods"]
        # Critical: ensure no vibectl flags leak into kubectl command
        assert "--show-streaming" not in kubectl_command
        assert "--streaming" not in kubectl_command

        # Verify output processing received the correct flags
        mock_handle_output.assert_called_once()
        ho_args, _ = mock_handle_output.call_args
        actual_output_flags = ho_args[1]
        assert actual_output_flags.show_streaming is True

    finally:
        # Clean up ContextVar override
        from vibectl.overrides import clear_overrides

        clear_overrides()
