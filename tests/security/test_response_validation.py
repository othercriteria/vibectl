import pytest

from vibectl.schema import CommandAction
from vibectl.security.response_validation import ValidationOutcome, validate_action
from vibectl.types import ExecutionMode


@pytest.mark.parametrize(
    "commands, exec_mode, expected",
    [
        # Read-only verbs are always SAFE
        (["get", "pods"], ExecutionMode.MANUAL, ValidationOutcome.SAFE),
        # Destructive verb - CONFIRM in MANUAL/SEMIAUTO, SAFE in AUTO
        (["delete", "pod", "foo"], ExecutionMode.MANUAL, ValidationOutcome.CONFIRM),
        (["delete", "pod", "foo"], ExecutionMode.SEMIAUTO, ValidationOutcome.CONFIRM),
        (["delete", "pod", "foo"], ExecutionMode.AUTO, ValidationOutcome.SAFE),
        # Dangerous flag triggers CONFIRM regardless of mode
        (
            ["delete", "pod", "foo", "--grace-period=0"],
            ExecutionMode.MANUAL,
            ValidationOutcome.CONFIRM,
        ),
        # Manifest-apply is considered potentially destructive → CONFIRM (non-AUTO)
        (
            ["apply", "-f", "deploy.yml"],
            ExecutionMode.MANUAL,
            ValidationOutcome.CONFIRM,
        ),
        # Chain operators are outright rejected
        (
            ["get", "pods", "&&", "echo", "MAL"],
            ExecutionMode.MANUAL,
            ValidationOutcome.REJECT,
        ),
        # Flag-only invocation (e.g. stdin manifest) is SAFE
        (["-f", "-"], ExecutionMode.MANUAL, ValidationOutcome.SAFE),
    ],
)
def test_validate_command_action(
    commands: list[str], exec_mode: ExecutionMode, expected: ValidationOutcome
) -> None:
    action = CommandAction(commands=commands)
    result = validate_action(action, exec_mode)
    assert result.outcome is expected
