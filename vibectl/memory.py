"""Memory management for vibectl.

This module provides functionality for managing and updating the memory
that is maintained between vibectl commands.
"""

from collections.abc import Callable
from typing import cast

from .config import Config
from .model_adapter import get_model_adapter
from .prompt import memory_update_prompt


def get_memory(config: Config | None = None) -> str:
    """Get current memory content from configuration.

    Args:
        config: Optional Config instance. If not provided, creates a new one.

    Returns:
        str: Current memory content or empty string if not set
    """
    cfg = config or Config()
    return cast("str", cfg.get("memory", ""))


def is_memory_enabled(config: Config | None = None) -> bool:
    """Check if memory is enabled.

    Args:
        config: Optional Config instance. If not provided, creates a new one.

    Returns:
        bool: True if memory is enabled, False otherwise
    """
    cfg = config or Config()
    return cast("bool", cfg.get("memory_enabled", True))


def set_memory(memory_text: str, config: Config | None = None) -> None:
    """Set memory content, respecting the maximum length limit.

    Args:
        memory_text: The memory content to set
        config: Optional Config instance. If not provided, creates a new one.
    """
    cfg = config or Config()
    max_chars = cfg.get("memory_max_chars", 500)

    # Truncate if needed
    if memory_text and len(memory_text) > max_chars:
        memory_text = memory_text[:max_chars]

    cfg.set("memory", memory_text)
    cfg.save()


def enable_memory(config: Config | None = None) -> None:
    """Enable memory updates.

    Args:
        config: Optional Config instance. If not provided, creates a new one.
    """
    cfg = config or Config()
    cfg.set("memory_enabled", True)
    cfg.save()


def disable_memory(config: Config | None = None) -> None:
    """Disable memory updates.

    Args:
        config: Optional Config instance. If not provided, creates a new one.
    """
    cfg = config or Config()
    cfg.set("memory_enabled", False)
    cfg.save()


def clear_memory(config: Config | None = None) -> None:
    """Clear memory content.

    Args:
        config: Optional Config instance. If not provided, creates a new one.
    """
    cfg = config or Config()
    cfg.set("memory", "")
    cfg.save()


def update_memory(
    command: str,
    command_output: str,
    vibe_output: str,
    model_name: str = "claude-3.7-sonnet",
    config: Config | None = None,
) -> None:
    """Update memory with new command execution context.

    This function takes a command, its output, and the AI's interpretation
    and uses them to update the memory content via an LLM call.

    Args:
        command: The command that was executed
        command_output: The raw output from the command
        vibe_output: The AI's interpretation of the command output
        model_name: Model name to use for memory update
        config: Optional Config instance to use
    """
    if not is_memory_enabled(config):
        return

    cfg = config or Config()

    # Use model adapter instead of direct llm usage
    model_adapter = get_model_adapter(cfg)
    model = model_adapter.get_model(model_name)
    prompt = memory_update_prompt(command, command_output, vibe_output, cfg)

    updated_memory = model_adapter.execute(model, prompt)
    set_memory(updated_memory, cfg)


def include_memory_in_prompt(
    prompt_template: str | Callable[[], str], config: Config | None = None
) -> str:
    """Include memory in a prompt template if available and enabled.

    Args:
        prompt_template: The prompt template or callable returning template
        config: Optional Config instance. If not provided, creates a new one.

    Returns:
        str: Updated prompt with memory context if available
    """
    cfg = config or Config()

    # If memory is disabled or empty, return original prompt
    if not is_memory_enabled(cfg):
        return prompt_template() if callable(prompt_template) else prompt_template

    memory = get_memory(cfg)
    if not memory:
        return prompt_template() if callable(prompt_template) else prompt_template

    # Get the prompt text
    prompt = prompt_template() if callable(prompt_template) else prompt_template

    # Insert memory context after formatting instructions and before the actual prompt
    memory_section = f"""
Memory context:
{memory}

"""

    # Try to find an appropriate insertion point
    # Check for common markers in our prompts
    if "Important:" in prompt:
        # Insert before the "Important:" section
        prompt = prompt.replace("Important:", f"{memory_section}Important:")
    elif "Example format:" in prompt:
        # Insert before the "Example format:" section
        prompt = prompt.replace("Example format:", f"{memory_section}Example format:")
    elif "Example inputs and outputs:" in prompt:
        # Insert before the "Example inputs and outputs:" section
        prompt = prompt.replace(
            "Example inputs and outputs:",
            f"{memory_section}Example inputs and outputs:",
        )
    else:
        # If no marker found, just add at the beginning
        prompt = f"{memory_section}{prompt}"

    return prompt


def configure_memory_flags(freeze: bool, unfreeze: bool) -> None:
    """Configure memory behavior based on flags.

    Args:
        freeze: Whether to disable memory updates for this command
        unfreeze: Whether to enable memory updates for this command

    Raises:
        ValueError: If both freeze and unfreeze are specified
    """
    if freeze and unfreeze:
        raise ValueError("Cannot specify both --freeze-memory and --unfreeze-memory")

    cfg = Config()

    if freeze:
        disable_memory(cfg)
    elif unfreeze:
        enable_memory(cfg)
