"""Unit tests for the `setup-proxy list` command."""

from typing import Any

import pytest

from vibectl.subcommands import setup_proxy_cmd as spc


class _DummyConfigList:
    """Dummy Config implementation for the list command."""

    def __init__(
        self, profiles: dict[str, dict[str, Any]], active: str | None = None
    ) -> None:
        self._profiles = profiles
        self._active = active

    def list_proxy_profiles(self) -> list[str]:
        return list(self._profiles.keys())

    def get_proxy_profile(self, name: str) -> dict[str, Any] | None:
        return self._profiles.get(name)

    def get_active_proxy_profile(self) -> str | None:
        return self._active


@pytest.mark.parametrize(
    "profiles,active",
    [
        ({}, None),
        (
            {
                "corp": {"server_url": "vibectl-server://c:443"},
                "demo": {"server_url": "vibectl-server://d:443"},
            },
            "corp",
        ),
    ],
)
def test_list_proxy_profiles(
    monkeypatch: pytest.MonkeyPatch,
    profiles: dict[str, dict[str, Any]],
    active: str | None,
) -> None:
    """Ensure list command prints table and handles no-profile case gracefully."""

    cfg = _DummyConfigList(profiles, active)
    monkeypatch.setattr(spc, "Config", lambda *a, **k: cfg)
    monkeypatch.setattr(spc, "handle_exception", lambda *a, **k: None)

    def mock_exit(code: int = 0) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(spc, "sys", type("MockSys", (), {"exit": mock_exit}))

    # Track different types of console output
    safe_print_calls: dict[str, Any] = {}
    print_calls: dict[str, Any] = {}
    print_note_calls: dict[str, Any] = {}
    print_success_calls: dict[str, Any] = {}

    def _capture_safe_print(*args: Any, **kwargs: Any) -> None:
        safe_print_calls["called"] = True

    def _capture_print(*args: Any, **kwargs: Any) -> None:
        print_calls["called"] = True

    def _capture_print_note(*args: Any, **kwargs: Any) -> None:
        print_note_calls["called"] = True

    def _capture_print_success(*args: Any, **kwargs: Any) -> None:
        print_success_calls["called"] = True

    monkeypatch.setattr(spc.console_manager, "safe_print", _capture_safe_print)
    monkeypatch.setattr(spc.console_manager, "print", _capture_print)
    monkeypatch.setattr(spc.console_manager, "print_note", _capture_print_note)
    monkeypatch.setattr(spc.console_manager, "print_success", _capture_print_success)

    # Execute command callback
    spc.list_proxy_profiles.callback()  # type: ignore[misc]

    # Assertions
    if profiles:
        # When profiles exist: table is printed via safe_print, status messages
        # via print_success/print_note
        assert safe_print_calls.get("called") is True  # table printed
    else:
        # When no profiles: only print and print_note are called, not safe_print
        assert safe_print_calls.get("called") is None  # table not printed
        assert (
            print_calls.get("called") is True
        )  # "No proxy profiles configured" message
        assert print_note_calls.get("called") is True  # help message
