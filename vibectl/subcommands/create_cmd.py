from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_vibe_request,
    run_kubectl,
)
from vibectl.logutil import logger
from vibectl.memory import (
    configure_memory_flags,
    include_memory_in_prompt,
)
from vibectl.prompt import (
    PLAN_CREATE_PROMPT,
    create_resource_prompt,
)
from vibectl.types import Error, Result, Success


def run_create_command(
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
    Implements the 'create' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'create' subcommand with resource: {resource}, args: {args}")
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
                    'vibectl create vibe "an nginx pod in default"'
                )
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: create %s", request)
            try:
                handle_vibe_request(
                    request=request,
                    command="create",
                    plan_prompt=include_memory_in_prompt(PLAN_CREATE_PROMPT),
                    summary_prompt_func=create_resource_prompt,
                    output_flags=output_flags,
                )
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)
            logger.info("Completed 'create' subcommand for vibe request.")
            return Success(message="Completed 'create' subcommand for vibe request.")

        # Regular create command
        cmd = ["create", resource, *args]
        logger.info(f"Running kubectl command: {' '.join(cmd)}")
        try:
            output = run_kubectl(cmd, capture=True)
        except Exception as e:
            logger.error("Error running kubectl: %s", e, exc_info=True)
            return Error(error="Exception running kubectl", exception=e)

        if not output:
            logger.info("No output from kubectl create command.")
            return Success(message="No output from kubectl create command.")

        try:
            handle_command_output(
                output=output,
                output_flags=output_flags,
                summary_prompt_func=create_resource_prompt,
            )
        except Exception as e:
            logger.error("Error in handle_command_output: %s", e, exc_info=True)
            return Error(error="Exception in handle_command_output", exception=e)

        logger.info(f"Completed 'create' subcommand for resource: {resource}")
        return Success(
            message=f"Completed 'create' subcommand for resource: {resource}"
        )
    except Exception as e:
        logger.error("Error in 'create' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'create' subcommand", exception=e)
