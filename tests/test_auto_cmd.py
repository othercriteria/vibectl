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


def test_run_auto_command_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test auto command with an error in vibe command."""
    # Mock run_vibe_command to return an error
    error_result = Error(error="Test error", exception=ValueError("Test error"))
    mock_vibe = Mock(return_value=error_result)
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

    # Call the function with exit_on_error=True (default) for this test
    with pytest.raises(ValueError, match="Error in vibe command"):
        vibectl.subcommands.auto_cmd.run_auto_command(
            request="test request",
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            interval=0,
            exit_on_error=True,  # This should cause the error to be raised
        )

    # Verify mocks were called correctly
    mock_configure_output.assert_called_once()
    mock_configure_memory.assert_called_once()
    mock_vibe.assert_called_once()
    # Error message is now logged instead of printed to console
    mock_sleep.assert_not_called()  # Sleep should not be called on error

    # Now test with exit_on_error=False
    mock_vibe.reset_mock()
    mock_console.reset_mock()
    mock_configure_output.reset_mock()
    mock_configure_memory.reset_mock()

    # Set up the mock to raise KeyboardInterrupt after the first iteration
    # to prevent infinite loops in the test
    mock_vibe = Mock(side_effect=[error_result, KeyboardInterrupt])
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # This time we shouldn't raise an exception but instead get an Error result
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=1,  # Use a positive interval value to trigger sleep
        exit_on_error=False,  # This should prevent the error from being raised
    )

    # With exit_on_error=False, it should attempt to continue and then be
    # interrupted by our KeyboardInterrupt in the second iteration
    assert isinstance(result, Success)
    assert "stopped by user" in result.message
    assert mock_vibe.call_count == 2
    # We no longer expect print_error to be called
    assert mock_sleep.call_count == 1  # Sleep should be called once after the error


def test_run_semiauto_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test semiauto command, which should call run_auto_command with semiauto=True."""
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
        freeze_memory=False,
        unfreeze_memory=False,
        yes=False,  # Should be False for semiauto
        interval=0,  # Should use 0 interval for semiauto
        semiauto=True,  # Should be True for semiauto
        exit_on_error=True,
    )


def test_auto_command_exit_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test auto command with Success(continue_execution=False) from vibe command."""
    # Mock run_vibe_command to return Success with continue_execution=False
    mock_vibe = Mock(
        return_value=Success(message="User requested exit", continue_execution=False)
    )
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
        interval=0,
        semiauto=True,  # Use semiauto mode
    )

    # Verify the result
    assert isinstance(result, Success)
    assert "exited by user" in result.message

    # Verify mocks were called correctly
    mock_configure_output.assert_called_once()
    mock_configure_memory.assert_called_once()
    mock_vibe.assert_called_once()
    mock_console.print_note.assert_called()
    mock_sleep.assert_not_called()


def test_semiauto_mode_with_exit_on_error_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test semiauto command with exit_on_error set to False."""
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
        exit_on_error=False,
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
        freeze_memory=False,
        unfreeze_memory=False,
        yes=False,
        interval=0,
        semiauto=True,
        exit_on_error=False,
    )


def test_auto_command_zero_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test auto command with zero interval (no sleep)."""
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

    # Call the function with interval=0
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=0,  # Zero interval should skip sleep
    )

    # Verify the result
    assert isinstance(result, Success)
    assert "stopped by user" in result.message

    # Verify sleep was not called
    mock_sleep.assert_not_called()


def test_auto_command_semiauto_no_sleep_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test auto command with Success(continue_execution=False)
    where there's no error."""
    # Create a Success with continue_execution=False
    exit_result = Success(message="User requested exit", continue_execution=False)

    # Set up multiple return values
    mock_vibe = Mock(
        side_effect=[
            Success(message="First success"),
            Success(message="Second success"),
            exit_result,
        ]
    )
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

    # Call the function in semiauto mode with a positive interval and
    # exit_on_error=False
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=1,
        semiauto=True,  # Use semiauto mode
        exit_on_error=True,  # Not relevant for this test
    )

    # Verify the result
    assert isinstance(result, Success)
    assert "exited by user" in result.message

    # Verify mocks were called correctly
    assert mock_vibe.call_count == 3  # Should be called 3 times

    # In semiauto mode without errors, sleep is not called because user confirmation
    # provides natural pausing - this behavior is documented in auto_cmd.py
    assert mock_sleep.call_count == 0  # No sleep in semiauto mode without errors


