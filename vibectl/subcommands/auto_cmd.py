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
    limit: int | None = None,
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
                "Dangerous commands (e.g., delete, apply) will require confirmation."
            )
        else:
            console_manager.print_note(
                "Commands will execute automatically (no confirmation needed)."
            )

        # Show limit information if applicable
        if limit is not None and show_iterations:
            console_manager.print_note(f"Will run for {limit} iterations")

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
                result = run_vibe_command(
                    request=request,
                    show_raw_output=show_raw_output,
                    show_vibe=show_vibe,
                    show_kubectl=show_kubectl,
                    model=model,
                    freeze_memory=freeze_memory,
                    unfreeze_memory=unfreeze_memory,
                    # Override yes flag in semiauto mode
                    yes=yes if not semiauto else False,
                    semiauto=semiauto,
                    # Handle errors here instead of in run_vibe_command
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
            if interval > 0 and not semiauto:
                logger.info(
                    f"Completed iteration {iteration}, waiting {interval} "
                    f"seconds before next"
                )
                console_manager.print_note(
                    f"Waiting {interval} seconds before next iteration..."
                )
                time.sleep(interval)

            iteration += 1

    # Outer try-except catches setup errors and KeyboardInterrupt during setup
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt detected during auto command setup")
        console_manager.print_warning("Auto session interrupted by user")
        return Success(message="Auto session stopped by user")

    except Exception as e:
        # Catch any other unexpected exception during setup or loop exit logic
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
    exit_on_error: bool = False,
    limit: int | None = None,
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

    Returns:
        Result object (Success or Error)
    """
    logger.info(
        f"Starting 'semiauto' command with request: {request!r}, limit: {limit}"
    )

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
        limit=limit,  # Pass the iteration limit
    )
