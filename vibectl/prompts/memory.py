"""
Prompt templates for memory-related LLM interactions.

This module contains prompts for:
- Memory update operations
- Memory fuzzy update operations
"""

from __future__ import annotations

from vibectl.config import Config
from vibectl.types import Fragment, PromptFragments, SystemFragments, UserFragments

from .shared import (
    FRAGMENT_MEMORY_ASSISTANT,
    fragment_concision,
    fragment_current_time,
    fragment_memory_context,
)


def memory_update_prompt(
    command_message: str,
    command_output: str,
    vibe_output: str,
    current_memory: str,
    config: Config | None = None,
) -> PromptFragments:
    """Generate system and user fragments for memory update."""
    cfg = config or Config()
    max_chars = int(cfg.get("memory_max_chars", 500))

    system_fragments: SystemFragments = SystemFragments(
        [
            FRAGMENT_MEMORY_ASSISTANT,
            fragment_concision(max_chars),
            Fragment("Based on the context and interaction, give the updated memory."),
        ]
    )

    fragment_interaction = Fragment(f"""Interaction:
Action: {command_message}
Output: {command_output}
Vibe: {vibe_output}
""")

    user_fragments: UserFragments = UserFragments(
        [
            fragment_current_time(),
            fragment_memory_context(current_memory),
            fragment_interaction,
            Fragment("New Memory Summary:"),
        ]
    )
    return PromptFragments((system_fragments, user_fragments))


def memory_fuzzy_update_prompt(
    current_memory: str,
    update_text: str | None = None,
    config: Config | None = None,
) -> PromptFragments:
    """Generate system and user fragments for fuzzy memory update."""
    cfg = config or Config()
    max_chars = int(cfg.get("memory_max_chars", 500))

    system_fragments: SystemFragments = SystemFragments(
        [
            FRAGMENT_MEMORY_ASSISTANT,
            fragment_concision(max_chars),
            Fragment("Based on the user's new information, give the updated memory."),
        ]
    )

    user_fragments: UserFragments = UserFragments(
        [
            fragment_current_time(),
            fragment_memory_context(current_memory),
            Fragment(f"User Update: {update_text}"),
            Fragment("New Memory Summary:"),
        ]
    )
    return PromptFragments((system_fragments, user_fragments))
