"""Tests for vibectl auto command."""

from typing import Any
from unittest.mock import Mock

import pytest

import vibectl.subcommands.auto_cmd  # Import for direct module access
from vibectl.types import Error, Success


def test_run_auto_command_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test basic auto command functionality."""
    # Mock run_vibe_command to simulate a few iterations and then
    # raise KeyboardInterrupt
    counter = [0]  # Use a list to allow modification in the closure

    def side_effect(*args: Any, **kwargs: Any) -> Success:
        counter[0] += 1
        if counter[0] >= 3:  # After 3 iterations, raise KeyboardInterrupt
            raise KeyboardInterrupt
        return Success(message="Completed vibe")

    mock_vibe = Mock(side_effect=side_effect)
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Mock time.sleep to avoid waiting
    mock_sleep = Mock()
    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock console_manager
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.console_manager", mock_console)

    # Mock configure functions
    mock_configure_output = Mock(return_value="output_flags")
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_output_flags", mock_configure_output
    )
    mock_configure_memory = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_memory_flags", mock_configure_memory
    )

    # Call the function
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=1,  # Use positive interval to trigger sleep
    )

    # Verify the result
    assert isinstance(result, Success)
    assert "stopped by user" in result.message

    # Verify mocks were called correctly
    mock_configure_output.assert_called_once()
    mock_configure_memory.assert_called_once()
    assert mock_vibe.call_count == 3  # Should be called 3 times
    assert counter[0] == 3  # Counter should reach 3
    assert (
        mock_sleep.call_count == 2
    )  # Sleep should be called after each successful iteration except the last


def test_run_auto_command_with_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test auto command with various error scenarios.

    This comprehensive test covers:
    1. Error with exit_on_error=True (should raise)
    2. Error with exit_on_error=False (should continue)
    3. Error with recovery suggestions
    4. Multiple iterations with errors
    """
    # Mock to check if recovery suggestions are displayed
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.console_manager", mock_console)

    # Mock time.sleep to avoid waiting
    mock_sleep = Mock()
    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock configure functions
    mock_configure_output = Mock(return_value="output_flags")
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_output_flags", mock_configure_output
    )
    mock_configure_memory = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_memory_flags", mock_configure_memory
    )

    # 1. Test with exit_on_error=True
    # Create an error result
    error_result = Error(error="Test error", exception=ValueError("Test error"))
    mock_vibe = Mock(return_value=error_result)
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Should raise when exit_on_error=True
    with pytest.raises(ValueError, match="Error in vibe command"):
        vibectl.subcommands.auto_cmd.run_auto_command(
            request="test request",
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            interval=0,
            exit_on_error=True,
        )

    # 2. Test with exit_on_error=False and recovery suggestions
    mock_console.reset_mock()
    error_with_suggestions = Error(
        error="Resource not found error",
        exception=ValueError("Test error"),
        recovery_suggestions="Try using kubectl get pods instead",
    )

    # Set up sequential mock responses:
    # 1st call: return error with suggestions
    # 2nd call: raise KeyboardInterrupt to exit the loop
    mock_vibe = Mock(side_effect=[error_with_suggestions, KeyboardInterrupt])
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Call with exit_on_error=False, should continue to next iteration
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=1,
        exit_on_error=False,
    )

    # Check it returned Success due to KeyboardInterrupt
    assert isinstance(result, Success)
    assert "stopped by user" in result.message

    # Verify recovery suggestions were printed
    recovery_header_printed = False
    suggestions_printed = False

    # Extract recovery suggestion calls
    for args, _ in mock_console.print_note.call_args_list:
        if args[0] == "Recovery suggestions:":
            recovery_header_printed = True
        elif args[0] == "Try using kubectl get pods instead":
            suggestions_printed = True

    assert recovery_header_printed, "Recovery suggestions header not printed"
    assert suggestions_printed, "Recovery suggestions content not printed"

    # Sleep should be called once (after the error, before KeyboardInterrupt)
    assert mock_sleep.call_count == 1

    # 3. Test general exception in auto_command
    mock_console.reset_mock()
    mock_sleep.reset_mock()

    # Create a special exception to test exception handling
    class TestError(Exception):
        pass

    mock_configure_output = Mock(side_effect=TestError("Configuration error"))
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_output_flags", mock_configure_output
    )

    # Should return Error with exit_on_error=False
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=0,
        exit_on_error=False,
    )

    assert isinstance(result, Error)
    assert "Exception in auto command" in result.error

    # Should raise with exit_on_error=True
    with pytest.raises(TestError, match="Configuration error"):
        vibectl.subcommands.auto_cmd.run_auto_command(
            request="test request",
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            interval=0,
            exit_on_error=True,
        )


