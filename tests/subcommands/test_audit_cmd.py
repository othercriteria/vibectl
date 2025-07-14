"""Tests for vibectl audit subcommands."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import asyncclick
import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli as vibectl_cli
from vibectl.config import Config
from vibectl.subcommands.audit_cmd import (
    _parse_since,
)


@pytest.fixture()
def configured_audit_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, Path]:
    """Create a proxy profile with audit logging enabled and sample log file.

    This fixture ensures all Config instances during the test use the same
    configuration directory by monkeypatching the Config.__init__ method.
    """
    profile_name = "test-profile"
    log_path = tmp_path / f"audit-{profile_name}.log"

    # Ensure directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Write sample audit entries (3 lines JSONL) to the log
    sample_entries: list[dict[str, Any]] = [
        {
            "timestamp": "2025-01-01T00:00:00Z",
            "event_type": "llm_request",
            "command_generated": "kubectl get pods",
            "secrets_detected": 0,
            "secrets_types": [],
        },
        {
            "timestamp": "2025-01-01T00:01:00Z",
            "event_type": "sanitization",
            "secrets_detected": 1,
            "secrets_types": ["k8s-token"],
        },
        {
            "timestamp": "2025-01-01T00:02:00Z",
            "event_type": "proxy_connection",
            "server_url": "test://localhost",
            "success": True,
            "secrets_detected": 0,
            "secrets_types": [],
        },
    ]
    with log_path.open("w", encoding="utf-8") as f:
        for entry in sample_entries:
            json.dump(entry, f, separators=(",", ":"))
            f.write("\n")

    # Create a config directory in the temporary path
    config_dir = tmp_path / ".config" / "vibectl" / "client"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"

    # Create initial config with proxy profile
    config_data = {
        "proxy": {
            "active": profile_name,
            "profiles": {
                profile_name: {
                    "server_url": "vibectl-server://localhost:50051",
                    "security": {
                        "audit_logging": True,
                        "audit_log_path": str(log_path),
                    },
                },
            },
        },
    }

    # Save config to the temp directory
    import yaml

    with config_file.open("w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    # Monkeypatch Config to always use the temp directory
    original_init = Config.__init__

    def mock_init(self: Any, base_dir: Path | None = None) -> None:
        original_init(self, base_dir=tmp_path)

    monkeypatch.setattr(Config, "__init__", mock_init)

    return profile_name, log_path


@pytest.mark.asyncio
async def test_audit_export_jsonl(configured_audit_profile: tuple[str, Path]) -> None:
    """audit export should support jsonl format with newline-delimited JSON."""
    profile_name, _ = configured_audit_profile

    runner = CliRunner()
    with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            [
                "audit",
                "export",
                "--proxy",
                profile_name,
                "--format",
                "jsonl",
            ],
        )

    assert result_obj.exit_code == 0, result_obj.output

    json_lines = [
        line for line in result_obj.output.split("\n") if line.strip() and "{" in line
    ]
    assert len(json_lines) >= 3, (
        f"Expected at least three JSONL lines, got {len(json_lines)}. "
        f"Output: {result_obj.output!r}"
    )
    for line in json_lines[:3]:
        # Ensure each line is valid compact JSON
        obj = json.loads(line)
        assert "timestamp" in obj


@pytest.mark.asyncio
async def test_audit_info_paths_only(
    configured_audit_profile: tuple[str, Path],
) -> None:
    """audit info --paths-only should output the log path."""
    profile_name, log_path = configured_audit_profile
    runner = CliRunner()
    with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "info", "--proxy", profile_name, "--paths-only"],
        )

    assert result_obj.exit_code == 0, f"Command failed: {result_obj.output}"
    # The log path should appear in the output (potentially split across lines
    # due to console wrapping)
    output_normalized = result_obj.output.replace("\n", "")
    assert str(log_path) in output_normalized, (
        f"Expected {log_path} in output: {result_obj.output!r}"
    )


# Additional test for `audit show`


@pytest.mark.asyncio
async def test_audit_show_basic(configured_audit_profile: tuple[str, Path]) -> None:
    """Ensure audit show returns table without error."""
    profile_name, _ = configured_audit_profile
    runner = CliRunner()
    with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "show", "--proxy", profile_name, "--limit", "2"],
        )

    assert result_obj.exit_code == 0, f"Command failed: {result_obj.output}"
    # Should contain table header
    assert "Audit log" in result_obj.output, (
        f"Expected 'Audit log' in output: {result_obj.output!r}"
    )


@pytest.mark.asyncio
async def test_audit_export_csv(configured_audit_profile: tuple[str, Path]) -> None:
    """audit export should support CSV format with header line."""
    profile_name, _ = configured_audit_profile

    runner = CliRunner()
    with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            [
                "audit",
                "export",
                "--proxy",
                profile_name,
                "--format",
                "csv",
            ],
        )

    assert result_obj.exit_code == 0, f"Command failed: {result_obj.output}"
    # The first line should contain CSV headers including "timestamp"
    lines = [line for line in result_obj.output.split("\n") if line.strip()]
    assert len(lines) > 0, f"Expected CSV output, got: {result_obj.output!r}"
    header_line = lines[0]
    assert "timestamp" in header_line and "event_type" in header_line, (
        f"Expected CSV headers in: {header_line!r}"
    )


@pytest.mark.asyncio
async def test_audit_info_json(configured_audit_profile: tuple[str, Path]) -> None:
    """audit info should output valid JSON when --format json is used."""
    profile_name, log_path = configured_audit_profile
    runner = CliRunner()
    with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "info", "--proxy", profile_name, "--format", "json"],
        )

    assert result_obj.exit_code == 0, f"Command failed: {result_obj.output}"
    # Parse JSON to verify validity and check expected fields
    json_output = json.loads(result_obj.output)
    assert isinstance(json_output, list)
    assert len(json_output) > 0
    first_entry = json_output[0]
    assert "profile" in first_entry
    assert "enabled" in first_entry
    assert "path" in first_entry


# ---------------------------------------------------------------------------
# Unit tests for internal helper _parse_since in audit_cmd
# ---------------------------------------------------------------------------


def test_parse_since_relative_hours() -> None:
    """_parse_since should parse relative hours correctly."""
    two_h_ago = _parse_since("2h")
    assert two_h_ago is not None
    delta = (datetime.utcnow() - two_h_ago).total_seconds()
    # Allow small margin (1-3 seconds)
    assert 7190 < delta < 7210


def test_parse_since_unix_epoch() -> None:
    """_parse_since should parse epoch seconds."""
    dt = _parse_since("1718900000")
    assert dt is not None
    assert dt.year >= 2024  # Rough sanity check


def test_parse_since_invalid() -> None:
    """_parse_since should raise asyncclick.BadParameter for invalid input."""
    with pytest.raises(asyncclick.exceptions.BadParameter):
        _parse_since("not-a-time")


# ---------------------------------------------------------------------------
# Additional tests for better coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_show_no_profile() -> None:
    """audit show should show error when no profile is active."""
    runner = CliRunner()
    with (
        patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}),
        patch("vibectl.subcommands.audit_cmd.Config") as mock_config_class,
    ):
        mock_config = Mock(spec=Config)
        mock_config.get_active_proxy_profile.return_value = None
        mock_config_class.return_value = mock_config

        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "show"],
        )

    assert result_obj.exit_code == 0
    assert "No proxy profile specified and no active profile set" in result_obj.output


@pytest.mark.asyncio
async def test_audit_show_disabled_logging(
    configured_audit_profile: tuple[str, Path],
) -> None:
    """audit show should show warning when audit logging is disabled."""
    profile_name, _ = configured_audit_profile

    runner = CliRunner()
    with (
        patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}),
        patch(
            "vibectl.subcommands.audit_cmd.Config", new_callable=Mock
        ) as mock_config_class,
    ):
        mock_config = Mock()
        mock_config.get_active_proxy_profile.return_value = profile_name
        mock_config.get_proxy_profile.return_value = {
            "security": {"audit_logging": False}
        }
        mock_config_class.return_value = mock_config

        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "show", "--proxy", profile_name],
        )

    assert result_obj.exit_code == 0
    assert "Audit logging disabled for this profile" in result_obj.output


@pytest.mark.asyncio
async def test_audit_show_no_entries(
    configured_audit_profile: tuple[str, Path],
) -> None:
    """audit show should handle empty audit logs gracefully."""
    profile_name, log_path = configured_audit_profile

    # Empty the log file
    log_path.write_text("")

    runner = CliRunner()
    with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "show", "--proxy", profile_name],
        )

    assert result_obj.exit_code == 0
    assert "No audit entries found" in result_obj.output


def test_parse_since_none() -> None:
    """_parse_since should return None for None input."""
    assert _parse_since(None) is None


def test_parse_since_relative_minutes() -> None:
    """_parse_since should parse relative minutes correctly."""
    thirty_m_ago = _parse_since("30m")
    assert thirty_m_ago is not None
    delta = (datetime.utcnow() - thirty_m_ago).total_seconds()
    # Allow small margin (29-31 minutes)
    assert 1740 < delta < 1860


def test_parse_since_relative_days() -> None:
    """_parse_since should parse relative days correctly."""
    one_d_ago = _parse_since("1d")
    assert one_d_ago is not None
    delta = (datetime.utcnow() - one_d_ago).total_seconds()
    # Allow small margin (23-25 hours)
    assert 82800 < delta < 90000


def test_parse_since_iso_with_z() -> None:
    """_parse_since should parse ISO timestamp with Z suffix."""
    dt = _parse_since("2025-01-15T10:30:45Z")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 1
    assert dt.day == 15


def test_parse_since_iso_without_z() -> None:
    """_parse_since should parse ISO timestamp without Z suffix."""
    dt = _parse_since("2025-01-15T10:30:45")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 1
    assert dt.day == 15


# Additional tests for coverage gaps


@pytest.mark.asyncio
async def test_audit_show_no_active_profile() -> None:
    """audit show should handle case where no active profile is set."""
    runner = CliRunner()

    # Mock Config to return None for active profile
    with patch(
        "vibectl.subcommands.audit_cmd.Config", new_callable=Mock
    ) as mock_config_class:
        mock_config = Mock()
        mock_config.get_active_proxy_profile.return_value = None
        mock_config_class.return_value = mock_config

        with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
            result_obj = await runner.invoke(  # type: ignore[func-returns-value]
                vibectl_cli,
                ["audit", "show"],
            )

    assert result_obj.exit_code == 0
    assert "No proxy profile specified and no active profile set" in result_obj.output


@pytest.mark.asyncio
async def test_audit_show_profile_not_found() -> None:
    """audit show should handle case where specified profile doesn't exist."""
    runner = CliRunner()

    with patch(
        "vibectl.subcommands.audit_cmd.Config", new_callable=Mock
    ) as mock_config_class:
        mock_config = Mock()
        mock_config.get_proxy_profile.return_value = None
        mock_config_class.return_value = mock_config

        with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
            result_obj = await runner.invoke(  # type: ignore[func-returns-value]
                vibectl_cli,
                ["audit", "show", "--proxy", "nonexistent"],
            )

    assert result_obj.exit_code == 0
    assert "Proxy profile 'nonexistent' not found" in result_obj.output


