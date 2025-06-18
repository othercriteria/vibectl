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
        result = determine_execution_mode(yes=False, semiauto=False)
        assert result is expected
    finally:
        clear_overrides()


def test_determine_execution_mode_legacy_flags() -> None:
    """Legacy flag logic still works when no override is present."""
    # yes -> AUTO
    clear_overrides()
    assert determine_execution_mode(yes=True, semiauto=False) is ExecutionMode.AUTO

    # semiauto True has priority
    assert determine_execution_mode(yes=True, semiauto=True) is ExecutionMode.SEMIAUTO

    # default is MANUAL
    assert determine_execution_mode(yes=False, semiauto=False) is ExecutionMode.MANUAL
