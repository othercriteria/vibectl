"""Integration tests for vibectl-server ``config`` CLI sub-commands."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from _pytest.monkeypatch import MonkeyPatch
from click.testing import CliRunner, Result

import vibectl.server.main as server_main

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_server_config_path(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> Iterator[Path]:
    """Redirect server config path to a temp file for isolation."""

    cfg_file = tmp_path / "server-config.yaml"

    import vibectl.server.config as server_config

    monkeypatch.setattr(server_config, "get_server_config_path", lambda: cfg_file)

    yield cfg_file


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> Result:
    runner = CliRunner()
    return runner.invoke(server_main.cli, list(args))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_config_show_defaults() -> None:
    """Showing defaults prints top-level sections."""

    result = _run_cli("config", "show")
    assert result.exit_code == 0, result.output
    assert "server:" in result.output
    assert "jwt:" in result.output


def test_config_set_and_show_value(patch_server_config_path: Path) -> None:
    """Setting a value persists it and show retrieves it."""

    _run_cli("config", "set", "server.port", "6000")

    cfg_file = patch_server_config_path
    data = yaml.safe_load(cfg_file.read_text())
    assert data["server"]["port"] == 6000

    result = _run_cli("config", "show", "server.port")
    assert "server.port: 6000" in result.output.strip()


def test_config_validate_success() -> None:
    """Validate succeeds for a minimal correct config."""

    _run_cli("config", "set", "server.port", "50051")
    result = _run_cli("config", "validate")
    assert result.exit_code == 0


def test_config_show_invalid_section() -> None:
    """Requesting an unknown section exits with error."""

    result = _run_cli("config", "show", "nonexistent")
    assert result.exit_code == 1


def test_config_validate_failure() -> None:
    """Validation fails when config is clearly invalid (out of range port)."""

    _run_cli("config", "set", "server.port", "70000")
    result = _run_cli("config", "validate")
    assert result.exit_code == 1
