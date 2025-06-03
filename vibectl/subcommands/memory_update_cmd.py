"""
Handles the logic for the 'vibectl memory update' command.
"""

from vibectl.config import DEFAULT_CONFIG, Config
from vibectl.console import console_manager
from vibectl.memory import get_memory, set_memory
from vibectl.model_adapter import get_model_adapter
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

        model_adapter = get_model_adapter(cfg)
        model_instance = model_adapter.get_model(model_name_to_use)

        system_fragments, user_fragments_template = memory_fuzzy_update_prompt(
            current_memory=current_memory, update_text=update_text_str, config=cfg
        )

        filled_user_fragments = []
        for template_str in user_fragments_template:
            try:
                filled_user_fragments.append(
                    Fragment(template_str.format(update_text=update_text_str))
                )
            except KeyError:
                filled_user_fragments.append(Fragment(template_str))

        console_manager.print_processing(
            f"Updating memory using {model_name_to_use}..."
        )

        # Simulate LLMMetrics for now if not fully returned by all adapters
        # In a real scenario, execute_and_log_metrics would return this
        updated_memory, llm_metrics = await model_adapter.execute_and_log_metrics(
            model=model_instance,
            system_fragments=system_fragments,
            user_fragments=UserFragments(filled_user_fragments),
        )

        set_memory(updated_memory, cfg)
        # Include metrics in success data if available
        success_data = (
            f"Memory updated successfully.\nUpdated Memory Content:\n{updated_memory}"
        )

        return Success(data=success_data, metrics=llm_metrics)

    except Exception as e:
        return Error(error=f"Failed to update memory: {e}", exception=e)