@pytest.mark.asyncio
async def test_audit_export_no_active_profile() -> None:
    """audit export should handle case where no active profile is set."""
    runner = CliRunner()

    with patch(
        "vibectl.subcommands.audit_cmd.Config", new_callable=Mock
    ) as mock_config_class:
        mock_config = Mock()
        mock_config.get_active_proxy_profile.return_value = None
        mock_config_class.return_value = mock_config

        with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
            result_obj = await runner.invoke(  # type: ignore[func-returns-value]
                vibectl_cli,
                ["audit", "export"],
            )

    assert result_obj.exit_code == 0
    assert "No proxy profile specified and no active profile set" in result_obj.output


@pytest.mark.asyncio
async def test_audit_export_profile_not_found() -> None:
    """audit export should handle case where specified profile doesn't exist."""
    runner = CliRunner()

    with patch(
        "vibectl.subcommands.audit_cmd.Config", new_callable=Mock
    ) as mock_config_class:
        mock_config = Mock()
        mock_config.get_proxy_profile.return_value = None
        mock_config_class.return_value = mock_config

        with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
            result_obj = await runner.invoke(  # type: ignore[func-returns-value]
                vibectl_cli,
                ["audit", "export", "--proxy", "nonexistent"],
            )

    assert result_obj.exit_code == 0
    assert "Proxy profile 'nonexistent' not found" in result_obj.output


