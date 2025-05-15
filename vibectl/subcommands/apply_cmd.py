import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
    handle_vibe_request,
)
from vibectl.config import Config
from vibectl.k8s_utils import run_kubectl
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompt import PLAN_APPLY_PROMPT, apply_output_prompt
from vibectl.types import (
    Error,
    Result,
)


async def run_apply_command(
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
    Implements the 'apply' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'apply' subcommand with args: {args}")
    configure_memory_flags(freeze_memory, unfreeze_memory)

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
    )

    cfg = Config()

    if args[0] == "vibe":
        args = args[1:]
        if len(args) < 1:
            msg = (
                "Missing request after 'vibe' command. "
                "Please provide a natural language request, e.g.: "
                'vibectl apply vibe "server side new.yaml"'
            )
            return Error(error=msg)
        request = " ".join(args)
        logger.info(f"Planning how to: {request}")

        result = await handle_vibe_request(
            request=request,
            command="apply",
            plan_prompt_func=lambda: PLAN_APPLY_PROMPT,
            summary_prompt_func=apply_output_prompt,
            output_flags=output_flags,
            yes=False,
        )

        if isinstance(result, Error):
            logger.error(f"Error from handle_vibe_request: {result.error}")
            return result

        logger.info("Completed 'apply' subcommand for vibe request.")
    else:
        cmd = ["apply", *args]

        kubectl_result: Result = await asyncio.to_thread(
            run_kubectl,
            cmd=cmd,
            config=cfg,
        )

        if isinstance(kubectl_result, Error):
            logger.error(f"Error running kubectl: {kubectl_result.error}")
            # Propagate the error object
            return kubectl_result

        result = await asyncio.to_thread(
            handle_command_output,
            output=kubectl_result,
            output_flags=output_flags,
            summary_prompt_func=apply_output_prompt,
        )

        logger.info("Completed direct 'apply' subcommand execution.")

    return result
