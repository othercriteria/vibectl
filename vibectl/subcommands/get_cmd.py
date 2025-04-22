from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
    handle_vibe_request,
)
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
    get_memory,
)
from vibectl.prompt import (
    PLAN_GET_PROMPT,
    get_resource_prompt,
)
from vibectl.types import Error, Result, Success


def run_get_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
) -> Result:
    """
    Implements the 'get' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'get' subcommand with resource: {resource}, args: {args}")
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        if resource == "vibe":
            if len(args) < 1:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl get vibe "all nginx pods in kube-system"'
                )
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: %s", request)

            # Use the Result returned from handle_vibe_request
            result = handle_vibe_request(
                request=request,
                command="get",
                plan_prompt=PLAN_GET_PROMPT,
                summary_prompt_func=get_resource_prompt,
                output_flags=output_flags,
                memory_context=get_memory() or "",
            )

            # Forward the Result from handle_vibe_request
            if isinstance(result, Error):
                logger.error(f"Error from handle_vibe_request: {result.error}")
                return result

            logger.info("Completed 'get' subcommand for vibe request.")
            return Success(
                message="Completed 'get' subcommand for vibe request.",
                data=result.data
                if isinstance(result, Success) and result.data
                else None,
            )

        # Use the Result returned from handle_standard_command
        result = handle_standard_command(
            command="get",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=get_resource_prompt,
        )

        # Forward the Result from handle_standard_command
        if isinstance(result, Error):
            logger.error(f"Error from handle_standard_command: {result.error}")
            return result

        logger.info(f"Completed 'get' subcommand for resource: {resource}")
        return Success(
            message=f"Completed 'get' subcommand for resource: {resource}",
            data=result.data if isinstance(result, Success) and result.data else None,
        )
    except Exception as e:
        logger.error("Error in 'get' subcommand: %s", e, exc_info=True)
        return Error(
            error="Exception in 'get' subcommand",
            exception=e,
        )
