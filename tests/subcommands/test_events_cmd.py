from unittest.mock import Mock, patch

import pytest

from vibectl.cli import cli
from vibectl.config import DEFAULT_CONFIG
from vibectl.prompt import PLAN_EVENTS_PROMPT, events_prompt

# from asyncclick.testing import CliRunner # No longer needed if using main directly
from vibectl.types import Error, OutputFlags, Success


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@pytest.mark.asyncio
async def test_events_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    # cli_runner: CliRunner, # No longer needed
) -> None:
    """Test error handling in events command."""
    mock_run_kubectl.return_value = Error(error="Test error")

    events_command = cli.commands.get("events")
    assert events_command is not None, "'events' command not found in CLI"

    with pytest.raises(SystemExit) as exc_info:
        # Call main directly, ensure standalone_mode=False if main uses it
        await events_command.main(["pods", "--show-streaming"], standalone_mode=False)

    assert exc_info.value.code != 0

    mock_run_kubectl.assert_called_once()
    # Args check can be tricky due to how click processes them.
    # A simple check that "pods" and "--show-streaming" are in the command list.
    called_args, _ = mock_run_kubectl.call_args
    assert "events" in called_args[0]  # Base command
    assert "pods" in called_args[0]
    # --show-streaming is a vibectl flag, not passed to kubectl events
    # So, it should NOT be in called_args[0] for run_kubectl
    # This was an error in my previous reasoning for this test.
    # The run_events_command itself forms the kubectl command.

    mock_handle_output.assert_not_called()


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.handle_command_output")
@pytest.mark.asyncio
async def test_events_output_processing(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    # cli_runner: CliRunner, # No longer needed
) -> None:
    """Test events command output processing."""
    # from vibectl.types import OutputFlags, Success # Moved to top

    mock_run_kubectl.return_value = Success(data="Event data")

    # This OutputFlags object is an example of what configure_output_flags might return.
    # The actual assertion will be on the mock_handle_output call.
    # expected_output_flags = OutputFlags(
    #     show_raw=False,
    #     show_vibe=True,
    #     model_name=str(DEFAULT_CONFIG.get("model")),
    #     warn_no_output=True,
    #     show_kubectl=False,
    #     show_metrics=False,
    #     show_streaming=True,
    # )

    events_command = cli.commands.get("events")
    assert events_command is not None, "'events' command not found in CLI"

    with pytest.raises(SystemExit) as exc_info:
        await events_command.main(["pods", "--show-streaming"], standalone_mode=False)

    assert exc_info.value.code == 0

    mock_run_kubectl.assert_called_once()
    called_args, _ = mock_run_kubectl.call_args
    assert "events" in called_args[0]  # Base command
    assert "pods" in called_args[0]
    # --show-streaming is a vibectl flag, should not be in kubectl args.
    assert called_args[0] == ["events", "pods"]

    mock_handle_output.assert_called_once()
    # Example: Assert specific properties of OutputFlags if crucial
    ho_args, _ = mock_handle_output.call_args  # Get positional arguments
    assert len(ho_args) > 1, "handle_command_output not called with enough arguments"
    actual_output_flags = ho_args[1]  # output_flags is the second positional argument
    assert actual_output_flags is not None
    assert (
        actual_output_flags.show_streaming is True
    )  # Since --show-streaming was passed
    assert actual_output_flags.show_vibe is True  # Default or from --show-streaming
    assert actual_output_flags.model_name == str(DEFAULT_CONFIG.get("model"))


@patch("vibectl.subcommands.events_cmd.handle_vibe_request")
@patch("vibectl.subcommands.events_cmd.configure_memory_flags")
@patch("vibectl.subcommands.events_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_events_vibe_path(
    mock_configure_output_flags: Mock,
    mock_configure_memory_flags: Mock,
    mock_handle_vibe_request: Mock,
) -> None:
    """Test the 'vibe' path in the events command."""
    dummy_output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        model_name="test_model_vibe",
        warn_no_output=False,
        show_kubectl=False,
        show_metrics=False,
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
    assert cof_kwargs.get("model") is None
    assert cof_kwargs.get("show_kubectl") is None
    assert cof_kwargs.get("show_metrics") is None
    assert cof_kwargs.get("show_streaming") is None

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
    assert hvr_call_kwargs.get("plan_prompt_func")() == PLAN_EVENTS_PROMPT
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
        show_raw=False,
        show_vibe=True,
        model_name="test_model_watch",
        warn_no_output=False,
        show_kubectl=False,
        show_metrics=False,
        show_streaming=False,
    )
    mock_configure_output_flags.return_value = dummy_output_flags
    mock_handle_watch_with_live_display.return_value = Success(
        data="watch data successful"
    )

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
    assert cof_kwargs.get("model") is None
    assert cof_kwargs.get("show_kubectl") is None
    assert cof_kwargs.get("show_metrics") is None
    assert cof_kwargs.get("show_streaming") is None

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


# Mock DEFAULT_CONFIG for tests in this file if needed, or ensure it's available.
# from vibectl.config import DEFAULT_CONFIG (if not already imported for the whole file)