@pytest.mark.asyncio
async def test_audit_export_to_file(
    configured_audit_profile: tuple[str, Path], tmp_path: Path
) -> None:
    """audit export should write to file when --output is specified."""
    profile_name, _ = configured_audit_profile
    output_file = tmp_path / "audit_export.json"

    runner = CliRunner()
    with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            [
                "audit",
                "export",
                "--proxy",
                profile_name,
                "--output",
                str(output_file),
            ],
        )

    assert result_obj.exit_code == 0
    assert "Exported" in result_obj.output
    assert output_file.exists()

    # Verify file contains valid JSON
    content = output_file.read_text()
    json_data = json.loads(content)
    assert isinstance(json_data, list)


@pytest.mark.asyncio
async def test_audit_export_empty_csv(
    configured_audit_profile: tuple[str, Path],
) -> None:
    """audit export should handle empty CSV case."""
    profile_name, _ = configured_audit_profile

    runner = CliRunner()

    # Mock AuditLogger to return no entries
    with patch("vibectl.subcommands.audit_cmd.AuditLogger") as mock_audit_logger_class:
        mock_audit_logger = Mock()
        mock_audit_logger.get_audit_entries.return_value = []
        mock_audit_logger_class.return_value = mock_audit_logger

        with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
            result_obj = await runner.invoke(  # type: ignore[func-returns-value]
                vibectl_cli,
                [
                    "audit",
                    "export",
                    "--proxy",
                    profile_name,
                    "--format",
                    "csv",
                ],
            )

    assert result_obj.exit_code == 0
    # Empty CSV should produce empty output (no headers)
    assert result_obj.output.strip() == ""


