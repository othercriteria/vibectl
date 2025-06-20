"""Runtime overrides for vibectl configuration values.

This lightweight utility lets the root CLI set process-local overrides (via
`contextvars`) without having to thread parameters through every function
call.  Any part of the codebase can query the override using
`overrides.get_override("proxy.active")` (or another config path) **before**
falling back to persisted configuration.

Initially we only need the proxy override but the helper is generic so we can
add model, display flags, etc. later without further plumbing.
"""

from contextvars import ContextVar
from typing import Any

# Internal: one context-local dict holding all overrides.  We avoid a mutable
# default to satisfy flake8-bandit (B039) and similar linters.
_overrides: ContextVar[dict[str, Any] | None] = ContextVar(
    "_vibectl_cli_overrides", default=None
)


def _current_dict() -> dict[str, Any]:
    """Return the current overrides mapping, initialising if necessary."""
    current = _overrides.get()
    if current is None:
        current = {}
        _overrides.set(current)
    return current


def set_override(key: str, value: Any) -> None:
    """Set or update an override for *key*.

    The *key* should be the **full dotted config path** (e.g. ``"proxy.active"``
    or ``"llm.model"``).  ``None`` disables/clears the value but the presence of
    the key still means "explicitly overridden" - this lets callers override a
    config value *to* ``None``.
    """
    current = _current_dict()
    # Copy to avoid mutating the shared dict across ContextVar states
    updated = dict(current)
    updated[key] = value
    _overrides.set(updated)


def get_override(key: str) -> tuple[bool, Any]:
    """Return (is_overridden, value) for *key*.

    *is_overridden* is ``True`` when the CLI explicitly set the key, even if the
    value is ``None``.  This allows the calling code to distinguish between "no
    override" and "override to None".
    """
    current = _overrides.get() or {}
    if key in current:
        return True, current[key]
    return False, None


def clear_overrides() -> None:
    """Reset all overrides - useful in test suites."""
    _overrides.set({})
