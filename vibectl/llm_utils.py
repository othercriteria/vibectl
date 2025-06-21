"""Utility helpers for interacting with the LLM adapter.

This module currently exposes a single ``run_llm`` coroutine that consolidates
common boiler-plate required for executing a prompt and collecting metrics.

Historically, many call-sites repeated the following steps:

1. ``model_adapter = get_model_adapter()``
2. ``model = model_adapter.get_model(model_name)``
3. ``response, metrics = await model_adapter.execute_and_log_metrics(...)``
4. Optionally accumulate metrics via a ``LLMMetricsAccumulator``.

The new helper wraps these steps to reduce repetition and unify behaviour.
Future refactors can gradually migrate modules to use ``run_llm``.
"""

from typing import Any

from vibectl.config import Config
from vibectl.types import (
    LLMMetrics,
    LLMMetricsAccumulator,
    SystemFragments,
    UserFragments,
)

__all__ = ["run_llm"]


async def run_llm(
    system_fragments: SystemFragments,
    user_fragments: UserFragments,
    model_name: str,
    *,
    metrics_acc: LLMMetricsAccumulator | None = None,
    metrics_source: str = "LLM Call",
    config: Config,
    **execute_kwargs: Any,
) -> tuple[str, LLMMetrics | None]:
    """Execute **one** LLM call and optionally accumulate its metrics.

    Args:
        system_fragments: The ``SystemFragments`` to pass to the model.
        user_fragments: The ``UserFragments`` to pass to the model.
        model_name: Identifier of the model to use (e.g. ``"claude-3-sonnet"``).
        metrics_acc: Optional ``LLMMetricsAccumulator`` which, when provided,
            will receive the call metrics via ``add_metrics``.
        metrics_source: A human-readable label describing the call. This is
            forwarded to ``metrics_acc.add_metrics``.
        config: The active ``Config`` instance driving this CLI invocation. **This
            parameter is now required** so that all call-sites share a single,
            explicit configuration context.
        **execute_kwargs: Additional keyword arguments forwarded verbatim to
            ``model_adapter.execute_and_log_metrics``.

    Returns:
        A tuple ``(response_text, metrics)`` where ``response_text`` is the raw
        string returned by the provider and ``metrics`` contains any associated
        usage/cost information (or ``None`` when unavailable).

    Call-site convention (2025-06-21):
        >>> response, metrics = await run_llm(
        ...     system_fragments=system_frags,
        ...     user_fragments=user_frags,
        ...     model_name=model_name,
        ...     config=cfg,  # <-- Always pass the active Config
        ... )
    """

    # Late import ensures that any monkey-patches applied by tests to
    # ``vibectl.model_adapter.get_model_adapter`` are respected. Importing
    # lazily also avoids potential circular-import issues.
    from vibectl.model_adapter import get_model_adapter as _get_adapter

    model_adapter = _get_adapter(config)
    model = model_adapter.get_model(model_name)

    # Step 3 - execute prompt & gather metrics
    response_text, metrics = await model_adapter.execute_and_log_metrics(
        model=model,
        system_fragments=system_fragments,
        user_fragments=user_fragments,
        **execute_kwargs,
    )

    # Step 4 - accumulate metrics if requested
    if metrics_acc is not None:
        metrics_acc.add_metrics(metrics, metrics_source)

    return response_text, metrics