def test_auto_command_semiauto_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test semiauto-specific behaviors of the auto command.

    This tests the special behavior of semiauto mode:
    1. No sleep after successful iterations (user confirmation provides pausing)
    2. Sleep after errors in semiauto mode
    3. Special console output for semiauto mode
    4. User requesting exit (Success with continue_execution=False)
    """
    # Mock console_manager to check for semiauto-specific messages
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.console_manager", mock_console)

    # Mock time.sleep to verify it's called or not called appropriately
    mock_sleep = Mock()
    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock configure functions
    mock_configure_output = Mock(return_value="output_flags")
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_output_flags", mock_configure_output
    )
    mock_configure_memory = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_memory_flags", mock_configure_memory
    )

    # 1. Test semiauto with normal success results (should not sleep)
    success_results = [
        Success(message="First success"),
        Success(message="Second success"),
        KeyboardInterrupt,  # To exit the loop
    ]

    mock_vibe = Mock(side_effect=success_results)
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Run in semiauto mode with interval=1
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=1,
        semiauto=True,
        yes=False,
    )

    # Verify no sleep was called (semiauto's natural user confirmation provides pausing)
    assert mock_sleep.call_count == 0

    # Verify semiauto-specific messages were printed
    semiauto_header_printed = False
    confirmation_message_printed = False

    for args, _ in mock_console.print_note.call_args_list:
        if "semiauto" in str(args[0]):
            semiauto_header_printed = True
        if "Commands will require confirmation" in str(args[0]):
            confirmation_message_printed = True

    assert semiauto_header_printed, "Semiauto header not printed"
    assert confirmation_message_printed, "Confirmation message not printed"

    # 2. Test semiauto with error (should NOT sleep in semiauto mode)
    mock_console.reset_mock()
    mock_sleep.reset_mock()

    error_result = Error(error="Test error", exception=ValueError("Test error"))
    mock_vibe = Mock(side_effect=[error_result, KeyboardInterrupt])
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Run in semiauto mode with interval=1 and exit_on_error=False
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=1,
        semiauto=True,
        yes=False,
        exit_on_error=False,
    )

    # Verify sleep was NOT called
    # (even with errors, semiauto mode doesn't need rate limiting)
    assert mock_sleep.call_count == 0

    # 3. Test user exit request (via Success with continue_execution=False)
    mock_console.reset_mock()
    mock_sleep.reset_mock()

    # Create a Success with continue_execution=False to simulate exit request
    exit_result = Success(message="User requested exit", continue_execution=False)
    mock_vibe = Mock(return_value=exit_result)
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Run in semiauto mode
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        semiauto=True,
    )

    # Verify result indicates user exit
    assert isinstance(result, Success)
    assert "exited by user" in result.message

    # Verify the exit message was printed
    exit_message_printed = False
    for args, _ in mock_console.print_note.call_args_list:
        if "exited by user" in str(args[0]):
            exit_message_printed = True

    assert exit_message_printed, "Exit message not printed"


def test_keyboard_interrupt_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test keyboard interrupt handling in both loop and outer levels."""
    # Mock console for checking warnings
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.console_manager", mock_console)

    # Mock other required functions
    mock_configure_output = Mock(return_value="output_flags")
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_output_flags", mock_configure_output
    )
    mock_configure_memory = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_memory_flags", mock_configure_memory
    )

    # 1. Test KeyboardInterrupt in the vibe command (inner loop)
    mock_vibe = Mock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
    )

    # Verify the result
    assert isinstance(result, Success)
    assert "stopped by user" in result.message

    # Check for warning message
    inner_interrupt_warning = False
    for args, _ in mock_console.print_warning.call_args_list:
        if "interrupted by user" in args[0]:
            inner_interrupt_warning = True

    assert inner_interrupt_warning, "Inner interrupt warning not printed"

    # 2. Test KeyboardInterrupt in the outer level (setup phase)
    mock_console.reset_mock()

    # Make configure_memory_flags raise KeyboardInterrupt to simulate
    # keyboard interrupt during setup
    mock_configure_memory = Mock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_memory_flags", mock_configure_memory
    )

    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
    )

    # Verify the result
    assert isinstance(result, Success)
    assert "stopped by user" in result.message

    # Check for warning message
    outer_interrupt_warning = False
    for args, _ in mock_console.print_warning.call_args_list:
        if "interrupted by user" in args[0]:
            outer_interrupt_warning = True

    assert outer_interrupt_warning, "Outer interrupt warning not printed"


