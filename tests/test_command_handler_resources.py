"""Tests for command_handler.py's resource handling and cleanup.

This module tests resource handling, focusing on file descriptors and
temporary file cleanup to prevent leaks.
"""

import os
import tempfile
from collections.abc import Generator
from contextlib import suppress
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from vibectl.command_handler import _execute_yaml_command


@pytest.fixture
def temp_yaml_file() -> Generator[Path, None, None]:
    """Create a temporary YAML file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write("apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod")
        tmp_path = Path(tmp.name)

    yield tmp_path

    # Clean up after test
    if tmp_path.exists():
        os.unlink(tmp_path)


def test_yaml_command_cleanup_on_success() -> None:
    """Test that temporary files are cleaned up after successful execution."""
    with (
        patch("subprocess.run") as mock_run,
        patch("vibectl.command_handler.console_manager"),
        patch("os.unlink") as mock_unlink,
    ):
        # Set up subprocess mock
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = "pod/test-pod created"
        mock_run.return_value = mock_process

        # Create a counter to track NamedTemporaryFile calls
        temp_file_paths = []

        # Patch NamedTemporaryFile to track created files
        original_named_temp_file = tempfile.NamedTemporaryFile

        def mock_named_temp_file(*args: Any, **kwargs: Any) -> Any:
            temp_file = original_named_temp_file(*args, **kwargs)
            temp_file_paths.append(temp_file.name)
            return temp_file

        with patch("tempfile.NamedTemporaryFile", side_effect=mock_named_temp_file):
            # Execute YAML command
            _execute_yaml_command(["apply"], "apiVersion: v1\nkind: Pod")

            # Verify unlink was called for each temp file
            assert len(temp_file_paths) > 0
            for path in temp_file_paths:
                mock_unlink.assert_any_call(path)


def test_yaml_command_cleanup_on_error() -> None:
    """Test that temporary files are cleaned up even when command fails."""
    with (
        patch("subprocess.run") as mock_run,
        patch("vibectl.command_handler.console_manager"),
        patch("os.unlink") as mock_unlink,
    ):
        # Set up subprocess mock to simulate failure
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.stderr = "Error: invalid Pod specification"
        mock_run.return_value = mock_process

        # Create a counter to track NamedTemporaryFile calls
        temp_file_paths = []

        # Patch NamedTemporaryFile to track created files
        original_named_temp_file = tempfile.NamedTemporaryFile

        def mock_named_temp_file(*args: Any, **kwargs: Any) -> Any:
            temp_file = original_named_temp_file(*args, **kwargs)
            temp_file_paths.append(temp_file.name)
            return temp_file

        with patch("tempfile.NamedTemporaryFile", side_effect=mock_named_temp_file):
            # Execute YAML command expecting it to fail
            with suppress(Exception):
                _execute_yaml_command(["apply"], "invalid YAML")

            # Verify unlink was called for cleanup despite error
            assert len(temp_file_paths) > 0
            for path in temp_file_paths:
                mock_unlink.assert_any_call(path)


def test_yaml_command_cleanup_on_exception() -> None:
    """Test that temporary files are cleaned up when unexpected exceptions occur."""
    with (
        patch("subprocess.run") as mock_run,
        patch("vibectl.command_handler.console_manager"),
        patch("os.unlink") as mock_unlink,
    ):
        # Set up subprocess mock to raise exception
        mock_run.side_effect = RuntimeError("Unexpected error")

        # Create a counter to track NamedTemporaryFile calls
        temp_file_paths = []

        # Patch NamedTemporaryFile to track created files
        original_named_temp_file = tempfile.NamedTemporaryFile

        def mock_named_temp_file(*args: Any, **kwargs: Any) -> Any:
            temp_file = original_named_temp_file(*args, **kwargs)
            temp_file_paths.append(temp_file.name)
            return temp_file

        with patch("tempfile.NamedTemporaryFile", side_effect=mock_named_temp_file):
            # Execute YAML command expecting it to raise exception
            with suppress(RuntimeError):
                _execute_yaml_command(["apply"], "apiVersion: v1\nkind: Pod")

            # Verify unlink was called for cleanup despite exception
            assert len(temp_file_paths) > 0
            for path in temp_file_paths:
                mock_unlink.assert_any_call(path)


def test_stdin_pipe_resource_handling() -> None:
    """Test that stdin pipes are properly closed in YAML command execution."""
    with (
        patch("subprocess.Popen") as mock_popen,
        patch("vibectl.command_handler.console_manager"),
    ):
        # Create mock process
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Output", b"")
        mock_popen.return_value = mock_process

        # Execute command with stdin pipe
        _execute_yaml_command(["apply", "-f", "-"], "apiVersion: v1\nkind: Pod")

        # Verify communicate was called exactly once to ensure proper stdin handling
        mock_process.communicate.assert_called_once()


def test_file_descriptor_leak_prevention() -> None:
    """Test that file descriptors are not leaked during command execution."""
    # Count open file descriptors before the test
    start_fds = count_open_fds()

    # Use real temporary file but mock subprocess to avoid actual command execution
    with (
        patch("subprocess.run") as mock_run,
        patch("vibectl.command_handler.console_manager"),
    ):
        # Configure mock
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = "pod/test-pod created"
        mock_run.return_value = mock_process

        # Execute YAML command with real file operations
        _execute_yaml_command(["apply"], "apiVersion: v1\nkind: Pod")

    # Count open file descriptors after the test
    end_fds = count_open_fds()

    # Verify no file descriptor leaks (allow small fluctuations due to Python internals)
    # The difference should be minimal - typically 0 or very small
    assert (
        end_fds - start_fds < 5
    ), f"Possible file descriptor leak: {end_fds - start_fds} new fds"


def count_open_fds() -> int:
    """Count the number of open file descriptors for the current process."""
    if not os.path.exists("/proc/self/fd"):
        # If /proc/self/fd doesn't exist (non-Linux), return a dummy value
        return 0

    try:
        return len(os.listdir("/proc/self/fd"))
    except (PermissionError, FileNotFoundError):
        # Fall back to a dummy value if we can't access fd directory
        return 0
