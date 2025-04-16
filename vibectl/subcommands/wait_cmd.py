from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
    handle_vibe_request,
    handle_wait_with_live_display,
)
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags, include_memory_in_prompt
from vibectl.prompt import PLAN_WAIT_PROMPT, wait_resource_prompt
from vibectl.types import Error, Result, Success
from vibectl.utils import handle_exception


def run_wait_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    live_display: bool = True,
) -> Result:
    """
    Implements the 'wait' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(
        f"Invoking 'wait' subcommand with resource: {resource}, args: {args}, live_display: {live_display}"
    )
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Special case for vibe command
        if resource == "vibe":
            if len(args) < 1:
                msg = "Missing request after 'vibe'"
                console_manager.print_error(msg)
                logger.error(msg + " in wait subcommand.")
                return Error(error=msg)
            request = " ".join(args)
            try:
                handle_vibe_request(
                    request=request,
                    command="wait",
                    plan_prompt=include_memory_in_prompt(PLAN_WAIT_PROMPT),
                    summary_prompt_func=wait_resource_prompt,
                    output_flags=output_flags,
                )
            except Exception as e:
                logger.error(f"Error in handle_vibe_request: {e}")
                handle_exception(e)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'wait' subcommand for vibe request.")
            return Success(message="Completed 'wait' subcommand for vibe request.")

        # Handle command with live display
        if live_display:
            logger.info(f"Handling wait with live display for resource: {resource}")
            handle_wait_with_live_display(
                resource=resource,
                args=args,
                output_flags=output_flags,
            )
            logger.info(f"Completed wait with live display for resource: {resource}")
            return Success(
                message=f"Completed wait with live display for resource: {resource}"
            )
        else:
            # Standard command without live display
            logger.info(f"Handling standard wait command for resource: {resource}")
            handle_standard_command(
                command="wait",
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=wait_resource_prompt,
            )
            logger.info(f"Completed standard wait command for resource: {resource}")
            return Success(
                message=f"Completed standard wait command for resource: {resource}"
            )
    except Exception as e:
        logger.error(f"Error in 'wait' subcommand: {e}")
        handle_exception(e)
        return Error(error="Exception in 'wait' subcommand", exception=e)
