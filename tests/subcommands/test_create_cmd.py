"""Tests for the CLI create command.

This module tests the create command functionality of vibectl with focus on
error handling.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.cli import create
from vibectl.command_handler import OutputFlags
from vibectl.prompts.create import create_resource_prompt
from vibectl.subcommands.create_cmd import run_create_command
from vibectl.types import Error, Success


# Patch run_kubectl where it's used by run_create_command
@patch("vibectl.subcommands.create_cmd.run_kubectl")
@pytest.mark.asyncio
async def test_create_logic_basic(mock_run_kubectl: Mock) -> None:
    """Test basic run_create_command functionality."""
    mock_run_kubectl.return_value = Success(data="test output")

    # Mock handle_command_output
    with patch(
        "vibectl.subcommands.create_cmd.handle_command_output", new_callable=AsyncMock
    ) as mock_handle_cmd_output:
        mock_handle_cmd_output.return_value = Success(message="handled")

        result_from_logic = await run_create_command(
            resource="pod",
            args=("my-pod",),
            show_vibe=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

    assert isinstance(result_from_logic, Success)
    assert (
        result_from_logic.message == "Completed 'create' subcommand for resource: pod"
    )

    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"])

    mock_handle_cmd_output.assert_called_once()
    call_args, call_kwargs = mock_handle_cmd_output.call_args
    assert isinstance(call_kwargs["output"], Success)
    assert call_kwargs["output"].data == "test output"
    assert isinstance(call_kwargs["output_flags"], OutputFlags)
    assert call_kwargs["output_flags"].show_vibe is True
    assert call_kwargs["summary_prompt_func"] == create_resource_prompt


@patch("vibectl.subcommands.create_cmd.run_kubectl")
@pytest.mark.asyncio
async def test_create_logic_with_args(mock_run_kubectl: Mock) -> None:
    """Test run_create_command with additional arguments."""
    mock_run_kubectl.return_value = Success(data="test output with args")

    with patch(
        "vibectl.subcommands.create_cmd.handle_command_output", new_callable=AsyncMock
    ) as mock_handle_cmd_output:
        mock_handle_cmd_output.return_value = Success(message="handled")
        result_from_logic = await run_create_command(
            resource="pod",
            args=("my-pod", "--", "-n", "default"),
            show_vibe=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

    assert isinstance(result_from_logic, Success)
    assert (
        result_from_logic.message == "Completed 'create' subcommand for resource: pod"
    )

    mock_run_kubectl.assert_called_once_with(
        ["create", "pod", "my-pod", "--", "-n", "default"]
    )
    mock_handle_cmd_output.assert_called_once()
    passed_output_to_handler = mock_handle_cmd_output.call_args.kwargs["output"]
    assert isinstance(passed_output_to_handler, Success)
    assert passed_output_to_handler.data == "test output with args"


@patch("vibectl.subcommands.create_cmd.run_kubectl")
@pytest.mark.asyncio
async def test_create_logic_with_flags(mock_run_kubectl: Mock) -> None:
    """Test run_create_command with output flags."""
    mock_run_kubectl.return_value = Success(data="test output with flags")

    with patch(
        "vibectl.subcommands.create_cmd.handle_command_output", new_callable=AsyncMock
    ) as mock_handle_cmd_output:
        mock_handle_cmd_output.return_value = Success(message="handled")
        result_from_logic = await run_create_command(
            resource="pod",
            args=("my-pod",),
            show_vibe=False,
            freeze_memory=False,
            unfreeze_memory=False,
        )

    assert isinstance(result_from_logic, Success)
    assert (
        result_from_logic.message == "Completed 'create' subcommand for resource: pod"
    )

    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"])

    mock_handle_cmd_output.assert_called_once()
    call_args, call_kwargs = mock_handle_cmd_output.call_args
    passed_output_to_handler = call_kwargs["output"]
    assert isinstance(passed_output_to_handler, Success)
    assert passed_output_to_handler.data == "test output with flags"
    output_flags = call_kwargs["output_flags"]
    assert output_flags.show_vibe is False


@patch("vibectl.subcommands.create_cmd.run_kubectl")
@pytest.mark.asyncio
async def test_create_logic_no_output(mock_run_kubectl: Mock) -> None:
    """Test run_create_command when kubectl returns no output."""
    mock_run_kubectl.return_value = Success(
        data=None
    )  # run_kubectl returns Success with data=None

    with patch(
        "vibectl.subcommands.create_cmd.handle_command_output", new_callable=AsyncMock
    ) as mock_handle_cmd_output:
        result_from_logic = await run_create_command(
            resource="pod",
            args=("my-pod",),
            show_vibe=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

    assert isinstance(result_from_logic, Success)
    # The message comes directly from run_create_command when output.data is None
    assert result_from_logic.message == "No output from kubectl create command."

    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"])
    # handle_command_output should NOT be called if kubectl returns no data
    mock_handle_cmd_output.assert_not_called()


@patch("vibectl.subcommands.create_cmd.run_kubectl")
@pytest.mark.asyncio
async def test_create_logic_error_handling(
    mock_run_kubectl: Mock,
) -> None:
    """Test run_create_command error handling when run_kubectl raises an exception."""
    test_exception = ValueError("Kubectl execution failed badly")
    mock_run_kubectl.side_effect = test_exception  # run_kubectl raises an exception

    # No need to mock handle_command_output as it won't be reached if run_kubectl fails
    result_from_logic = await run_create_command(
        resource="pod",
        args=("my-pod",),
        show_vibe=None,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    assert isinstance(result_from_logic, Error)
    # The error message comes directly from the except block in run_create_command
    assert result_from_logic.error == "Exception running kubectl"
    assert result_from_logic.exception == test_exception

    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"])


@pytest.mark.asyncio
@patch("vibectl.subcommands.create_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.cli.handle_result")
async def test_create_vibe_request(
    mock_handle_result: Mock,
    mock_handle_vibe: AsyncMock,
) -> None:
    """Test create command with vibe request (direct call)."""
    mock_handle_vibe.return_value = Success(data="vibe output")

    # Use main() for async command invocation
    # The 'create' object here is the asyncclick.Group/Command from vibectl.cli
    await create.main(
        args=["vibe", "create", "a", "new", "pod"],  # Pass full args list
        standalone_mode=False,
        # Add other default args if main expects them, or rely on defaults
    )

    mock_handle_vibe.assert_called_once()
    call_kwargs = mock_handle_vibe.call_args[1]  # Access kwargs from call_args tuple
    assert call_kwargs["request"] == "create a new pod"
    mock_handle_result.assert_called_once_with(mock_handle_vibe.return_value)


@pytest.mark.asyncio
@patch("sys.exit")
@patch("vibectl.cli.console_manager")
async def test_create_vibe_no_request(mock_console: Mock, mock_exit: Mock) -> None:
    """Test create vibe command without a request (direct call)."""
    # Use main() for async command invocation
    # Call create.main - it should call sys.exit via the mock
    await create.main(
        args=["vibe"],  # Only provide 'vibe'
        standalone_mode=False,
    )

    # Assert sys.exit was called with code 1
    mock_exit.assert_called_once_with(1)
    # Assert error message was printed
    mock_console.print_error.assert_called_once_with(
        "Missing request after 'vibe'. Usage: vibectl create vibe <request>"
    )
