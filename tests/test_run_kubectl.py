"""Tests for run_kubectl functionality."""

import subprocess
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from vibectl.command_handler import run_kubectl

# The mock_subprocess and test_config fixtures are now provided by conftest.py


def test_run_kubectl_basic(mock_subprocess: MagicMock) -> None:
    """Test basic kubectl command execution."""
    # Set up mock
    mock_result = Mock()
    mock_result.stdout = "test output"
    mock_subprocess.run.return_value = mock_result

    result = run_kubectl(["get", "pods"], capture=True)
    assert result == "test output"


def test_run_kubectl_success(mock_subprocess: MagicMock, test_config: Any) -> None:
    """Test successful kubectl command execution."""
    # Set test kubeconfig
    test_config.set("kubeconfig", "/test/kubeconfig")

    # Configure mock to return success
    mock_subprocess.return_value.stdout = "test output"

    # Run command
    output = run_kubectl(["get", "pods"], capture=True, config=test_config)

    # Verify command construction
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "--kubeconfig", "/test/kubeconfig", "get", "pods"]
    assert output == "test output"


def test_run_kubectl_no_kubeconfig(
    mock_subprocess: MagicMock, test_config: Any
) -> None:
    """Test kubectl command without kubeconfig."""
    # Explicitly set kubeconfig to None
    test_config.set("kubeconfig", None)

    # Configure mock to return success
    mock_subprocess.return_value.stdout = "test output"

    output = run_kubectl(["get", "pods"], capture=True, config=test_config)

    # Verify command construction without kubeconfig
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "get", "pods"]
    assert output == "test output"


def test_run_kubectl_error(mock_subprocess: MagicMock) -> None:
    """Test kubectl command error handling."""
    mock_subprocess.side_effect = Exception("test error")

    with pytest.raises(Exception, match="test error"):
        run_kubectl(["get", "pods"])


def test_run_kubectl_not_found(mock_subprocess: MagicMock) -> None:
    """Test kubectl not found error."""
    mock_subprocess.side_effect = FileNotFoundError()

    with pytest.raises(FileNotFoundError):
        run_kubectl(["get", "pods"])


def test_run_kubectl_called_process_error(
    mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test kubectl command error handling with CalledProcessError."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="test error")
    mock_subprocess.side_effect = error

    output = run_kubectl(["get", "pods"], capture=True)

    # Verify error was printed to stderr
    captured = capsys.readouterr()
    assert captured.err == "test error\n"
    # Check error message is properly formatted
    assert output == "Error: test error"


def test_run_kubectl_called_process_error_no_stderr(mock_subprocess: MagicMock) -> None:
    """Test kubectl command error handling with CalledProcessError but no stderr."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="")
    mock_subprocess.side_effect = error

    output = run_kubectl(["get", "pods"], capture=True)
    assert output == "Error: Command failed with exit code 1"


def test_run_kubectl_no_capture(mock_subprocess: MagicMock) -> None:
    """Test kubectl command without output capture."""
    output = run_kubectl(["get", "pods"], capture=False)

    # Verify command was run without capture
    mock_subprocess.assert_called_once()
    assert output is None


def test_run_kubectl_called_process_error_no_capture(
    mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test kubectl command error handling with CalledProcessError in non-capture mode.

    Verifies proper error handling when subprocess raises a CalledProcessError.
    """
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="test error")
    mock_subprocess.side_effect = error

    output = run_kubectl(["get", "pods"], capture=False)

    # Verify error was printed to stderr and no output returned
    captured = capsys.readouterr()
    assert captured.err == "test error\n"
    assert output is None
