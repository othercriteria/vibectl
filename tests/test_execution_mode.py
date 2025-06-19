import pytest

from vibectl.overrides import clear_overrides, set_override
from vibectl.types import ExecutionMode, determine_execution_mode


@pytest.mark.parametrize(
    "override, expected",
    [
        ("auto", ExecutionMode.AUTO),
        ("manual", ExecutionMode.MANUAL),
        ("semiauto", ExecutionMode.SEMIAUTO),
    ],
)
def test_determine_execution_mode_with_override(
    override: str, expected: ExecutionMode
) -> None:
    """determine_execution_mode should honor ContextVar overrides over legacy flags."""
    try:
        set_override("execution.mode", override)
        result = determine_execution_mode(semiauto=False)
        assert result is expected
    finally:
        clear_overrides()


def test_determine_execution_mode_semiauto_and_default() -> None:
    """determine_execution_mode should respect semiauto flag and default to MANUAL."""
    clear_overrides()

    # semiauto True maps to SEMIAUTO
    assert determine_execution_mode(semiauto=True) is ExecutionMode.SEMIAUTO

    # default is MANUAL when no semiauto and no overrides
    assert determine_execution_mode(semiauto=False) is ExecutionMode.MANUAL
