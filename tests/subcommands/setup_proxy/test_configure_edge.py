"""Edge-case tests for setup-proxy configure command to hit lesser-used branches."""

from pathlib import Path

import pytest

from vibectl.subcommands import setup_proxy_cmd as spc


class _CfgMinimal:
    """Minimal config object for flag-validation branches."""

    def __init__(self) -> None:
        self.saved = False

    # methods used before we expect SystemExit so can be no-ops
    def save(self) -> None:
        self.saved = True


@pytest.mark.asyncio
async def test_activate_with_no_test_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    """--activate combined with --no-test must abort (security validation)."""

    monkeypatch.setattr(spc, "Config", _CfgMinimal)
    monkeypatch.setattr(spc, "handle_exception", lambda *a, **k: None)

    def mock_exit(code: int = 0) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(spc, "sys", type("MockSys", (), {"exit": mock_exit}))
    # Allow console output for debugging

    with pytest.raises(SystemExit):
        await spc.setup_proxy_configure.callback(  # type: ignore[misc]
            profile_name="p",
            proxy_url="vibectl-server://host:443",
            no_test=True,
            ca_bundle=None,
            jwt_path=None,
            enable_sanitization=False,
            enable_audit_logging=False,
            activate=True,  # invalid with no_test
            no_activate=False,
        )


@pytest.mark.asyncio
async def test_missing_ca_bundle_file_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Providing a non-existent CA bundle should exit early (line ~589)."""

    ca_path = tmp_path / "missing.pem"  # DO NOT create

    monkeypatch.setattr(spc, "Config", _CfgMinimal)
    monkeypatch.setattr(spc, "handle_exception", lambda *a, **k: None)

    def mock_exit(code: int = 0) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(spc, "sys", type("MockSys", (), {"exit": mock_exit}))
    # Allow console output for debugging

    with pytest.raises(SystemExit):
        await spc.setup_proxy_configure.callback(  # type: ignore[misc]
            profile_name="ca",
            proxy_url="vibectl-server://host:443",
            no_test=True,
            ca_bundle=str(ca_path),  # missing file triggers validation branch
            jwt_path=None,
            enable_sanitization=False,
            enable_audit_logging=False,
            activate=False,
            no_activate=True,
        )
