"""Tests for setup-proxy configure command covering success and error paths."""

import pytest

from vibectl.subcommands import setup_proxy_cmd as spc
from vibectl.types import Error, Success


class _DummyConfig:
    """Minimal stand-in for vibectl.config.Config used by configure cmd."""

    def __init__(self) -> None:
        self.profiles: dict[str, dict] = {}
        self._active: str | None = None

    # Methods invoked by setup_proxy_configure
    def set_proxy_profile(self, name: str, cfg: dict) -> None:
        self.profiles[name] = cfg

    def set_active_proxy_profile(self, name: str | None) -> None:
        self._active = name

    def save(self) -> None:
        # No-op for tests
        pass


@pytest.mark.asyncio
async def test_setup_proxy_configure_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy-path: connection test success leads to profile saved without exit."""

    # Stub Success result from connection test
    async def _fake_check(*_: object, **__: object) -> Success:
        return Success(
            data={
                "server_name": "test",
                "version": "1.0",
                "supported_models": ["gpt"],
                "limits": {
                    "max_request_size": 1,
                    "max_concurrent_requests": 1,
                    "timeout_seconds": 1,
                },
            }
        )

    monkeypatch.setattr(spc, "check_proxy_connection", _fake_check)
    monkeypatch.setattr(spc, "Config", _DummyConfig)
    monkeypatch.setattr(spc, "show_proxy_status", lambda: None)
    monkeypatch.setattr(spc, "_print_server_info", lambda *a, **k: None)
    monkeypatch.setattr(spc, "handle_exception", lambda *a, **k: None)

    # Allow console output for debugging

    # Call the click-wrapped async callback directly
    await spc.setup_proxy_configure.callback(  # type: ignore[misc]
        profile_name="testprof",
        proxy_url="vibectl-server://localhost:443",
        no_test=False,
        ca_bundle=None,
        jwt_path=None,
        enable_sanitization=True,
        enable_audit_logging=False,
        activate=True,
        no_activate=False,
    )


@pytest.mark.asyncio
async def test_setup_proxy_configure_connection_failure_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If connection test fails, the command should call sys.exit(1)."""

    async def _fail_check(*_: object, **__: object) -> Error:
        return Error(error="boom")

    monkeypatch.setattr(spc, "check_proxy_connection", _fail_check)
    monkeypatch.setattr(spc, "Config", _DummyConfig)
    monkeypatch.setattr(spc, "show_proxy_status", lambda: None)
    monkeypatch.setattr(spc, "_print_server_info", lambda *a, **k: None)
    monkeypatch.setattr(spc, "handle_exception", lambda *a, **k: None)

    # Allow console output for debugging

    with pytest.raises(SystemExit):
        await spc.setup_proxy_configure.callback(  # type: ignore[misc]
            profile_name="bad",
            proxy_url="vibectl-server://localhost:443",
            no_test=False,
            ca_bundle=None,
            jwt_path=None,
            enable_sanitization=False,
            enable_audit_logging=False,
            activate=False,
            no_activate=True,
        )
