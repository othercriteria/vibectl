"""
Handles the logic for the 'vibectl memory update' command.
"""

from vibectl.config import DEFAULT_CONFIG, Config
from vibectl.console import console_manager
from vibectl.llm_utils import run_llm
from vibectl.memory import get_memory, set_memory
from vibectl.prompts.memory import memory_fuzzy_update_prompt
from vibectl.types import Error, Fragment, Result, Success, UserFragments


async def run_memory_update_logic(
    update_text_str: str, model_name: str | None
) -> Result:
    """
    Core logic to update memory using LLM.

    Args:
        update_text_str: The text to update memory with.
        model_name: Optional model name to override config.

    Returns:
        A Result object (Success or Error).
    """
    try:
        cfg = Config()
        current_memory = get_memory(cfg)
        model_name_to_use = model_name or cfg.get(
            "llm.model", DEFAULT_CONFIG["llm"]["model"]
        )

        console_manager.print_processing(
            f"Updating memory using {model_name_to_use}..."
        )

        # Build prompt fragments for the memory update
        system_fragments, user_fragments_template = memory_fuzzy_update_prompt(
            current_memory=current_memory,
            update_text=update_text_str,
            config=cfg,
        )

        filled_user_fragments: list[Fragment] = []
        for template_str in user_fragments_template:
            try:
                filled_user_fragments.append(
                    Fragment(template_str.format(update_text=update_text_str))
                )
            except KeyError:
                filled_user_fragments.append(Fragment(template_str))

        # Use shared helper for LLM execution
        updated_memory, llm_metrics = await run_llm(
            system_fragments=system_fragments,
            user_fragments=UserFragments(filled_user_fragments),
            model_name=model_name_to_use,
            metrics_source="LLM Memory Update",
            config=cfg,
        )

        set_memory(updated_memory, cfg)
        # Include metrics in success data if available
        success_data = (
            f"Memory updated successfully.\nUpdated Memory Content:\n{updated_memory}"
        )

        return Success(data=success_data, metrics=llm_metrics)

    except Exception as e:
        return Error(error=f"Failed to update memory: {e}", exception=e)
