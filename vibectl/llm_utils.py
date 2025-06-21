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

from collections.abc import Callable
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
    config: Config | None = None,
    get_adapter: Callable | None = None,
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
        config: Optional ``Config`` instance.  Currently unused but reserved for
            future extension (e.g., adapter selection overrides).
        get_adapter: Optional callable to use for obtaining the model adapter.
        **execute_kwargs: Additional keyword arguments to forward to
            ``model_adapter.execute_and_log_metrics``.

    Returns:
        A tuple ``(response_text, metrics)`` where ``response_text`` is the raw
        string returned by the provider and ``metrics`` contains any associated
        usage/cost information (or ``None`` when unavailable).
    """

    if get_adapter is None:
        # Late import to ensure any monkey-patches performed by tests on
        # ``vibectl.model_adapter.get_model_adapter`` take effect.  Importing
        # lazily also avoids tight coupling that could complicate circular
        # imports when ``run_llm`` is invoked from modules that themselves
        # import this helper at import-time.
        from vibectl.model_adapter import get_model_adapter as _default_get_adapter

        get_adapter = _default_get_adapter

    model_adapter = get_adapter(config)  # type: ignore[arg-type]
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
