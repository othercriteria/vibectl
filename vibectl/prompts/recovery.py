"""
Prompt templates for recovery-related LLM interactions.

This module contains prompts for:
- Recovery action suggestions after command failures
"""

from __future__ import annotations

from vibectl.config import Config
from vibectl.plugins import PromptMapping
from vibectl.types import Fragment, PromptFragments, SystemFragments, UserFragments

from .shared import (
    fragment_concision,
    fragment_current_time,
    with_custom_prompt_override,
)


@with_custom_prompt_override("recovery_suggestions")
def recovery_prompt(
    custom_mapping: PromptMapping | None,
    failed_command: str,
    error_output: str,
    original_explanation: str | None = None,
    config: Config | None = None,
) -> PromptFragments:
    """Generate system and user fragments for suggesting recovery actions."""
    cfg = config or Config()
    max_chars = int(cfg.get("memory.max_chars", 500))

    # Get custom mapping attributes, if provided
    task_description = (
        custom_mapping.get("task_description", "") if custom_mapping else ""
    )
    context_instructions = (
        custom_mapping.get("context_instructions", "") if custom_mapping else ""
    )

    # Use custom task description if provided, otherwise use default
    if task_description:
        system_description = Fragment(task_description)
    else:
        system_description = Fragment(
            "You are a Kubernetes troubleshooting assistant. A kubectl "
            "command failed. Analyze the error and suggest potential "
            "next steps or fixes. Provide concise bullet points."
        )

    system_fragments: SystemFragments = SystemFragments(
        [
            system_description,
            fragment_concision(max_chars),
        ]
    )

    # Build failure information fragment
    failure_parts = [
        f"Failed Command: {failed_command}",
        f"Error Output: {error_output}",
    ]
    if original_explanation:
        failure_parts.append(f"Explanation: {original_explanation}")

    fragment_failure = Fragment("\n".join(failure_parts))

    # Use custom context instructions if provided
    if context_instructions:
        prompt_instruction = Fragment(context_instructions)
    else:
        prompt_instruction = Fragment(
            "Troubleshooting Suggestions (provide concise bullet points "
            "or a brief explanation):"
        )

    user_fragments: UserFragments = UserFragments(
        [
            fragment_current_time(),
            fragment_failure,
            prompt_instruction,
        ]
    )
    return PromptFragments((system_fragments, user_fragments))
