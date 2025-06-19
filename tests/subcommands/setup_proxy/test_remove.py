from typing import Any

import pytest

from vibectl.subcommands import setup_proxy_cmd as spc


class _DummyConfigRemove:
    """Dummy Config object emulating proxy profile storage for remove tests."""

    def __init__(
        self, profiles: dict[str, dict[str, Any]], active: str | None = None
    ) -> None:
        self._profiles = profiles
        self._active = active
        self.removed = False

    # Methods exercised by remove_profile
    def get_proxy_profile(self, name: str) -> dict[str, Any] | None:
        return self._profiles.get(name)

    def remove_proxy_profile(self, name: str) -> bool:
        if name in self._profiles:
            del self._profiles[name]
            if self._active == name:
                self._active = None
            self.removed = True
            return True
        return False

    def get_active_proxy_profile(self) -> str | None:
        return self._active

    # Additional helpers used elsewhere in command but not in removal logic
    def set_active_proxy_profile(self, name: str | None) -> None:
        self._active = name

    def list_proxy_profiles(self) -> list[str]:
        return list(self._profiles.keys())


@pytest.mark.parametrize("exists", [True, False])
def test_remove_profile(monkeypatch: pytest.MonkeyPatch, exists: bool) -> None:
    """Cover both success (profile exists) and error path (missing profile)."""

    profiles = (
        {"to-remove": {"server_url": "vibectl-server://host:443"}} if exists else {}
    )
    dummy_cfg = _DummyConfigRemove(profiles, active="to-remove" if exists else None)

    # Patch Config to return our dummy instance
    monkeypatch.setattr(spc, "Config", lambda *a, **k: dummy_cfg)
    monkeypatch.setattr(spc, "handle_exception", lambda *a, **k: None)
    monkeypatch.setattr(
        spc, "click", type("MockClick", (), {"confirm": lambda *a, **k: True})
    )

    def mock_exit(code: int = 0) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(spc, "sys", type("MockSys", (), {"exit": mock_exit}))

    # Allow console output for debugging

    # Execute command via underlying callback (sync function)
    spc.remove_profile.callback("to-remove", mode="auto")  # type: ignore[misc]

    if exists:
        assert dummy_cfg.removed is True
        assert dummy_cfg.get_active_proxy_profile() is None
    else:
        # Should remain untouched
        assert dummy_cfg.removed is False
