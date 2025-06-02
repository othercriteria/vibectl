import asyncio

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
)
from vibectl.config import Config
from vibectl.execution.apply import run_intelligent_apply_workflow
from vibectl.execution.vibe import (
    handle_vibe_request,
)
from vibectl.k8s_utils import run_kubectl
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.prompts.apply import (
    apply_output_prompt,
    apply_plan_prompt,
)
from vibectl.types import (
    Error,
    MetricsDisplayMode,
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
    show_metrics: MetricsDisplayMode | None,
    show_streaming: bool | None,
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
        show_streaming=show_streaming,
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

        if cfg.get_typed("intelligent_apply", True):
            return await run_intelligent_apply_workflow(request, cfg, output_flags)
        else:  # Not intelligent_apply
            logger.info("Using standard vibe request handler for apply.")
            # Ensure result is awaited if handle_vibe_request is async
            result_standard_vibe = await handle_vibe_request(
                request=request,
                command="apply",
                plan_prompt_func=apply_plan_prompt,
                summary_prompt_func=apply_output_prompt,
                output_flags=output_flags,
                yes=False,
            )

            if isinstance(result_standard_vibe, Error):
                logger.error(
                    f"Error from handle_vibe_request: {result_standard_vibe.error}"
                )
                return result_standard_vibe

            logger.info("Completed 'apply' subcommand for standard vibe request.")
            return result_standard_vibe

    else:
        cmd = ["apply", *args]

        kubectl_result_direct: Result = await asyncio.to_thread(
            run_kubectl,
            cmd=cmd,
            config=cfg,
        )

        if isinstance(kubectl_result_direct, Error):
            logger.error(
                f"Error running kubectl for direct apply: {kubectl_result_direct.error}"
            )
            return kubectl_result_direct

        result_direct_apply = await handle_command_output(
            output=kubectl_result_direct,
            output_flags=output_flags,
            summary_prompt_func=apply_output_prompt,
        )

        logger.info("Completed direct 'apply' subcommand execution.")
        return result_direct_apply
