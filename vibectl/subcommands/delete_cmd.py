from vibectl.command_handler import (
    configure_output_flags,
    handle_standard_command,
    handle_vibe_request,
)
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags, include_memory_in_prompt
from vibectl.prompt import PLAN_DELETE_PROMPT, delete_resource_prompt
from vibectl.types import Error, Result, Success


def run_delete_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    show_kubectl: bool | None = None,
    yes: bool = False,
) -> Result:
    """
    Implements the 'delete' subcommand logic, including vibe handling, confirmation,
    and error handling. Returns a Result (Success or Error).
    """
    logger.info(
        f"Invoking 'delete' subcommand for resource: {resource} with args: {args}"
    )
    try:
        # Configure output flags
        output_flags = configure_output_flags(
            show_raw_output=show_raw_output, show_vibe=show_vibe, model=model
        )
        # Configure memory flags
        configure_memory_flags(freeze_memory, unfreeze_memory)

        # Handle vibe command
        if resource == "vibe":
            if not args:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl delete vibe "the nginx deployment in default"'
                )
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: delete %s", request)
            try:
                handle_vibe_request(
                    request=request,
                    command="delete",
                    plan_prompt=include_memory_in_prompt(PLAN_DELETE_PROMPT),
                    summary_prompt_func=delete_resource_prompt,
                    output_flags=output_flags,
                    yes=yes,
                )
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'delete' subcommand for vibe request.")
            return Success(message="Completed 'delete' subcommand for vibe request.")

        # Handle standard command without confirmation
        try:
            handle_standard_command(
                command="delete",
                resource=resource,
                args=args,
                output_flags=output_flags,
                summary_prompt_func=delete_resource_prompt,
            )
        except Exception as e:
            logger.error("Error running standard delete command: %s", e, exc_info=True)
            return Error(error="Exception running standard delete command", exception=e)
        logger.info("Completed 'delete' subcommand.")
        return Success(message="Completed 'delete' subcommand.")
    except Exception as e:
        logger.error("Error in 'delete' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'delete' subcommand", exception=e)
