from typing import Any

import pytest

from vibectl.subcommands import setup_proxy_cmd as spc


class _DummyConfigActive:
    """Dummy Config for set-active command tests."""

    def __init__(
        self, profiles: dict[str, dict[str, Any]], active: str | None = None
    ) -> None:
        self._profiles = profiles
        self._active = active

    def get_proxy_profile(self, name: str) -> dict[str, Any] | None:
        return self._profiles.get(name)

    def list_proxy_profiles(self) -> list[str]:
        return list(self._profiles.keys())

    def set_active_proxy_profile(self, name: str | None) -> None:
        self._active = name

    def get_active_proxy_profile(self) -> str | None:
        return self._active


@pytest.mark.parametrize("exists", [True, False])
def test_set_active_profile(monkeypatch: pytest.MonkeyPatch, exists: bool) -> None:
    """Validate both successful activation and not-found exit path."""

    profiles = {"profA": {"server_url": "vibectl-server://host:443"}} if exists else {}
    cfg = _DummyConfigActive(profiles)

    monkeypatch.setattr(spc, "Config", lambda *a, **k: cfg)
    monkeypatch.setattr(spc, "show_proxy_status", lambda: None)
    monkeypatch.setattr(spc, "handle_exception", lambda *a, **k: None)

    def mock_exit(code: int = 0) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(spc, "sys", type("MockSys", (), {"exit": mock_exit}))

    # Allow console output for debugging

    if exists:
        spc.set_active_profile.callback("profA")  # type: ignore[misc]
        assert cfg.get_active_proxy_profile() == "profA"
    else:
        with pytest.raises(SystemExit):
            spc.set_active_profile.callback("profA")  # type: ignore[misc]
        assert cfg.get_active_proxy_profile() is None
