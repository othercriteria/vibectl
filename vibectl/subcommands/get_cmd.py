from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
    handle_vibe_request,
    handle_watch_with_live_display,
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

        # Check for --watch flag
        watch_flag_present = "--watch" in args or "-w" in args

        if watch_flag_present:
            logger.info("Handling 'get' command with --watch flag using live display.")
            # Call the new handler for watch with live display
            result = handle_watch_with_live_display(
                command="get",
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=get_resource_prompt,
            )

        else:
            # Use the Result returned from handle_standard_command
            logger.info("Handling standard 'get' command.")
            result = handle_standard_command(
                command="get",
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=get_resource_prompt,
            )

        # Forward the Result from the chosen handler
        if isinstance(result, Error):
            logger.error(f"Error from command handler: {result.error}")
            return result

        logger.info(f"Completed 'get' subcommand for resource: {resource}")

        # Determine final result based on handler's output
        if isinstance(result, Error):
            return result
        result_data = result.data if result.data else None
        if args and args[0] == "vibe":  # vibe request handled
            return Success(
                message="Completed 'get' subcommand for vibe request.",
                data=result_data,
            )
        else:  # Standard get command (including --watch)
            # Use 'resource' parameter directly, args contains only extra flags/params
            return Success(
                message=f"Completed 'get' subcommand for resource: {resource}",
                data=result_data,
            )

    except Exception as e:
        logger.error("Error in 'get' subcommand: %s", e, exc_info=True)
        return Error(
            error="Exception in 'get' subcommand",
            exception=e,
        )
