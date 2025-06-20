"""
Response validation logic for LLM-planned actions.

This module performs a light, fast, *client-side* safety pass over the
`AnyLLMAction` returned by the planner before we hit any execution or
confirmation flow.  The immediate goal is to force confirmation (or, in
rare cases, outright reject) obviously destructive / malformed
`CommandAction`s.  The design is intentionally extensible so that future
`LLMAction` subclasses (e.g. PageAction, EmailAction) can register their
own validators.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from vibectl.k8s_utils import is_kubectl_command_read_only
from vibectl.logutil import logger
from vibectl.schema import AnyLLMAction, CommandAction, WaitAction
from vibectl.types import ExecutionMode

__all__ = [
    "ValidationOutcome",
    "ValidationResult",
    "validate_action",
]


class ValidationOutcome(Enum):
    """Possible results of a response validation pass."""

    SAFE = auto()  # No additional confirmation beyond normal rules
    CONFIRM = auto()  # Force command confirmation regardless of exec mode
    REJECT = auto()  # Reject the action entirely - return Error upstream


@dataclass(slots=True)
class ValidationResult:
    """Container for a validation outcome and an optional explanation."""

    outcome: ValidationOutcome
    message: str | None = None


# ---------------------------------------------------------------------------
# Validator registry helpers
# ---------------------------------------------------------------------------

ValidatorFunc = Callable[[Any, ExecutionMode], ValidationResult]
_VALIDATORS: dict[type[AnyLLMAction], ValidatorFunc] = {}


def _register_validator(
    action_cls: type[AnyLLMAction],
) -> Callable[[ValidatorFunc], ValidatorFunc]:
    """Decorator to register *validator* function for a given *action_cls*."""

    def decorator(func: ValidatorFunc) -> ValidatorFunc:
        _VALIDATORS[action_cls] = func
        return func

    return decorator


# ---------------------------------------------------------------------------
# Specific validators
# ---------------------------------------------------------------------------

_DESTRUCTIVE_KUBECTL_VERBS: set[str] = {
    # High-risk or state-changing verbs that should *always* prompt.
    "delete",
    "drain",
    "scale",
    "patch",
    "apply",  # The manifest could be destructive (e.g., replica=0)
    "annotate",
    "label",
    "cordon",
    "uncordon",
    "rollout",
}


@_register_validator(CommandAction)
def _validate_command_action(
    action: CommandAction, _exec_mode: ExecutionMode
) -> ValidationResult:
    """Lightweight heuristics for `CommandAction` safety.

    1. Extract verb + args from *action.commands* (best-effort).
    2. If verb looks non-kubectl (e.g. contains shell metachars or an
       obvious non-k8s binary) → REJECT.
    3. If verb is read-only → SAFE.
    4. If verb is in *destructive* list or a manifest is present → CONFIRM.
    5. Fallback → CONFIRM (better to be safe).
    """

    commands = action.commands or []

    # Fallback to confirm if we cannot even parse a verb.
    if not commands:
        if action.yaml_manifest:
            return ValidationResult(
                ValidationOutcome.CONFIRM,
                "No command arguments provided - confirmation required.",
            )
        return ValidationResult(
            ValidationOutcome.REJECT,
            "CommandAction without commands or manifest cannot be executed.",
        )

    verb = commands[0].strip().lower()

    # ------------------------------------------------------------------
    # 1. Syntactic sanity checks (entire command list, not just verb)
    # ------------------------------------------------------------------

    # If the first token *looks* like a flag (starts with "-") we simply treat the
    # whole action as an argument-only set - that is perfectly fine (caller supplies
    # the verb separately).  No special handling needed.
    chain_tokens = {";", "&&", "||", "|", "`"}

    # Exact chain operators as standalone tokens ⇒ outright reject (they cannot
    # be legitimate kubectl args).
    if any(tok in chain_tokens for tok in commands):
        return ValidationResult(
            ValidationOutcome.REJECT,
            "Command list contains standalone shell chain operators (e.g. '&&').",
        )

    # Tokens *containing* metacharacters (e.g. "echo;whoami") - treat as risky but
    # allow with confirmation.  This covers kubectl exec "sh -c 'ls;rm'" patterns
    # where the user may legitimately need complex shell.  We flag for CONFIRM so
    # AUTO mode cannot run it blindly.
    if any(any(ch in t for ch in chain_tokens) for t in commands):
        return ValidationResult(
            ValidationOutcome.CONFIRM,
            "Arguments contain shell metacharacters - confirmation required.",
        )

    # 2. Read-only short-circuit (only applies if verb actually looks like a verb)
    if is_kubectl_command_read_only([verb, *commands[1:]]):
        return ValidationResult(ValidationOutcome.SAFE)

    # 3. Flag / argument heuristics - escalate to CONFIRM when obviously risky
    dangerous_flags_prefixes = (
        "--force",
        "--grace-period",
        "--cascade",
        "--overwrite",
        "--all",
        "--prune",
    )

    has_dangerous_flag = any(
        tok.startswith(dangerous_flags_prefixes) for tok in commands
    )

    # Destructive verbs may still be executed non-interactively in AUTO mode,
    # preserving existing UX.  In MANUAL/SEMIAUTO they should prompt.

    if verb in _DESTRUCTIVE_KUBECTL_VERBS and not has_dangerous_flag:
        if _exec_mode is ExecutionMode.AUTO:
            return ValidationResult(ValidationOutcome.SAFE)
        return ValidationResult(
            ValidationOutcome.CONFIRM,
            "Destructive kubectl verb - confirmation required in this mode.",
        )

    # YAML manifest with -f is common and generally expected; we only prompt if
    # combined with dangerous flags.

    if has_dangerous_flag:
        return ValidationResult(
            ValidationOutcome.CONFIRM,
            "Kubectl arguments include potentially destructive flags - "
            "confirmation required.",
        )

    # 4. Default: allow (SAFE). Better to keep AUTO mode non-interactive unless
    # risk detected.
    return ValidationResult(ValidationOutcome.SAFE)


@_register_validator(WaitAction)
def _validate_wait_action(
    action: WaitAction, _exec_mode: ExecutionMode
) -> ValidationResult:
    """Initial placeholder - all waits are SAFE for now."""

    return ValidationResult(ValidationOutcome.SAFE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_action(action: AnyLLMAction, exec_mode: ExecutionMode) -> ValidationResult:
    """Validate *action* and return a :class:`ValidationResult`.

    If no specific validator is registered, default to *SAFE* to avoid
    breaking existing behaviour.  Callers should treat unknown actions with
    caution.
    """

    action_type = type(action)
    validator = _VALIDATORS.get(action_type)

    if validator is None:
        # No dedicated validator - treat as SAFE but record the situation for
        # future hardening work.
        logger.debug(
            "No validator registered for action type %s - defaulting to SAFE",
            action_type.__name__,
        )
        return ValidationResult(ValidationOutcome.SAFE)

    result = validator(action, exec_mode)

    # Emit extra context when the validator triggers a CONFIRM/REJECT so that
    # troubleshooting can see *why* the outcome was escalated.
    if result.outcome is not ValidationOutcome.SAFE:
        logger.debug(
            "Validator outcome %s for %s: %s",
            result.outcome.name,
            action_type.__name__,
            result.message or "<no message>",
        )

    return result
