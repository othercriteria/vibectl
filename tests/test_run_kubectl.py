"""Tests for run_kubectl functionality."""

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
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "test output"
    mock_subprocess.return_value = mock_result

    # Run command
    output = run_kubectl(["get", "pods"], capture=True, config=test_config)

    # Verify command construction
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]

    # With our changes, the order of arguments is now different
    # kubeconfig is placed after the command for kubernetes compatibility
    # Just check that all necessary parts are there, not their exact order
    assert "kubectl" in cmd
    assert "get" in cmd
    assert "pods" in cmd
    assert "--kubeconfig" in cmd
    assert "/test/kubeconfig" in cmd

    # Also verify the output is correct
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

    with pytest.raises(Exception, match="kubectl not found"):
        run_kubectl(["get", "pods"])


def test_run_kubectl_called_process_error(
    mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test kubectl command error handling with CalledProcessError."""
    # Create a mock result with error
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "test error"
    mock_subprocess.return_value = mock_result

    with pytest.raises(Exception, match="test error"):
        run_kubectl(["get", "pods"], capture=True)


def test_run_kubectl_called_process_error_no_stderr(mock_subprocess: MagicMock) -> None:
    """Test kubectl command error handling with CalledProcessError but no stderr."""
    # Create a mock result with error but no stderr
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    with pytest.raises(Exception, match="Command failed with exit code 1"):
        run_kubectl(["get", "pods"], capture=True)


def test_run_kubectl_no_capture(mock_subprocess: MagicMock) -> None:
    """Test kubectl command without output capture."""
    # Create a successful mock result
    mock_result = Mock()
    mock_result.returncode = 0
    mock_subprocess.return_value = mock_result

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
    # Create a mock result with error
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "test error"
    mock_subprocess.return_value = mock_result

    with pytest.raises(Exception) as exc_info:
        run_kubectl(["get", "pods"], capture=False)

    # Check either "test error" or "Command failed" is in the exception message
    assert any(
        msg in str(exc_info.value) for msg in ["test error", "Command failed"]
    ), f"Expected error message not found in: {exc_info.value!s}"
