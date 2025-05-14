"""
Auto command for vibectl.

This module provides the implementation for the 'auto' subcommand,
which reifies the looping 'vibectl vibe --yes' pattern.
"""

import time

from rich.panel import Panel

from vibectl.command_handler import configure_output_flags
from vibectl.config import Config
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags, get_memory
from vibectl.subcommands.vibe_cmd import run_vibe_command
from vibectl.types import Error, Result, Success


async def run_auto_command(
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
    limit: int | None = None,
    show_metrics: bool | None = None,
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
        limit: Maximum number of iterations to run (None for unlimited)
        show_metrics: Whether to show metrics

    Returns:
        Result object (Success or Error)
    """
    logger.info(
        f"Starting '{('semi' if semiauto else '')}auto' command with "
        f"request: {request!r}, limit: {limit}"
    )

    try:
        # Get config first, as it might raise an error handled by the outer except
        cfg = Config()
        show_memory = cfg.get("show_memory", False)
        show_iterations = cfg.get("show_iterations", False)

        # Display a header for the auto session
        mode_name = "semiauto" if semiauto else "auto"
        console_manager.print_note(f"Starting vibectl {mode_name} session")

        if semiauto:
            console_manager.print_note(
                "Starting vibectl semiauto session. "
                "You will be prompted to confirm each command."
            )
            console_manager.print_note(
                "Dangerous commands (e.g., delete, apply) will require confirmation. "
                "Review each step carefully."
            )
            yes_to_pass_to_vibe = False  # Semiauto always requires initial confirmation
            effective_interval = (
                0  # No sleep in semiauto, user confirmation is the pause
            )
        else:  # Full auto mode
            yes_to_pass_to_vibe = True  # <<< MODIFIED: Force True for full auto mode
            effective_interval = interval

        # Show limit information if applicable
        if limit is not None and show_iterations:
            console_manager.print_note(f"Will run for {limit} iterations")

        # Configure output flags and memory
        configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
            show_metrics=show_metrics,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Keep running until stopped
        iteration = 1
        while True:
            # Check iteration limit
            if limit is not None and iteration > limit:
                logger.info(f"Reached iteration limit of {limit}")
                console_manager.print_note(f"Completed {limit} iterations as requested")
                return Success(
                    message=f"Auto session completed after {limit} iterations"
                )

            logger.info(f"Starting iteration {iteration} of auto loop")

            # Show iteration information if enabled
            if show_iterations:
                if limit is not None:
                    console_manager.print_note(f"Iteration {iteration}/{limit}")
                else:
                    console_manager.print_note(f"Iteration {iteration}")

            # Show memory content if configured
            if show_memory:
                memory_content = get_memory()
                if memory_content:
                    console_manager.console.print(
                        Panel(
                            memory_content,
                            title="Memory Content",
                            border_style="blue",
                            expand=False,
                        )
                    )
                else:
                    console_manager.print_warning(
                        "Memory is empty. Use 'vibectl memory set' to add content."
                    )

            # Inner try-except for the vibe command execution within the loop
            try:
                # Run the vibe command with semiauto-specific settings
                result = await run_vibe_command(
                    request=request,
                    show_raw_output=show_raw_output,
                    show_vibe=show_vibe,
                    show_kubectl=show_kubectl,
                    model=model,
                    freeze_memory=freeze_memory,
                    unfreeze_memory=unfreeze_memory,
                    show_metrics=show_metrics,
                    yes=yes_to_pass_to_vibe,
                    semiauto=semiauto,
                    exit_on_error=False,
                )

                # Handle user exit request
                if isinstance(result, Success) and not result.continue_execution:
                    logger.info("User requested exit from auto/semiauto loop")
                    console_manager.print_note("Auto session exited by user")
                    return Success(message="Auto session exited by user")

                # Handle errors
                error_occurred = isinstance(result, Error)
                # Add extra type check for linter to avoid attribute errors
                if error_occurred and isinstance(result, Error):
                    logger.error(f"Error in vibe command: {result.error}")

                    # Display recovery suggestions if they exist
                    if result.recovery_suggestions:
                        logger.info("Displaying recovery suggestions")
                        console_manager.print_note("Recovery suggestions:")
                        console_manager.print_note(result.recovery_suggestions)

                    # Check if this error should halt the auto loop
                    if not result.halt_auto_loop:
                        logger.info("Continuing auto loop despite non-halting error")
                        console_manager.print_note("Continuing to next step...")
                    # Raise error to be caught by outer handler if loop should halt
                    elif exit_on_error and not semiauto:
                        # We raise ValueError specifically, as caught by existing tests
                        raise ValueError(f"Error in vibe command: {result.error}")

            # Catch KeyboardInterrupt within the loop to allow graceful exit
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt detected in auto loop")
                console_manager.print_warning("Auto session interrupted by user")
                return Success(message="Auto session stopped by user")

            # Determine if we need to sleep before next iteration
            # In semiauto mode without error, user confirmation provides natural pausing
            # The test expects that we don't sleep in semiauto mode, even with errors
            if effective_interval > 0 and not semiauto:
                logger.info(
                    f"Completed iteration {iteration}, waiting {effective_interval} "
                    f"seconds before next"
                )
                console_manager.print_note(
                    f"Waiting {effective_interval} seconds before next iteration..."
                )
                time.sleep(effective_interval)

            iteration += 1

    # Outer try-except catches setup errors and KeyboardInterrupt during setup
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt detected during auto command setup")
        console_manager.print_warning("Auto session stopped by user")
        return Success(message="Auto session stopped by user")
    except Exception as e:
        # If exit_on_error is True, always re-raise the original exception
        # to halt execution and allow tests to catch it.
        if exit_on_error:
            # Log before raising might be helpful for debugging
            logger.error(f"Halting auto command due to error: {e}", exc_info=True)
            raise e

        # If exit_on_error is False (e.g., during testing or specific scenarios):
        # Log the error and return an Error object.
        log_msg = f"Error during auto command execution: {e}"
        logger.error(log_msg, exc_info=True)
        return Error(error=log_msg, exception=e)


async def run_semiauto_command(
    request: str | None,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    exit_on_error: bool = False,
    limit: int | None = None,
    show_metrics: bool | None = None,
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
        exit_on_error: If True, errors will terminate the process.
           If False (default for semiauto), errors are handled gracefully
           and the loop continues.
        limit: Maximum number of iterations to run (None for unlimited)
        show_metrics: Whether to show metrics

    Returns:
        Result object (Success or Error)
    """
    logger.info(
        f"Starting 'semiauto' command with request: {request!r}, limit: {limit}"
    )

    return await run_auto_command(
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
        limit=limit,  # Pass the iteration limit
        show_metrics=show_metrics,
    )
