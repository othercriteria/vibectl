from vibectl.cli import (
    configure_memory_flags,
    configure_output_flags,
    handle_vibe_request,
)
from vibectl.command_handler import handle_standard_command
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import include_memory_in_prompt
from vibectl.prompt import (
    PLAN_GET_PROMPT,
    get_resource_prompt,
)
from vibectl.types import Error, Result, Success
from vibectl.utils import handle_exception


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
                msg = "Missing request after 'vibe'"
                console_manager.print_error(msg)
                logger.error(msg + " in get subcommand.")
                return Error(error=msg)
            request = " ".join(args)
            try:
                handle_vibe_request(
                    request=request,
                    command="get",
                    plan_prompt=include_memory_in_prompt(PLAN_GET_PROMPT),
                    summary_prompt_func=get_resource_prompt,
                    output_flags=output_flags,
                )
            except Exception as e:
                logger.error(f"Error in handle_vibe_request: {e}")
                handle_exception(e)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'get' subcommand for vibe request.")
            return Success(message="Completed 'get' subcommand for vibe request.")

        handle_standard_command(
            command="get",
            resource=resource,
            args=args,
            output_flags=output_flags,
            summary_prompt_func=get_resource_prompt,
        )
        logger.info(f"Completed 'get' subcommand for resource: {resource}")
        return Success(message=f"Completed 'get' subcommand for resource: {resource}")
    except Exception as e:
        logger.error(f"Error in 'get' subcommand: {e}")
        handle_exception(e)
        return Error(error="Exception in 'get' subcommand", exception=e)