def test_run_semiauto_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that run_semiauto_command properly calls run_auto_command with
    the right parameters."""
    # Mock run_auto_command
    mock_auto = Mock(return_value=Success(message="Success"))
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_auto_command", mock_auto)

    # Call the function
    result = vibectl.subcommands.auto_cmd.run_semiauto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=True,  # Test with non-default value
        unfreeze_memory=True,  # Test with non-default value
    )

    # Verify the result
    assert isinstance(result, Success)

    # Verify mock was called with correct arguments
    mock_auto.assert_called_once_with(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=True,  # Should pass through
        unfreeze_memory=True,  # Should pass through
        yes=False,  # Should be False for semiauto
        interval=0,  # Should use 0 interval for semiauto
        semiauto=True,  # Should be True for semiauto
        exit_on_error=False,  # Should be False by default now
        limit=None,  # Should pass through as None by default
    )

    # Test with exit_on_error explicitly set to True
    mock_auto.reset_mock()
    result = vibectl.subcommands.auto_cmd.run_semiauto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        exit_on_error=True,  # Explicitly set to True
    )

    assert isinstance(result, Success)

    # Verify correct parameters are passed
    mock_auto.assert_called_once()
    call_args = mock_auto.call_args[1]
    assert call_args["exit_on_error"] is True


def test_resource_not_found_recovery_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test recovery suggestions are correctly displayed for resource
    not found errors."""
    # Create an error with recovery suggestions
    not_found_error = Error(
        error='Error from server (NotFound): deployments.apps "nginx-demo" not found',
        exception=Exception("Resource not found"),
        recovery_suggestions=(
            "# Kubectl Error Explanation\n\n"
            "The deployment doesn't exist in that namespace\n\n"
            "## Fix Approaches\n\n"
            "- Check deployments with: kubectl get deployments -n sandbox\n"
            "- Look in other namespaces: kubectl get deployments --all-namespaces"
        ),
    )

    # Set up counter to control side effect behavior
    counter = [0]

    def side_effect(*args: Any, **_: Any) -> Any:
        counter[0] += 1
        if counter[0] == 1:
            return not_found_error
        else:
            raise KeyboardInterrupt()

    # Mock vibe_command
    mock_vibe = Mock(side_effect=side_effect)
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Mock console to verify output
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.console_manager", mock_console)

    # Mock other required functions
    mock_configure_output = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_output_flags", mock_configure_output
    )
    mock_configure_memory = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_memory_flags", mock_configure_memory
    )

    # No sleep needed
    mock_sleep = Mock()
    monkeypatch.setattr("time.sleep", mock_sleep)

    # Call function
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="Get deployment nginx-demo",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        exit_on_error=False,
        interval=0,  # No sleep
    )

    # Verify result
    assert isinstance(result, Success)
    assert "stopped by user" in result.message

    # Check for both the header and content of recovery suggestions
    header_printed = False
    content_printed = False
    for call_args in mock_console.print_note.call_args_list:
        if call_args[0][0] == "Recovery suggestions:":
            header_printed = True
        # Check for content fragments
        elif (
            isinstance(call_args[0][0], str)
            and "Check deployments with:" in call_args[0][0]
        ):
            content_printed = True

    assert header_printed, "Recovery suggestions header not printed"
    assert content_printed, "Recovery suggestions content not printed"
