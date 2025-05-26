"""
Prompt templates for recovery-related LLM interactions.

This module contains prompts for:
- Recovery action suggestions after command failures
"""

from __future__ import annotations

from vibectl.config import Config
from vibectl.types import Fragment, PromptFragments, SystemFragments, UserFragments

from .shared import fragment_concision, fragment_current_time


def recovery_prompt(
    failed_command: str,
    error_output: str,
    current_memory: str,
    original_explanation: str | None = None,
    config: Config | None = None,
) -> PromptFragments:
    """Generate system and user fragments for suggesting recovery actions."""
    cfg = config or Config()
    max_chars = int(cfg.get("memory_max_chars", 500))

    system_fragments: SystemFragments = SystemFragments(
        [
            Fragment(
                "You are a Kubernetes troubleshooting assistant. A kubectl "
                "command failed. Analyze the error and suggest potential "
                "next steps or fixes. Provide concise bullet points."
            ),
            fragment_concision(max_chars),
        ]
    )

    fragment_failure = Fragment(f"""Failed Command: {failed_command}
Error Output: {error_output}
{(original_explanation or "") and f"Explanation: {original_explanation}"}""")

    user_fragments: UserFragments = UserFragments(
        [
            fragment_current_time(),
            fragment_failure,
            Fragment(
                "Troubleshooting Suggestions (provide concise bullet points "
                "or a brief explanation):"
            ),
        ]
    )
    return PromptFragments((system_fragments, user_fragments))
