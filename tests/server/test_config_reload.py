import asyncio
import os
import tempfile
import threading
from pathlib import Path

import pytest
import yaml

from vibectl.server.config import ServerConfig, Success

# ---------------------------------------------------------------------------
# NOTE: These tests rely on the lightweight polling-based auto-reload mechanism
# added to ``ServerConfig``.  A small poll interval is used so the tests complete
# well under 1 second.
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, data: dict) -> None:
    """Helper that atomically writes YAML to *path*."""
    # Write to temporary file in the same directory, then atomic replace so that
    # watchers never observe a partially-written file.
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, suffix=path.suffix or "", delete=False, encoding="utf-8"
    ) as tmp:
        yaml.dump(data, tmp, indent=2, default_flow_style=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)

    os.replace(tmp_path, path)


@pytest.mark.asyncio
async def test_config_auto_reload_success() -> None:
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

        # Allow the watcher thread to start before we modify the file. A short
        # async sleep keeps the test deterministic under heavy CI load without
        # noticeably impacting total runtime (~0.1 s).
        await asyncio.sleep(0.1)

        # Modify the file
        modified_cfg = {"server": {"host": "modified", "port": 1234}}
        _write_yaml(config_path, modified_cfg)

        # Wait up to ~1s for the change to propagate
        assert await asyncio.to_thread(event.wait, 1.0), (
            "Config change callback not triggered"
        )

        # Cache should be updated too
        assert sc.get("server.host") == "modified"

    finally:
        sc.stop_auto_reload()
        config_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_config_auto_reload_invalid_change() -> None:
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

        # Ensure the watcher thread is running before we introduce malformed
        # YAML. A brief pause avoids race conditions seen when the watcher had
        # not yet performed its first poll.
        await asyncio.sleep(0.1)

        # Write malformed YAML atomically to avoid triggering partial-read races
        tmp_path = config_path.with_suffix(".tmp")
        tmp_path.write_text("invalid: [\n", encoding="utf-8")
        os.replace(tmp_path, config_path)

        # Give watcher some time
        await asyncio.sleep(0.3)

        assert sc.get("server.host") == "stable"
        assert called is False, "Callback should not run on invalid reload"

    finally:
        sc.stop_auto_reload()
        config_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_config_auto_reload_multiple_changes() -> None:
    """Watcher should emit callbacks for each successive config update."""

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        config_path = Path(tmp.name)

    try:
        base_cfg = {"server": {"host": "v1", "port": 9999}}
        _write_yaml(config_path, base_cfg)

        sc = ServerConfig(config_path)
        assert isinstance(sc.load(), Success)

        # Track all hosts seen by the callback so we can verify both updates
        seen_hosts: list[str] = []
        event = threading.Event()

        def _cb(new_cfg: dict) -> None:
            host = new_cfg["server"]["host"]
            seen_hosts.append(host)
            # Signal when we've observed the *second* update (v3)
            if host == "v3":
                event.set()

        sc.subscribe(_cb)
        sc.start_auto_reload(poll_interval=0.05)

        # Give the watcher thread a moment to spin up before the first update -
        # eliminates occasional flakes under high load.
        await asyncio.sleep(0.1)

        # First update
        _write_yaml(config_path, {"server": {"host": "v2", "port": 9999}})
        await asyncio.sleep(0.2)  # Allow watcher to detect first change

        # Second update
        _write_yaml(config_path, {"server": {"host": "v3", "port": 9999}})

        # Wait up to 1s for second callback
        assert await asyncio.to_thread(event.wait, 1.0), (
            "Second config change not detected"
        )
        # We expect to see both v2 and v3 in callbacks (order preserved)
        assert seen_hosts == ["v2", "v3"]

    finally:
        sc.stop_auto_reload()
        config_path.unlink(missing_ok=True)
