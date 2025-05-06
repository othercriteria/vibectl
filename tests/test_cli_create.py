"""Tests for the CLI create command.

This module tests the create command functionality of vibectl with focus on
error handling.
"""

from unittest.mock import Mock, patch

import pytest

# Add CliRunner back
# Import cli for vibe tests, and the helper for standard tests
# Also import the specific create command function for direct calls
from vibectl.cli import _create_command_logic, create

# Import OutputFlags and the prompt func for assertions
from vibectl.command_handler import OutputFlags
from vibectl.prompt import create_resource_prompt
from vibectl.types import Error, Success  # Import necessary types

# --- Tests for _create_command_logic --- #


# Patch run_kubectl where it's used by run_create_command
@patch("vibectl.subcommands.create_cmd.run_kubectl")
def test_create_logic_basic(mock_run_kubectl: Mock) -> None:
    """Test basic _create_command_logic functionality."""
    mock_run_kubectl.return_value = "test output"

    # Mock handle_command_output
    with patch(
        "vibectl.subcommands.create_cmd.handle_command_output"
    ) as mock_handle_cmd_output:
        result = _create_command_logic(
            resource="pod",
            args=("my-pod",),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            show_kubectl=None,
        )

    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_cmd_output.assert_called_once()
    call_args, call_kwargs = mock_handle_cmd_output.call_args
    assert call_kwargs["output"] == "test output"
    assert isinstance(call_kwargs["output_flags"], OutputFlags)
    assert call_kwargs["output_flags"].show_vibe is True
    assert call_kwargs["summary_prompt_func"] == create_resource_prompt


@patch("vibectl.subcommands.create_cmd.run_kubectl")
def test_create_logic_with_args(mock_run_kubectl: Mock) -> None:
    """Test _create_command_logic with additional arguments."""
    mock_run_kubectl.return_value = "test output"

    with patch(
        "vibectl.subcommands.create_cmd.handle_command_output"
    ) as mock_handle_cmd_output:
        result = _create_command_logic(
            resource="pod",
            args=("my-pod", "--", "-n", "default"),  # Pass args directly
            show_raw_output=None,
            show_vibe=None,
            model=None,
            show_kubectl=None,
        )

    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(
        ["create", "pod", "my-pod", "--", "-n", "default"], capture=True
    )
    mock_handle_cmd_output.assert_called_once()


@patch("vibectl.subcommands.create_cmd.run_kubectl")
def test_create_logic_with_flags(mock_run_kubectl: Mock) -> None:
    """Test _create_command_logic with output flags."""
    mock_run_kubectl.return_value = "test output"

    with patch(
        "vibectl.subcommands.create_cmd.handle_command_output"
    ) as mock_handle_cmd_output:
        result = _create_command_logic(
            resource="pod",
            args=("my-pod",),  # Pass args directly
            show_raw_output=True,
            show_vibe=False,
            model="test-model",
            show_kubectl=True,
        )

    assert isinstance(result, Success)
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_cmd_output.assert_called_once()
    # Check flags passed to handle_command_output (via output_flags)
    call_args, call_kwargs = mock_handle_cmd_output.call_args
    output_flags = call_kwargs["output_flags"]
    assert output_flags.show_raw is True
    assert output_flags.show_vibe is False
    assert output_flags.model_name == "test-model"
    assert output_flags.show_kubectl is True


@patch("vibectl.subcommands.create_cmd.run_kubectl")
def test_create_logic_no_output(mock_run_kubectl: Mock) -> None:
    """Test _create_command_logic when kubectl returns no output."""
    mock_run_kubectl.return_value = ""

    with patch(
        "vibectl.subcommands.create_cmd.handle_command_output"
    ) as mock_handle_cmd_output:
        result = _create_command_logic(
            resource="pod",
            args=("my-pod",),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            show_kubectl=None,
        )

    assert isinstance(result, Success)
    assert result.message == "No output from kubectl create command."
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_cmd_output.assert_not_called()


@patch("vibectl.subcommands.create_cmd.run_kubectl")
def test_create_logic_error_handling(mock_run_kubectl: Mock) -> None:
    """Test _create_command_logic error handling."""
    test_exception = Exception("Kubectl error")
    mock_run_kubectl.side_effect = test_exception

    result = _create_command_logic(
        resource="pod",
        args=("my-pod",),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        show_kubectl=None,
    )

    assert isinstance(result, Error)
    assert result.error == "Exception running kubectl"
    assert result.exception == test_exception
    mock_run_kubectl.assert_called_once()


# --- Tests for vibe functionality using create --- #


@pytest.mark.asyncio  # Mark test as async
# Patch run_vibe_command where it's imported in the cli module
@patch("vibectl.cli.run_vibe_command")
@patch("vibectl.cli.handle_result")  # Keep patch for handle_result
async def test_create_vibe_request(
    mock_handle_result: Mock, mock_run_vibe: Mock
) -> None:
    """Test create command with vibe request (direct call)."""
    mock_run_vibe.return_value = Success(data="vibe output")

    # Use main() for async command invocation
    await create.main(
        args=["vibe", "create", "a", "new", "pod"],  # Pass full args list
        standalone_mode=False,
        # Add other default args if main expects them, or rely on defaults
    )

    mock_run_vibe.assert_called_once()
    call_kwargs = mock_run_vibe.call_args[1]
    assert call_kwargs["request"] == "create a new pod"
    mock_handle_result.assert_called_once_with(mock_run_vibe.return_value)


@pytest.mark.asyncio  # Mark test as async
@patch("sys.exit")  # Keep patch for sys.exit
@patch("vibectl.cli.console_manager")  # Keep patch for console
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
