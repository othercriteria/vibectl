from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.server import overrides as server_overrides
from vibectl.server.config import ServerConfig, Success, get_default_server_config
from vibectl.server.main import cli


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    """Ensure ContextVar overrides are cleared around each test."""
    server_overrides.clear_overrides()
    yield
    server_overrides.clear_overrides()


def _mock_common_success(mock_load: Mock, mock_start: Mock) -> None:
    """Helper that wires Success returns into common server helpers."""
    cfg = get_default_server_config()
    mock_load.return_value = Success(data=cfg)
    mock_start.return_value = Success()


def test_cli_flags_set_contextvar_overrides() -> None:
    """--max-rpm / --max-concurrent should populate ContextVar overrides."""
    runner = CliRunner()
    with (
        patch("vibectl.server.main._load_and_validate_config") as mock_load,
        patch("vibectl.server.main._create_and_start_server_common") as mock_start,
        patch("vibectl.server.main.console_manager"),
    ):
        _mock_common_success(mock_load, mock_start)

        result = runner.invoke(
            cli,
            [
                "serve-insecure",
                "--max-rpm",
                "7",
                "--max-concurrent",
                "3",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # Overrides should be visible globally
        assert server_overrides.get_override(
            "server.limits.global.max_requests_per_minute"
        ) == (True, 7)
        assert server_overrides.get_override(
            "server.limits.global.max_concurrent_requests"
        ) == (True, 3)

        # And reflected through ServerConfig.get_limits()
        limits = ServerConfig().get_limits()
        assert limits.max_requests_per_minute == 7
        assert limits.max_concurrent_requests == 3
