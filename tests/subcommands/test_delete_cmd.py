"""Tests for vibectl.subcommands.delete_cmd."""

from unittest.mock import AsyncMock, patch

import pytest

from vibectl.cli import cli  # For any CLI-level tests moved later
from vibectl.config import DEFAULT_CONFIG
from vibectl.subcommands.delete_cmd import run_delete_command
from vibectl.types import (
    Error,
    Fragment,
    OutputFlags,
    PromptFragments,
    Success,
    SystemFragments,
    UserFragments,
)


# Fixture for default OutputFlags, similar to other subcommands test files
@pytest.fixture
def default_delete_output_flags() -> OutputFlags:
    return OutputFlags(
        show_raw=bool(DEFAULT_CONFIG.get("show_raw_output", False)),
        show_vibe=bool(DEFAULT_CONFIG.get("show_vibe", True)),
        warn_no_output=bool(DEFAULT_CONFIG.get("warn_no_output", True)),
        model_name=str(DEFAULT_CONFIG.get("model", "default_model_name_fixture")),
        show_metrics=bool(DEFAULT_CONFIG.get("show_metrics", False)),
        show_kubectl=bool(DEFAULT_CONFIG.get("show_kubectl", False)),
        warn_no_proxy=bool(DEFAULT_CONFIG.get("warn_no_proxy", True)),
    )


# Fixture for a dummy summary_prompt_func
@pytest.fixture
def dummy_delete_summary_prompt() -> PromptFragments:
    # In a real scenario, delete_resource_prompt from vibectl.prompts.delete
    # would be used.
    # This is a simplified version for testing the call.
    return PromptFragments(
        (
            SystemFragments([Fragment("System prompt for delete summary")]),
            UserFragments([Fragment("User prompt for delete summary")]),
        )
    )


@pytest.mark.asyncio
async def test_run_delete_command_passes_success_object_to_handle_output(
    default_delete_output_flags: OutputFlags,
    dummy_delete_summary_prompt: PromptFragments,
) -> None:
    """Test that run_delete_command (via handle_standard_command) returns Success."""

    resource_type = "pod"
    resource_name = "test-pod"
    args_tuple = (resource_name,)

    mock_kubectl_success_result = Success(
        data=f"{resource_type}/{resource_name} deleted"
    )

    # Define what the mocked handle_command_output should return for the test to proceed
    mock_handle_command_output_return_value = Success(
        message="Processed by mock_handle_cmd_output"
    )

    # Patch _run_standard_kubectl_command within handle_standard_command,
    # which is called by run_delete_command
    # Note: run_delete_command calls handle_standard_command via asyncio.to_thread.
    # So, we need to patch where handle_standard_command *looks for*
    # _run_standard_kubectl_command.
    # And handle_command_output is also called within handle_standard_command.
    with (
        patch(
            "vibectl.command_handler._run_standard_kubectl_command",
            return_value=mock_kubectl_success_result,
        ) as mock_internal_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output",
            return_value=mock_handle_command_output_return_value,
        ) as mock_handle_cmd_output,
        patch(
            "vibectl.subcommands.delete_cmd.configure_output_flags",
            return_value=default_delete_output_flags,
        ),
        patch("vibectl.subcommands.delete_cmd.configure_memory_flags"),
    ):
        result = await run_delete_command(
            resource=resource_type,
            args=args_tuple,
            show_raw_output=default_delete_output_flags.show_raw,
            show_vibe=default_delete_output_flags.show_vibe,
            model=default_delete_output_flags.model_name,
            show_kubectl=default_delete_output_flags.show_kubectl,
        )

        assert isinstance(result, Success), (
            f"Expected Success, got {type(result)}: {result}"
        )
        mock_internal_run_kubectl.assert_called_once()
        mock_handle_cmd_output.assert_called_once()

        call_args_to_handle_output = mock_handle_cmd_output.call_args
        assert call_args_to_handle_output is not None, (
            "handle_command_output was not called with arguments"
        )

        passed_output_arg = call_args_to_handle_output[0][
            0
        ]  # First positional argument
        assert isinstance(passed_output_arg, Success), (
            f"handle_command_output expected Success, got {type(passed_output_arg)}"
        )
        assert passed_output_arg.data == mock_kubectl_success_result.data

        # Check other important args for handle_command_output
        assert (
            call_args_to_handle_output[0][1] == default_delete_output_flags
        )  # output_flags
        assert call_args_to_handle_output[0][2] is not None  # summary_prompt_func
        assert (
            call_args_to_handle_output.kwargs.get("command") == "delete"
        )  # command kwarg


