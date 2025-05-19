from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
    handle_wait_with_live_display,
)
from vibectl.config import Config
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import PLAN_WAIT_PROMPT, wait_resource_prompt
from vibectl.types import Error, Result, Success


async def run_wait_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    live_display: bool = True,
    show_metrics: bool | None = None,
) -> Result:
    """
    Implements the 'wait' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(
        f"Invoking 'wait' subcommand with resource: {resource}, args: {args}, "
        f"live_display: {live_display}"
    )
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
            show_metrics=show_metrics,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Special case for vibe command
        if resource == "vibe":
            if len(args) < 1:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl wait vibe "for the nginx pod to be ready"'
                )
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: wait for %s", request)

            # Use the Result returned by handle_vibe_request
            result = await handle_vibe_request(
                request=request,
                command="wait",
                plan_prompt_func=lambda: PLAN_WAIT_PROMPT,
                summary_prompt_func=wait_resource_prompt,
                output_flags=output_flags,
                config=Config(),
            )

            # Forward any errors from handle_vibe_request
            if isinstance(result, Error):
                logger.error(f"Error from handle_vibe_request: {result.error}")
                return result

            logger.info("Completed 'wait' subcommand for vibe request.")
            return Success(
                message="Completed 'wait' subcommand for vibe request.",
                data=result.data
                if isinstance(result, Success) and result.data
                else None,
            )

        # Handle command with live display
        if live_display:
            logger.info(f"Handling wait with live display for resource: {resource}")

            # Use the Result returned by handle_wait_with_live_display
            result = await handle_wait_with_live_display(
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=wait_resource_prompt,
            )

            # Forward any errors from handle_wait_with_live_display
            if isinstance(result, Error):
                logger.error(
                    f"Error from handle_wait_with_live_display: {result.error}"
                )
                return result

            logger.info(f"Completed wait with live display for resource: {resource}")
            return Success(
                message=f"Completed wait with live display for resource: {resource}",
                data=result.data
                if isinstance(result, Success) and result.data
                else None,
            )
        else:
            # Standard command without live display
            logger.info(f"Handling standard wait command for resource: {resource}")

            # Use the Result returned by handle_standard_command
            result = handle_standard_command(
                command="wait",
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=wait_resource_prompt,
            )

            # Forward any errors from handle_standard_command
            if isinstance(result, Error):
                logger.error(f"Error from handle_standard_command: {result.error}")
                return result

            logger.info(f"Completed standard wait command for resource: {resource}")
            return Success(
                message=f"Completed standard wait command for resource: {resource}",
                data=result.data
                if isinstance(result, Success) and result.data
                else None,
            )
    except Exception as e:
        logger.error("Error in 'wait' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'wait' subcommand", exception=e)