def test_auto_command_semiauto_with_error_sleeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test semiauto mode sleeps after errors despite being in semiauto mode."""
    # Mock run_vibe_command to return an error and then raise KeyboardInterrupt
    error_result = Error(error="Test error", exception=ValueError("Test error"))
    mock_vibe = Mock(side_effect=[error_result, KeyboardInterrupt])
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Mock time.sleep to verify it's called
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

    # Call the function in semiauto mode with a positive interval and
    # exit_on_error=False
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=5,
        semiauto=True,  # Enable semiauto mode
        exit_on_error=False,  # Don't exit on error
    )

    # Verify the result
    assert isinstance(result, Success)
    assert "stopped by user" in result.message

    # Verify sleep was called once after the error
    mock_sleep.assert_called_once_with(5)


def test_auto_command_with_error_exit_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test auto command with Error after some iterations."""
    # Set up multiple return values - success then error
    mock_vibe = Mock(
        side_effect=[
            Success(message="First success"),
            Success(message="Second success"),
            Error(error="Error in loop"),
        ]
    )
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

    # Call the function - with exit_on_error=True, should raise
    with pytest.raises(ValueError, match="Error in vibe command"):
        vibectl.subcommands.auto_cmd.run_auto_command(
            request="test request",
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            interval=1,
            semiauto=True,  # Use semiauto mode
            exit_on_error=True,  # This should cause the error to be raised
        )

    # Reset mocks
    mock_vibe.reset_mock()
    mock_sleep.reset_mock()

    # Now reset the side effect
    mock_vibe = Mock(
        side_effect=[
            Success(message="First success"),
            Success(message="Second success"),
            Error(error="Error in loop"),
            KeyboardInterrupt,  # Add this to exit the loop
        ]
    )
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)

    # Call the function - with exit_on_error=False, should continue
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=1,
        semiauto=True,  # Use semiauto mode
        exit_on_error=False,  # This should allow continuation after error
    )

    # Verify mocks were called correctly
    assert mock_vibe.call_count == 4  # Should be called 4 times

    # In semiauto mode:
    # - No sleep after successful iterations (confirmation provides natural pausing)
    # - But sleep *is* called after an error occurs
    assert mock_sleep.call_count == 1  # Called after error only

    # Verify result
    assert isinstance(result, Success)
    assert "stopped by user" in result.message


def test_general_exception_in_auto_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test handling of general exceptions in auto command."""
    # Mock configure_output_flags to raise an exception
    mock_configure_output = Mock(side_effect=ValueError("Test error"))
    monkeypatch.setattr(
        "vibectl.subcommands.auto_cmd.configure_output_flags", mock_configure_output
    )

    # Mock console_manager
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.auto_cmd.console_manager", mock_console)

    # Call the function with exit_on_error=False
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=5,
        exit_on_error=False,
    )

    # Verify the result is an Error
    assert isinstance(result, Error)
    assert "Exception in auto command" in result.error

    # Verify that with exit_on_error=True (default), it raises the exception
    with pytest.raises(ValueError, match="Test error"):
        vibectl.subcommands.auto_cmd.run_auto_command(
            request="test request",
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            interval=5,
        )


def test_exception_in_middle_of_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test an exception being thrown in the middle of the auto loop."""
    # Set up a counter to track calls
    counter = [0]

    # Define a side effect that will succeed once, then throw a ValueError
    def side_effect(*args: Any, **kwargs: Any) -> Success:
        counter[0] += 1
        if counter[0] == 1:
            # First call succeeds
            return Success(message="Completed vibe")
        else:
            # Second call raises an exception
            raise ValueError("Test exception in middle of loop")

    # Mock run_vibe_command with our side effect
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

    # Call the function with exit_on_error=False to get the error as a return value
    result = vibectl.subcommands.auto_cmd.run_auto_command(
        request="test request",
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        interval=0,  # No need to sleep in test
        exit_on_error=False,  # Get an Error result instead of raising
    )

    # Verify the result is an Error with our exception message
    assert isinstance(result, Error)
    assert "Test exception in middle of loop" in result.error

    # Verify appropriate methods were called
    assert mock_vibe.call_count == 2  # Called twice
    mock_sleep.assert_not_called()  # Interval is 0

    # Reset mocks for the second test case
    mock_vibe.reset_mock()
    counter[0] = 0  # Reset the counter

    # Use a different approach to directly test the exception raising part
    # Create a subclass of Exception for this specific test
    class TestError(Exception):
        pass

    # A function that always raises our test exception
    def raise_exception(*args: Any, **kwargs: Any) -> None:
        raise TestError("Direct exception test")

    # Replace run_auto_command's original implementation with one that directly raises
    original_func = vibectl.subcommands.auto_cmd.run_auto_command

    # This mock will directly test the except block
    try:
        monkeypatch.setattr(
            "vibectl.subcommands.auto_cmd.run_vibe_command", raise_exception
        )

        # Call function with exit_on_error=True to verify it raises
        with pytest.raises(TestError, match="Direct exception test"):
            original_func(
                request="test request",
                show_raw_output=None,
                show_vibe=None,
                show_kubectl=None,
                model=None,
                interval=0,
                exit_on_error=True,  # This should cause it to re-raise
            )
    finally:
        # Restore the function to its original state
        monkeypatch.setattr("vibectl.subcommands.auto_cmd.run_vibe_command", mock_vibe)