@pytest.mark.asyncio
async def test_delete_vibe_request() -> None:
    """Test delete vibe request handling."""
    # run_delete_command calls handle_vibe_request directly (awaited)
    with patch(
        "vibectl.subcommands.delete_cmd.handle_vibe_request", new_callable=AsyncMock
    ) as mock_handle_vibe_request:
        from vibectl.types import Success  # Local import for clarity if needed

        mock_handle_vibe_request.return_value = Success(message="Vibe delete success")

        # We need CliRunner and the main `cli` object for these tests
        # Directly invoke the Click command object for 'delete'
        # This means we are testing the vibectl.cli.delete function
        cmd_obj = cli.commands["delete"]
        with pytest.raises(SystemExit) as exc_info:
            # The CLI command (e.g., vibectl.cli.delete) is async,
            # and its main method handles the async invocation.
            await cmd_obj.main(["vibe", "delete the nginx pod"])

        assert exc_info.value.code == 0
        mock_handle_vibe_request.assert_called_once()
        _args, kwargs = mock_handle_vibe_request.call_args
        assert kwargs["request"] == "delete the nginx pod"
        assert kwargs["command"] == "delete"
        assert kwargs["yes"] is False  # Default for 'yes' in handle_vibe_request


@pytest.mark.asyncio
async def test_delete_vibe_request_with_yes_flag() -> None:
    """Test delete vibe request with yes flag."""
    with patch(
        "vibectl.subcommands.delete_cmd.handle_vibe_request", new_callable=AsyncMock
    ) as mock_handle_vibe_request:
        from vibectl.types import Success

        mock_handle_vibe_request.return_value = Success(
            message="Vibe delete with yes success"
        )

        # Directly invoke the Click command object for 'delete'
        # This means we are testing the vibectl.cli.delete function
        cmd_obj = cli.commands["delete"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main(["vibe", "delete the nginx pod", "--yes"])

        assert exc_info.value.code == 0
        mock_handle_vibe_request.assert_called_once()
        _args, kwargs = mock_handle_vibe_request.call_args
        assert kwargs["yes"] is True  # 'yes' should be True when --yes is passed


@pytest.mark.asyncio
async def test_delete_standard(
    default_delete_output_flags: OutputFlags,  # Use existing fixture
) -> None:
    """Test standard delete command (non-vibe path)."""
    with patch(
        "vibectl.subcommands.delete_cmd.handle_standard_command", new_callable=AsyncMock
    ) as mock_handle_standard_command:
        from vibectl.types import Success

        mock_handle_standard_command.return_value = Success(
            message="Standard delete success"
        )

        # Directly invoke the Click command object for 'delete'
        # This means we are testing the vibectl.cli.delete function
        cmd_obj = cli.commands["delete"]
        # This is testing the CLI layer. The actual call inside run_delete_command to
        # handle_standard_command will be awaited.
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main(["pod", "nginx-pod"])

        assert exc_info.value.code == 0
        mock_handle_standard_command.assert_called_once()
        _args, kwargs = mock_handle_standard_command.call_args
        assert kwargs.get("command") == "delete"
        assert kwargs.get("resource") == "pod"
        assert kwargs.get("args") == ("nginx-pod",)


@pytest.mark.asyncio
async def test_delete_handles_exception() -> None:
    """Test error handling in CLI delete command on run_delete_command Error."""
    mock_error_obj = Error(
        error="Simulated error from run_delete_command",
        exception=ValueError("Simulated"),
    )

    # Patch run_delete_command directly as it's called by vibectl.cli.delete
    with patch(
        "vibectl.cli.run_delete_command",
        new_callable=AsyncMock,
        return_value=mock_error_obj,
    ) as mock_rdc:
        cmd_obj = cli.commands["delete"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main(["pod", "nginx-pod"])

        assert exc_info.value.code == 1, "Expected exit code 1 on error"
        mock_rdc.assert_called_once()
        # We can also check args passed to run_delete_command if needed, e.g.:
        # _args_to_rdc, kwargs_to_rdc = mock_rdc.call_args
        # assert kwargs_to_rdc.get("resource") == "pod"
