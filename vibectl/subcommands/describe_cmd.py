from vibectl.command_handler import (
    OutputFlags,
    configure_output_flags,
    handle_standard_command,
)
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
)
from vibectl.prompt import (
    PLAN_DESCRIBE_PROMPT,
    describe_resource_prompt,
)
from vibectl.types import Error, Result, Success


async def run_describe_command(
    resource: str,
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
) -> Result:
    """
    Implements the 'describe' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(
        f"Invoking 'describe' subcommand with resource: {resource}, args: {args}"
    )

    # Configure output and memory settings
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
            show_metrics=show_metrics,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)
    except Exception as e:
        logger.error(f"Error configuring flags: {e}", exc_info=True)
        return Error(error=f"Error configuring options: {e}", exception=e)

    # Handle 'vibe' command special case
    if resource == "vibe":
        return await _handle_vibe_describe(args, output_flags)

    # Handle standard describe command
    return _handle_standard_describe(resource, args, output_flags)


async def _handle_vibe_describe(args: tuple, output_flags: OutputFlags) -> Result:
    """Handle the 'describe vibe' subcommand."""
    # Ensure we have arguments after 'vibe'
    if not args:
        msg = (
            "Missing request after 'vibe' command. "
            "Please provide a natural language request, e.g.: "
            'vibectl describe vibe "the nginx pod in default"'
        )
        return Error(error=msg)

    # Process the natural language request
    request = " ".join(args)
    logger.info("Planning how to: describe %s", request)

    try:
        # Run the async function in a synchronous context
        result = await handle_vibe_request(
            request=request,
            command="describe",
            plan_prompt_func=lambda: PLAN_DESCRIBE_PROMPT,
            summary_prompt_func=describe_resource_prompt,
            output_flags=output_flags,
            config=None,
        )

        # Return any error unchanged
        if isinstance(result, Error):
            return result

        logger.info("Completed 'describe' subcommand for vibe request.")
        return Success(message="Completed 'describe' subcommand for vibe request.")
    except Exception as e:
        logger.error(f"Error in handle_vibe_request: {e}", exc_info=True)
        return Error(error=f"Exception in handle_vibe_request: {e}", exception=e)


def _handle_standard_describe(
    resource: str, args: tuple, output_flags: OutputFlags
) -> Result:
    """Handle a standard 'describe' command for a specific resource."""
    try:
        result = handle_standard_command(
            command="describe",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=describe_resource_prompt,
        )
        # Return any error unchanged
        if isinstance(result, Error):
            return result

        logger.info(f"Completed 'describe' subcommand for resource: {resource}")
        return Success(
            message=f"Completed 'describe' subcommand for resource: {resource}"
        )
    except Exception as e:
        logger.error(f"Error in handle_standard_command: {e}", exc_info=True)
        err_msg = f"Exception in handle_standard_command: {e}"
        return Error(error=err_msg, exception=e)
