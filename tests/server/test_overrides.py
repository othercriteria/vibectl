from collections.abc import Iterator

import pytest

from vibectl.server import overrides as server_overrides
from vibectl.server.config import ServerConfig


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    """Ensure overrides are cleared before each test."""
    server_overrides.clear_overrides()
    yield
    server_overrides.clear_overrides()


def test_get_uses_context_override() -> None:
    server_overrides.set_override("server.host", "example.com")
    cfg = ServerConfig()
    assert cfg.get("server.host") == "example.com"


def test_limits_respect_context_override() -> None:
    rpm_limit = 42
    server_overrides.set_override(
        "server.limits.global.max_requests_per_minute", rpm_limit
    )
    cfg = ServerConfig()
    limits = cfg.get_limits()
    assert limits.max_requests_per_minute == rpm_limit
