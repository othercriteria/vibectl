"""Tests for utility functions.

This module tests the utility functions used across the application.
"""

import json
import subprocess
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest

from vibectl.utils import handle_exception


@pytest.fixture(autouse=True)
def mock_console_manager(test_console: Any) -> Generator[None, None, None]:
    """Mock global console manager instance."""
    with patch("vibectl.utils.console_manager", test_console):
        yield


def test_handle_exception_api_key_error(test_console: Any) -> None:
    """Test handling of API key related errors."""
    # Test various API key error messages
    for error_msg in [
        "No key found",
        "Missing API key",
        "API key not found",
    ]:
        with pytest.raises(SystemExit):
            handle_exception(Exception(error_msg))
        output = test_console.error_console.export_text()
        assert "API key" in output
        test_console.error_console.clear()  # Clear for next iteration


def test_handle_exception_kubectl_error(test_console: Any) -> None:
    """Test handling of kubectl subprocess errors."""
    # Create mock CalledProcessError with stderr
    error = subprocess.CalledProcessError(1, "kubectl")
    error.stderr = b"kubectl error message"

    with pytest.raises(SystemExit):
        handle_exception(error)
    assert "kubectl error message" in test_console.error_console.export_text()

    # Test without stderr
    test_console.error_console.clear()
    error.stderr = None
    with pytest.raises(SystemExit):
        handle_exception(error)
    assert "Command failed with exit code 1" in test_console.error_console.export_text()


def test_handle_exception_file_not_found(test_console: Any) -> None:
    """Test handling of file not found errors."""
    # Test kubectl not found
    error = FileNotFoundError()
    error.filename = "kubectl"

    with pytest.raises(SystemExit):
        handle_exception(error)
    assert "kubectl not found in PATH" in test_console.error_console.export_text()

    # Test other file not found
    test_console.error_console.clear()
    error.filename = "other_file"
    with pytest.raises(SystemExit):
        handle_exception(error)
    assert "File not found: other_file" in test_console.error_console.export_text()


def test_handle_exception_json_error(test_console: Any) -> None:
    """Test handling of JSON parsing errors."""
    error = json.JSONDecodeError("Invalid JSON", "{", 0)

    with pytest.raises(SystemExit):
        handle_exception(error)
    assert (
        "kubectl version information not available"
        in test_console.error_console.export_text()
    )


def test_handle_exception_missing_request(test_console: Any) -> None:
    """Test handling of missing request errors."""
    with pytest.raises(SystemExit):
        handle_exception(Exception("missing request after 'vibe'"))
    assert "Missing request after 'vibe'" in test_console.error_console.export_text()


def test_handle_exception_llm_error(test_console: Any) -> None:
    """Test handling of LLM errors."""
    with pytest.raises(SystemExit):
        handle_exception(Exception("LLM error: something went wrong"))
    output = test_console.error_console.export_text()
    assert "LLM error: something went wrong" in output
    assert "Could not get vibe check" in output


def test_handle_exception_invalid_response(test_console: Any) -> None:
    """Test handling of invalid response format errors."""
    with pytest.raises(SystemExit):
        handle_exception(Exception("Invalid response format"))
    assert "Invalid response format" in test_console.error_console.export_text()


def test_handle_exception_truncation(test_console: Any) -> None:
    """Test handling of truncation warnings."""
    with pytest.raises(SystemExit):
        handle_exception(Exception("truncated output warning"))
    assert "Output was truncated" in test_console.error_console.export_text()


def test_handle_exception_empty_output(test_console: Any) -> None:
    """Test handling of empty output cases."""
    with pytest.raises(SystemExit):
        handle_exception(Exception("no output received"))
    assert "No output to display" in test_console.error_console.export_text()


def test_handle_exception_general_error(test_console: Any) -> None:
    """Test handling of general errors."""
    with pytest.raises(SystemExit):
        handle_exception(Exception("some other error"))
    assert "some other error" in test_console.error_console.export_text()


def test_handle_exception_no_exit(test_console: Any) -> None:
    """Test handling exceptions without exiting."""
    handle_exception(Exception("test error"), exit_on_error=False)
    assert "test error" in test_console.error_console.export_text()
