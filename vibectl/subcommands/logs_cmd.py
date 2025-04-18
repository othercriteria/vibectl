from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_vibe_request,
    run_kubectl,
)
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags, include_memory_in_prompt
from vibectl.prompt import PLAN_LOGS_PROMPT, logs_prompt
from vibectl.types import Error, Result, Success

MAX_TOKEN_LIMIT = 10000
LOGS_TRUNCATION_RATIO = 3


def run_logs_command(
    resource: str,
    args: tuple,
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
) -> Result:
    """
    Implements the 'logs' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'logs' subcommand with resource: {resource}, args: {args}")
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
            if not args:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl logs vibe "the nginx pod in default"'
                )
                return Error(error=msg)
            request = " ".join(args)
            planning_msg = f"Planning how to: logs {request}"
            console_manager.print_processing(planning_msg)
            try:
                handle_vibe_request(
                    request=request,
                    command="logs",
                    plan_prompt=include_memory_in_prompt(PLAN_LOGS_PROMPT),
                    summary_prompt_func=logs_prompt,
                    output_flags=output_flags,
                )
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'logs' subcommand for vibe request.")
            return Success(message="Completed 'logs' subcommand for vibe request.")

        # Regular logs command
        cmd = ["logs", resource, *args]
        logger.info(f"Running kubectl command: {' '.join(cmd)}")
        try:
            output = run_kubectl(cmd, capture=True)
        except Exception as e:
            logger.error("Error running kubectl: %s", e, exc_info=True)
            return Error(error="Exception running kubectl", exception=e)

        if not output:
            logger.info("No output from kubectl logs command.")
            return Success(message="No output from kubectl logs command.")

        # handle_command_output will handle truncation warnings and output display
        handle_command_output(
            output=output,
            output_flags=output_flags,
            summary_prompt_func=logs_prompt,
            max_token_limit=MAX_TOKEN_LIMIT,
            truncation_ratio=LOGS_TRUNCATION_RATIO,
        )
        logger.info("Completed 'logs' subcommand for resource: %s", resource)
        return Success(message=f"Completed 'logs' subcommand for resource: {resource}")
    except Exception as e:
        logger.error("Error in 'logs' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'logs' subcommand", exception=e)
