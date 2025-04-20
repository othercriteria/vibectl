"""
Auto command for vibectl.

This module provides the implementation for the 'auto' subcommand,
which reifies the looping 'vibectl vibe --yes' pattern.
"""

import time

from vibectl.command_handler import configure_output_flags
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.subcommands.vibe_cmd import run_vibe_command
from vibectl.types import Error, Result, Success


def run_auto_command(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    yes: bool = True,
    interval: int = 5,
    semiauto: bool = False,
    exit_on_error: bool = True,
) -> Result:
    """
    Implements the auto subcommand logic, including looping
    behavior and confirmation options.

    Args:
        request: Natural language request from the user
        show_raw_output: Whether to show raw output
        show_vibe: Whether to show vibe output
        show_kubectl: Whether to show kubectl commands
        model: Model name to use for vibe
        freeze_memory: Whether to freeze memory
        unfreeze_memory: Whether to unfreeze memory
        yes: Whether to automatically confirm actions (default:
            True for auto, False for semiauto)
        interval: Seconds to wait between loop iterations
        semiauto: Whether we're in semiauto mode with manual confirmation
        exit_on_error: If True (default), errors will terminate the process.
           If False, errors are returned as Error objects for tests.

    Returns:
        Result object (Success or Error)
    """
    logger.info(
        f"Starting '{('semi' if semiauto else '')}auto' command with "
        f"request: {request!r}"
    )

    # Display a header for the auto session
    mode_name = "semiauto" if semiauto else "auto"
    console_manager.print_note(f"Starting vibectl {mode_name} session")

    if semiauto:
        console_manager.print_note("Commands will require confirmation.")
        console_manager.print_note(
            "Use [Y]es, [N]o, [A]nd, [B]ut, or [E]xit to respond."
        )
    else:
        console_manager.print_note(
            "Commands will execute automatically (no confirmation needed)."
        )

    try:
        # Configure output flags and memory
        configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Keep running until stopped
        iteration = 1
        while True:
            logger.info(f"Starting iteration {iteration} of auto loop")
            console_manager.print_note(f"--- Iteration {iteration} ---")

            # If in semiauto mode, we need to modify the yes flag
            exec_yes = yes
            if semiauto:
                exec_yes = False  # Override to False for semiauto mode

            error_occurred = False
            try:
                # Run the vibe command
                result = run_vibe_command(
                    request=request,
                    show_raw_output=show_raw_output,
                    show_vibe=show_vibe,
                    show_kubectl=show_kubectl,
                    model=model,
                    freeze_memory=freeze_memory,
                    unfreeze_memory=unfreeze_memory,
                    yes=exec_yes,
                    semiauto=semiauto,
                    exit_on_error=False,  # Handle errors here instead
                )

                # Check if we got an error
                if isinstance(result, Error):
                    # Log the error but don't duplicate the error message to the console
                    # as it was already printed in vibe_cmd.py
                    logger.error(f"Error in vibe command: {result.error}")
                    error_occurred = True

                    # Display recovery suggestions if they exist
                    if result.recovery_suggestions:
                        logger.info("Displaying recovery suggestions")
                        console_manager.print_note("Recovery suggestions:")
                        console_manager.print_note(result.recovery_suggestions)

                    if exit_on_error:
                        raise ValueError(f"Error in vibe command: {result.error}")

                # Check if we got a Success with continue_execution=False
                elif isinstance(result, Success) and not result.continue_execution:
                    # User requested to exit the loop
                    logger.info("User requested exit from auto/semiauto loop")
                    console_manager.print_note("Auto session exited by user")
                    return Success(message="Auto session exited by user")

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt detected in auto loop")
                console_manager.print_warning("Auto session interrupted by user")
                return Success(message="Auto session stopped by user")

            # Wait before next iteration
            logger.info(
                f"Completed iteration {iteration}, waiting {interval} "
                f"seconds before next"
            )

            # Wait between iterations unless we're in semiauto mode AND
            # no error occurred
            # In semiauto mode without error, user confirmation provides
            # natural pausing
            # With errors or in auto mode, we always need to sleep
            if interval > 0 and (not semiauto or error_occurred):
                console_manager.print_note(
                    f"Waiting {interval} seconds before next iteration..."
                )
                time.sleep(interval)

            iteration += 1

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt detected in auto command")
        console_manager.print_warning("Auto session interrupted by user")
        return Success(message="Auto session stopped by user")

    except Exception as e:
        logger.error(f"Error in auto command: {e}")
        if exit_on_error:  # pragma: no cover - difficult to trigger in tests,
            # covered by integration tests
            raise
        return Error(error=f"Exception in auto command: {e}", exception=e)


def run_semiauto_command(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    exit_on_error: bool = True,
) -> Result:
    """
    Implements the semiauto subcommand logic, which is sugar
    for auto with manual confirmation.

    This just calls run_auto_command with semiauto=True and yes=False.

    Args:
        request: Natural language request from the user
        show_raw_output: Whether to show raw output
        show_vibe: Whether to show vibe output
        show_kubectl: Whether to show kubectl commands
        model: Model name to use for vibe
        freeze_memory: Whether to freeze memory
        unfreeze_memory: Whether to unfreeze memory
        exit_on_error: If True (default), errors will terminate the process.
           If False, errors are returned as Error objects for tests.

    Returns:
        Result object (Success or Error)
    """
    logger.info(f"Starting 'semiauto' command with request: {request!r}")

    return run_auto_command(
        request=request,
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        show_kubectl=show_kubectl,
        model=model,
        freeze_memory=freeze_memory,
        unfreeze_memory=unfreeze_memory,
        yes=False,  # Override to False for semiauto
        interval=0,  # Use 0 interval as semiauto has natural pausing through user input
        semiauto=True,  # Set semiauto mode
        exit_on_error=exit_on_error,
    )
