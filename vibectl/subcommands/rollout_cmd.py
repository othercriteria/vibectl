import asyncio

import click

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    run_kubectl,
)
from vibectl.console import console_manager
from vibectl.execution.vibe import handle_vibe_request
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import (
    PLAN_ROLLOUT_PROMPT,
    rollout_general_prompt,
    rollout_history_prompt,
    rollout_status_prompt,
)
from vibectl.types import Error, Result, Success


async def run_rollout_command(
    subcommand: str,
    resource: str,
    args: tuple,
    show_raw_output: bool | None = None,
    show_vibe: bool | None = None,
    show_kubectl: bool | None = None,
    model: str | None = None,
    freeze_memory: bool = False,
    unfreeze_memory: bool = False,
    yes: bool = False,
    exit_on_error: bool = True,
    show_metrics: bool | None = None,
) -> Result:
    """
    Implements the 'rollout' subcommands logic, including logging and error handling.

    Specifically, these are: status, history, undo, restart, pause, resume, vibe.

    Returns a Result (Success or Error).
    """
    logger.info(
        "Invoking 'rollout' subcommand: %s resource: %s, args: %s",
        subcommand,
        resource,
        args,
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

        # Handle 'vibe' mode
        if subcommand == "vibe":
            if not resource:
                msg = (
                    "Missing request after 'vibe' command. "
                    "Please provide a natural language request, e.g.: "
                    'vibectl rollout vibe "restart the nginx deployment"'
                )
                logger.error(msg + " in rollout subcommand.", exc_info=True)
                return Error(error=msg)
            request = " ".join(args)
            logger.info("Planning how to: rollout %s", request)
            try:
                result_vibe = await handle_vibe_request(
                    request=request,
                    command="rollout",
                    plan_prompt_func=lambda: PLAN_ROLLOUT_PROMPT,
                    summary_prompt_func=rollout_general_prompt,
                    output_flags=output_flags,
                )
                logger.info("Completed 'rollout' subcommand for vibe request.")
                return result_vibe
            except Exception as e:
                logger.error("Error in handle_vibe_request: %s", e, exc_info=True)
                return Error(error="Exception in handle_vibe_request", exception=e)

        # Map subcommand to kubectl rollout subcommand and summary prompt
        rollout_map = {
            "status": ("status", rollout_status_prompt),
            "history": ("history", rollout_history_prompt),
            "undo": ("undo", rollout_general_prompt),
            "restart": ("restart", rollout_general_prompt),
            "pause": ("pause", rollout_general_prompt),
            "resume": ("resume", rollout_general_prompt),
        }
        if subcommand not in rollout_map:
            msg = f"Unknown rollout subcommand: {subcommand}"
            logger.error(msg)
            return Error(error=msg)
        kubectl_subcmd, summary_prompt_func = rollout_map[subcommand]

        # Confirmation for undo
        if kubectl_subcmd == "undo" and not yes:
            confirmation_message = (
                f"Are you sure you want to undo the rollout for {resource}?"
            )
            if not click.confirm(confirmation_message):
                logger.info("Operation cancelled by user.")
                console_manager.print_note("Operation cancelled")
                return Success(message="Operation cancelled")

        cmd = ["rollout", kubectl_subcmd, resource, *args]
        logger.info(f"Running kubectl command: {' '.join(cmd)}")
        try:
            # Run kubectl command in a separate thread
            kubectl_result = await asyncio.to_thread(run_kubectl, cmd)

            if isinstance(kubectl_result, Error):
                logger.error(f"Error running kubectl: {kubectl_result.error}")
                return kubectl_result

            output_data = kubectl_result.data
            if not output_data:
                logger.info("No output from kubectl rollout command.")
                if "console_manager" in globals():
                    console_manager.print_note(
                        "No output from kubectl rollout command."
                    )
                return Success(message="No output from kubectl rollout command.")

        except Exception as e:
            logger.error("Error running kubectl: %s", e, exc_info=True)
            return Error(error="Exception running kubectl", exception=e)

        try:
            await asyncio.to_thread(
                handle_command_output,
                output=kubectl_result,
                output_flags=output_flags,
                summary_prompt_func=summary_prompt_func,
            )
        except Exception as e:
            logger.error("Error in handle_command_output: %s", e, exc_info=True)
            return Error(error="Exception in handle_command_output", exception=e)

        logger.info(
            f"Completed 'rollout' subcommand: {subcommand} for resource: {resource}"
        )
        return Success(
            message=(
                f"Completed 'rollout' subcommand: {subcommand} for resource: {resource}"
            )
        )
    except Exception as e:
        logger.error("Error in 'rollout' subcommand: %s", e, exc_info=True)
        return Error(error="Exception in 'rollout' subcommand", exception=e)
