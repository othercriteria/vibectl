import datetime
from collections.abc import Iterable
from pathlib import Path
from unittest.mock import patch

import pytest

from vibectl.config import Config
from vibectl.prompts.context import build_context_fragments


@pytest.fixture()
def fixed_datetime() -> datetime.datetime:  # type: ignore[name-defined]
    """Provide a fixed datetime for deterministic fragment_current_time."""
    return datetime.datetime(2024, 3, 20, 10, 30, 45)


def _combined_text(fragments: Iterable[str]) -> str:
    """Helper to join fragment list into a single string for assertions."""
    return "\n".join(fragments)


def test_build_context_fragments_all(
    tmp_path: Path, fixed_datetime: datetime.datetime
) -> None:
    """All optional context parts should be present when provided and enabled."""
    cfg = Config(base_dir=tmp_path)
    cfg.set("system.custom_instructions", "Be polite at all times.")
    cfg.set("memory.enabled", True)

    current_memory = "Previous stuff about pods"
    presentation_hints = "Prefer bullet points"

    with patch("vibectl.prompts.shared.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_datetime
        fragments = build_context_fragments(
            cfg,
            current_memory=current_memory,
            presentation_hints=presentation_hints,
        )

    combined = _combined_text(fragments)
    assert "Previous Memory:" in combined
    assert current_memory in combined
    assert "Custom instructions:" in combined
    assert "Be polite at all times." in combined
    assert "Presentation hints:" in combined
    assert presentation_hints in combined
    assert fixed_datetime.strftime("%Y-%m-%d %H:%M:%S") in combined


def test_build_context_fragments_memory_disabled(
    tmp_path: Path, fixed_datetime: datetime.datetime
) -> None:
    """Memory fragment should be skipped when memory.enabled is False."""
    cfg = Config(base_dir=tmp_path)
    cfg.set("system.custom_instructions", None)
    cfg.set("memory.enabled", False)

    current_memory = "Should be ignored"

    with patch("vibectl.prompts.shared.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_datetime
        fragments = build_context_fragments(cfg, current_memory=current_memory)

    combined = _combined_text(fragments)
    assert "Previous Memory:" not in combined
    assert current_memory not in combined


def test_build_context_fragments_no_optional(
    tmp_path: Path, fixed_datetime: datetime.datetime
) -> None:
    """Function should still return time fragment when no optional inputs."""
    cfg = Config(base_dir=tmp_path)

    with patch("vibectl.prompts.shared.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_datetime
        fragments = build_context_fragments(cfg)

    combined = _combined_text(fragments)
    # Only the time fragment expected
    assert "Current time is" in combined
    assert fixed_datetime.strftime("%Y-%m-%d %H:%M:%S") in combined
    # Check other markers absent
    assert "Previous Memory:" not in combined
    assert "Custom instructions:" not in combined
    assert "Presentation hints:" not in combined
