"""Tests for API error handling in auto mode."""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.command_handler import handle_command_output
from vibectl.config import DEFAULT_CONFIG, Config
from vibectl.types import (
    Error,
    Fragment,
    OutputFlags,
    PromptFragments,
    RecoverableApiError,
    Success,
    SystemFragments,
    UserFragments,
)

# Import the helper from the other test file (or define it here if preferred)
# For simplicity in this example, let's assume it can be defined/imported.
# If it's in test_command_output.py, you might need to adjust imports
# or duplicate the helper if direct import is problematic for test structure.


# Re-defining for clarity here, or ensure it's importable
def get_dummy_prompt_fragments(
    config: Config | None = None, current_memory: str | None = None
) -> PromptFragments:
    """Returns a dummy PromptFragments object for testing."""
    return PromptFragments(
        (
            SystemFragments([Fragment("System dummy")]),
            UserFragments([Fragment("User dummy: {output}")]),
        )
    )


def create_api_error(error_type: str, error_message: str) -> Exception:
    """Create an API error that resembles the Anthropic API error format."""
    return ValueError(
        f"Error executing prompt: {{'type': 'error', 'error': {{'details': None, "
        f"'type': '{error_type}', 'message': '{error_message}'}}}}"
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.auto_cmd.run_vibe_command", new_callable=AsyncMock)
@patch("vibectl.subcommands.auto_cmd.console_manager")
@patch("vibectl.subcommands.auto_cmd.configure_output_flags")
@patch("vibectl.subcommands.auto_cmd.configure_memory_flags")
@patch("vibectl.subcommands.auto_cmd.time.sleep")
async def test_auto_command_continues_on_api_error(
    mock_sleep: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_console: Mock,
    mock_vibe_command: AsyncMock,
) -> None:
    """Test that auto command continues on API errors like 'overloaded_error'."""
    from vibectl.subcommands.auto_cmd import run_auto_command

    # Mock responses:
    # 1. First call - return an API overloaded error with halt_auto_loop=False
    # 2. Second call - return Success
    # 3. Third call - raise KeyboardInterrupt to end the loop

    # Create a properly marked API error (halt_auto_loop=False)
    # This represents what our implementation should now produce
    mock_overloaded_error = Error(
        error="Error executing prompt: {'type': 'error', 'error': {'details': None, "
        "'type': 'overloaded_error', 'message': 'Overloaded'}}",
        exception=create_api_error("overloaded_error", "Overloaded"),
        halt_auto_loop=False,  # Updated to False - this is what our fix should produce
    )

    # Helper async function for side effect
    async def vibe_side_effect(*args: Any, **kwargs: Any) -> Any:
        call_num = mock_vibe_command.call_count
        if call_num == 1:
            return mock_overloaded_error
        elif call_num == 2:
            return Success(message="Command succeeded")
        else:
            raise KeyboardInterrupt()

    mock_vibe_command.side_effect = vibe_side_effect

    # Run the auto command
    result = await run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=0,  # No sleep delay
        exit_on_error=True,
    )

    # Verify auto command continues after the API error
    assert mock_vibe_command.call_count == 3

    # Verify the result is as expected
    assert isinstance(result, Success)
    assert "stopped by user" in result.message

    # Verify that console showed continuation message
    mock_console.print_note.assert_any_call("Continuing to next step...")


@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler._process_vibe_output")
async def test_handle_command_output_api_error_marked_non_halting(
    mock_process_vibe: Mock,
    mock_console: Mock,
) -> None:
    """Test that handle_command_output marks API errors as non-halting for auto loop."""
    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        show_metrics=True,
        # Explicitly cast to string to satisfy mypy
        model_name=str(DEFAULT_CONFIG["model"]),
    )

    # Create a RecoverableApiError
    api_exception = RecoverableApiError(
        "Error executing prompt: {'type': 'error', 'error': {'details': None, "
        "'type': 'overloaded_error', 'message': 'Overloaded'}}"
    )

    # Set up the mock to raise the API exception
    mock_process_vibe.side_effect = api_exception

    # Call the function (now imported at top level)
    result = await handle_command_output(
        output=Success(data="test output"),
        output_flags=output_flags,
        summary_prompt_func=get_dummy_prompt_fragments,
    )

    # Verify result is as expected
    assert isinstance(result, Error)
    assert "overloaded_error" in result.error
    assert result.halt_auto_loop is False  # This is the key assertion
