from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
    handle_vibe_request,
)
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
    get_memory,
)
from vibectl.prompt import (
    PLAN_DESCRIBE_PROMPT,
    describe_resource_prompt,
)
from vibectl.types import Error, Result, Success


def run_describe_command(
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
    Implements the 'describe' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(
        f"Invoking 'describe' subcommand with resource: {resource}, args: {args}"
    )
    try:
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output,
            show_vibe=show_vibe,
            model=model,
            show_kubectl=show_kubectl,
        )
        configure_memory_flags(freeze_memory, unfreeze_memory)

        if resource == "vibe":
            if not args:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl describe vibe "the nginx pod in default"'
                )
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: %s", request)
            planning_msg = f"Planning how to: describe {request}"
            console_manager.print_processing(planning_msg)
            try:
                handle_vibe_request(
                    request=request,
                    command="describe",
                    plan_prompt=PLAN_DESCRIBE_PROMPT,
                    summary_prompt_func=describe_resource_prompt,
                    output_flags=output_flags,
                    memory_context=get_memory() or "",
                )
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'describe' subcommand for vibe request.")
            return Success(message="Completed 'describe' subcommand for vibe request.")

        try:
            handle_standard_command(
                command="describe",
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=describe_resource_prompt,
            )
        except Exception as e:
            logger.error("Error in handle_standard_command: %s", e, exc_info=True)
            return Error(error="Exception in handle_standard_command", exception=e)
        logger.info(f"Completed 'describe' subcommand for resource: {resource}")
        return Success(
            message=f"Completed 'describe' subcommand for resource: {resource}"
        )
    except Exception as e:
        logger.error("Error in 'describe' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'describe' subcommand", exception=e)