@pytest.mark.asyncio
async def test_audit_info_no_profiles() -> None:
    """audit info should handle case where no profiles are configured."""
    runner = CliRunner()

    with patch(
        "vibectl.subcommands.audit_cmd.Config", new_callable=Mock
    ) as mock_config_class:
        mock_config = Mock()
        mock_config.list_proxy_profiles.return_value = []
        mock_config_class.return_value = mock_config

        with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
            result_obj = await runner.invoke(  # type: ignore[func-returns-value]
                vibectl_cli,
                ["audit", "info"],
            )

    assert result_obj.exit_code == 0
    assert "No proxy profiles configured" in result_obj.output


def test_parse_since_invalid_unix_timestamp() -> None:
    """_parse_since should handle invalid Unix timestamps."""
    # Test with a Unix timestamp that causes an exception
    from asyncclick.exceptions import BadParameter

    with pytest.raises(BadParameter):
        _parse_since(
            "99999999999999999999"
        )  # Extremely large number that will cause overflow


def test_parse_since_invalid_iso() -> None:
    """_parse_since should handle invalid ISO format strings."""
    from asyncclick.exceptions import BadParameter

    with pytest.raises(BadParameter, match="Invalid --since value"):
        _parse_since("not-a-date")


def test_parse_since_invalid_iso_malformed() -> None:
    """_parse_since should handle malformed ISO dates."""
    from asyncclick.exceptions import BadParameter

    with pytest.raises(BadParameter, match="Invalid --since value"):
        _parse_since("2025-13-99T99:99:99")  # Invalid month/day/time


def test_summarize_entry_llm_request() -> None:
    """_summarize_entry should handle llm_request events."""
    from vibectl.subcommands.audit_cmd import _summarize_entry

    entry = {
        "event_type": "llm_request",
        "command_generated": "kubectl get pods",
        "model_used": "claude-3",
        "secrets_detected": 2,
    }
    result = _summarize_entry(entry)
    assert "cmd=kubectl get pods" in result
    assert "model=claude-3" in result
    assert "secrets=2" in result


def test_summarize_entry_sanitization() -> None:
    """_summarize_entry should handle sanitization events."""
    from vibectl.subcommands.audit_cmd import _summarize_entry

    entry = {
        "event_type": "sanitization",
        "secrets_detected": 1,
        "secrets_types": ["k8s-token", "base64-data"],
    }
    result = _summarize_entry(entry)
    assert "secrets=1" in result
    assert "types=k8s-token,base64-data" in result


