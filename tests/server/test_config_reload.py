import tempfile
import threading
import time
from pathlib import Path

import yaml

from vibectl.server.config import ServerConfig, Success

# ---------------------------------------------------------------------------
# NOTE: These tests rely on the lightweight polling-based auto-reload mechanism
# added to ``ServerConfig``.  A small poll interval is used so the tests complete
# well under 1 second.
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, data: dict) -> None:
    """Helper that atomically writes YAML to *path* (best-effort)."""
    # Use json+dump to ensure consistent mtime update across platforms
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, indent=2, default_flow_style=False)
        f.flush()


def test_config_auto_reload_success() -> None:
    """Config watcher should pick up changes and invoke callbacks."""

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        config_path = Path(tmp.name)

    try:
        original_cfg = {"server": {"host": "orig", "port": 1234}}
        _write_yaml(config_path, original_cfg)

        sc = ServerConfig(config_path)
        assert isinstance(sc.load(), Success)
        assert sc.get("server.host") == "orig"

        event = threading.Event()

        def _on_change(new_cfg: dict) -> None:
            if new_cfg["server"]["host"] == "modified":
                event.set()

        sc.subscribe(_on_change)
        sc.start_auto_reload(poll_interval=0.05)

        # Modify the file
        modified_cfg = {"server": {"host": "modified", "port": 1234}}
        _write_yaml(config_path, modified_cfg)

        # Wait up to ~1s for the change to propagate
        assert event.wait(1.0), "Config change callback not triggered"

        # Cache should be updated too
        assert sc.get("server.host") == "modified"

    finally:
        sc.stop_auto_reload()
        config_path.unlink(missing_ok=True)


def test_config_auto_reload_invalid_change() -> None:
    """Invalid YAML should fail-open and keep previous config without callbacks."""

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        config_path = Path(tmp.name)

    try:
        base_cfg = {"server": {"host": "stable", "port": 1111}}
        _write_yaml(config_path, base_cfg)

        sc = ServerConfig(config_path)
        assert isinstance(sc.load(), Success)

        called = False

        def _fail_cb(_: dict) -> None:
            nonlocal called
            called = True

        sc.subscribe(_fail_cb)
        sc.start_auto_reload(poll_interval=0.05)

        # Write malformed YAML
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("invalid: [\n")
            f.flush()

        # Give watcher some time
        time.sleep(0.3)

        assert sc.get("server.host") == "stable"
        assert called is False, "Callback should not run on invalid reload"

    finally:
        sc.stop_auto_reload()
        config_path.unlink(missing_ok=True)
