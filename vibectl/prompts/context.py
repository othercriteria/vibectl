"""Prompt context helper.

This module centralises the logic for assembling *system* prompt fragments that
should appear at (almost) every LLM call - namely memory, user-supplied custom
instructions, optional presentation hints produced by planners, and a current
timestamp.  Putting this logic in one place avoids subtle discrepancies between
prompt builders and makes it easy to evolve the context over time (e.g. adding
extra fragments).
"""

from __future__ import annotations

from vibectl.config import Config
from vibectl.prompts.shared import (
    fragment_current_time,
    fragment_memory_context,
)
from vibectl.types import Fragment, SystemFragments

__all__ = ["build_context_fragments"]


def _add_if_not_empty(fragments: SystemFragments, fragment: Fragment | None) -> None:
    """Utility: append *fragment* to *fragments* if it is truthy.

    This avoids sprinkling truthiness checks throughout the core helper below.
    """

    if fragment:
        fragments.append(fragment)


def build_context_fragments(
    cfg: Config,
    *,
    current_memory: str | None = None,
    presentation_hints: str | None = None,
) -> SystemFragments:
    """Construct standard context fragments for prompt builders.

    Parameters
    ----------
    cfg:
        Active :class:`~vibectl.config.Config` instance.  The function never
        creates its own *Config* - callers are expected to provide the one
        already in use so look-ups share identical state.
    current_memory:
        Previously accumulated memory that should be surfaced to the LLM.  The
        fragment is only injected when *both* a) the argument is non-empty and
        b) ``memory.enabled`` is *true* in *cfg*.
    presentation_hints:
        Optional formatting or UI hints coming from a planner response.  When
        provided, the fragment is appended verbatim so downstream summarisation
        or execution prompts can leverage it.

    Returns
    -------
    SystemFragments
        A *mutable list* of :class:`~vibectl.types.Fragment` ready to be merged
        into the caller's system fragment collection.
    """

    system_fragments: SystemFragments = SystemFragments([])

    # 1. Memory context - import lazily to avoid circular import
    from vibectl.memory import (
        is_memory_enabled,
    )

    if current_memory and current_memory.strip() and is_memory_enabled(cfg):
        _add_if_not_empty(system_fragments, fragment_memory_context(current_memory))

    # 2. User-defined custom instructions
    custom_instructions = cfg.get("system.custom_instructions")
    if custom_instructions and str(custom_instructions).strip():
        _add_if_not_empty(
            system_fragments,
            Fragment(f"Custom instructions:\n{custom_instructions}"),
        )

    # 3. Presentation hints from planners
    if presentation_hints and presentation_hints.strip():
        _add_if_not_empty(
            system_fragments,
            Fragment(f"Presentation hints:\n{presentation_hints}"),
        )

    # 4. Always include current timestamp as the final fragment so templates can
    # refer to it consistently regardless of which optional fragments are
    # present.
    _add_if_not_empty(system_fragments, fragment_current_time())

    return system_fragments