def test_summarize_entry_proxy_connection_success() -> None:
    """_summarize_entry should handle successful proxy connection events."""
    from vibectl.subcommands.audit_cmd import _summarize_entry

    entry = {
        "event_type": "proxy_connection",
        "success": True,
        "server_url": "https://example.com",
    }
    result = _summarize_entry(entry)
    assert "✓" in result
    assert "https://example.com" in result


def test_summarize_entry_proxy_connection_failure() -> None:
    """_summarize_entry should handle failed proxy connection events."""
    from vibectl.subcommands.audit_cmd import _summarize_entry

    entry = {
        "event_type": "proxy_connection",
        "success": False,
        "server_url": "https://example.com",
    }
    result = _summarize_entry(entry)
    assert "✗" in result
    assert "https://example.com" in result


def test_summarize_entry_unknown_type() -> None:
    """_summarize_entry should handle unknown event types."""
    from vibectl.subcommands.audit_cmd import _summarize_entry

    entry = {
        "event_type": "unknown_type",
        "some_field": "some_value",
    }
    result = _summarize_entry(entry)
    assert result == "-"


def test_get_security_config_none() -> None:
    """_get_security_config should handle None profile config."""
    from vibectl.subcommands.audit_cmd import _get_security_config

    result = _get_security_config(None)
    assert result.audit_logging is True  # Default config


def test_get_security_config_no_security_section() -> None:
    """_get_security_config should handle profile config without security section."""
    from vibectl.subcommands.audit_cmd import _get_security_config

    profile_cfg = {"server_url": "test://localhost"}
    result = _get_security_config(profile_cfg)
    assert result.audit_logging is True  # Default config


@pytest.mark.asyncio
async def test_audit_commands_exception_handling() -> None:
    """Test that audit commands properly handle exceptions through handle_exception."""
    runner = CliRunner()

    # Test exception in audit show
    with (
        patch(
            "vibectl.subcommands.audit_cmd.Config",
            side_effect=Exception("Test error"),
            new_callable=Mock,
        ),
        patch("vibectl.subcommands.audit_cmd.handle_exception") as mock_handle,
        patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}),
    ):
        await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "show"],
        )
        mock_handle.assert_called_once()

    # Test exception in audit export
    with (
        patch(
            "vibectl.subcommands.audit_cmd.Config",
            side_effect=Exception("Test error"),
            new_callable=Mock,
        ),
        patch("vibectl.subcommands.audit_cmd.handle_exception") as mock_handle,
        patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}),
    ):
        await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "export"],
        )
        mock_handle.assert_called_once()

    # Test exception in audit info
    with (
        patch(
            "vibectl.subcommands.audit_cmd.Config",
            side_effect=Exception("Test error"),
            new_callable=Mock,
        ),
        patch("vibectl.subcommands.audit_cmd.handle_exception") as mock_handle,
        patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}),
    ):
        await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "info"],
        )
        mock_handle.assert_called_once()


@pytest.mark.asyncio
async def test_audit_info_profile_not_found_in_list() -> None:
    """Test audit info when a profile from list doesn't exist when retrieved."""
    runner = CliRunner()

    with patch(
        "vibectl.subcommands.audit_cmd.Config", new_callable=Mock
    ) as mock_config_class:
        mock_config = Mock()
        # Return a profile name but then return None when getting the profile
        mock_config.list_proxy_profiles.return_value = ["missing-profile"]
        mock_config.get_proxy_profile.return_value = None  # Profile disappeared
        mock_config_class.return_value = mock_config

        with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
            result_obj = await runner.invoke(  # type: ignore[func-returns-value]
                vibectl_cli,
                ["audit", "info"],
            )

    assert result_obj.exit_code == 0
    # Should still succeed but profile won't appear in results


@pytest.mark.asyncio
async def test_audit_info_nonexistent_log_file(
    configured_audit_profile: tuple[str, Path],
) -> None:
    """Test audit info when log file doesn't exist."""
    profile_name, log_path = configured_audit_profile

    # Remove the log file to test the nonexistent file branch
    log_path.unlink()

    runner = CliRunner()
    with patch.dict(os.environ, {"VIBECTL_ANTHROPIC_API_KEY": "dummy"}):
        result_obj = await runner.invoke(  # type: ignore[func-returns-value]
            vibectl_cli,
            ["audit", "info", "--proxy", profile_name],
        )

    assert result_obj.exit_code == 0
    assert "No" in result_obj.output  # File exists = No
