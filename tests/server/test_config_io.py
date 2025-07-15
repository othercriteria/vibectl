import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from vibectl.server.config import Error, Limits, ServerConfig, Success


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


@pytest.mark.parametrize("suffix", [".yaml", ".json"])
def test_save_and_load_roundtrip(tmp_path: Path, suffix: str) -> None:
    """ServerConfig.save() should persist the config atomically and load() should
    return exactly what was saved (merged with defaults). The test is run for
    both YAML and JSON formats via parametrize."""

    cfg_path = tmp_path / f"server_cfg{suffix}"

    cfg_to_save: dict[str, Any] = {
        "server": {
            "host": "test.example",
            "port": 4242,
            "limits": {"global": {"max_requests_per_minute": 99}},
        },
        "jwt": {"enabled": True},
    }

    sc = ServerConfig(cfg_path)
    save_result = sc.save(cfg_to_save)
    assert isinstance(save_result, Success), save_result

    # File should exist and contain the expected data
    assert cfg_path.exists()
    raw_on_disk = _load_json(cfg_path) if suffix == ".json" else _load_yaml(cfg_path)

    # The on-disk file should exactly match what we attempted to save (no defaults)
    assert raw_on_disk == cfg_to_save

    # load() merges defaults - verify that user values survive the merge
    load_result = sc.load(force_reload=True)
    assert isinstance(load_result, Success)
    loaded = load_result.data or {}

    assert loaded["server"]["host"] == "test.example"
    assert loaded["server"]["port"] == 4242
    # Default field should have been injected
    assert "default_model" in loaded["server"]


def test_set_and_get_dot_notation(tmp_path: Path) -> None:
    """The convenience set()/get() helpers should work with dotted paths."""

    cfg_path = tmp_path / "config.yaml"
    sc = ServerConfig(cfg_path)
    # Create default file first
    sc.save({})

    assert sc.set("server.host", "myhost"), "set() should succeed"
    assert sc.get("server.host") == "myhost"
    assert sc.get("nonexistent.key", default="fallback") == "fallback"


def test_get_limits_merges_per_token(tmp_path: Path) -> None:
    """get_limits() should merge per-token overrides over global defaults."""

    cfg_path = tmp_path / "cfg.yaml"
    cfg: dict[str, Any] = {
        "server": {
            "limits": {
                "global": {"max_requests_per_minute": 10},
                "per_token": {"user123": {"max_requests_per_minute": 1}},
            }
        }
    }
    sc = ServerConfig(cfg_path)
    sc.save(cfg)

    global_limits = sc.get_limits()
    token_limits = sc.get_limits("user123")

    assert isinstance(global_limits, Limits)
    assert isinstance(token_limits, Limits)
    assert global_limits.max_requests_per_minute == 10
    # Per-token override should win
    assert token_limits.max_requests_per_minute == 1
    # Unspecified dimensions fall back to None (unlimited)
    assert token_limits.max_concurrent_requests is None


def test_validate_detects_invalid_limits(tmp_path: Path) -> None:
    """validate() should flag nonsensical numeric limit values."""

    cfg_path = tmp_path / "bad.yaml"
    bad_cfg: dict[str, Any] = {
        "server": {"limits": {"global": {"max_requests_per_minute": -5}}}
    }
    sc = ServerConfig(cfg_path)
    sc.save(bad_cfg)

    validate_result = sc.validate()
    assert isinstance(validate_result, Error)
    assert "must be >= 1" in validate_result.error
