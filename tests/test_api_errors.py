"""Tests for API error handling in auto mode."""

from unittest.mock import Mock, patch

from vibectl.types import Error, Success


def create_api_error(error_type: str, error_message: str) -> Exception:
    """Create an API error that resembles the Anthropic API error format."""
    return ValueError(
        f"Error executing prompt: {{'type': 'error', 'error': {{'details': None, "
        f"'type': '{error_type}', 'message': '{error_message}'}}}}"
    )


@patch("vibectl.subcommands.auto_cmd.run_vibe_command")
@patch("vibectl.subcommands.auto_cmd.console_manager")
@patch("vibectl.subcommands.auto_cmd.configure_output_flags")
@patch("vibectl.subcommands.auto_cmd.configure_memory_flags")
@patch("vibectl.subcommands.auto_cmd.time.sleep")
def test_auto_command_continues_on_api_error(
    mock_sleep: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_console: Mock,
    mock_vibe_command: Mock,
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

    mock_vibe_command.side_effect = [
        mock_overloaded_error,
        Success(message="Command succeeded"),
        KeyboardInterrupt(),
    ]

    # Run the auto command
    result = run_auto_command(
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
def test_handle_command_output_api_error_marked_non_halting(
    mock_console: Mock,
) -> None:
    """Test that handle_command_output marks API errors as non-halting for auto loop."""
    from vibectl.cli import DEFAULT_MODEL
    from vibectl.command_handler import handle_command_output
    from vibectl.types import OutputFlags

    # Create output flags
    output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name=DEFAULT_MODEL,
    )

    # Create a ValueError with API error pattern
    api_exception = ValueError(
        "Error executing prompt: {'type': 'error', 'error': {'details': None, "
        "'type': 'overloaded_error', 'message': 'Overloaded'}}"
    )

    # Test with a mocked _process_vibe_output that raises an API error
    with patch("vibectl.command_handler._process_vibe_output") as mock_process_vibe:
        # Set up the mock to raise the API exception
        mock_process_vibe.side_effect = api_exception

        # Call the function
        result = handle_command_output(
            output="test output",
            output_flags=output_flags,
            summary_prompt_func=lambda: "Test prompt {output}",
        )

    # Verify result is as expected
    assert isinstance(result, Error)
    assert "overloaded_error" in result.error
    assert result.halt_auto_loop is False  # This is the key assertion
