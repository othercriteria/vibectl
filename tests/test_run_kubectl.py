"""Tests for run_kubectl functionality."""

import subprocess
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import run_kubectl
from vibectl.k8s_utils import (
    create_kubectl_error,
    run_kubectl_with_yaml,
)
from vibectl.types import Error, Success

# The mock_subprocess and test_config fixtures are now provided by conftest.py


def test_run_kubectl_basic(mock_subprocess: MagicMock) -> None:
    """Test basic kubectl command execution."""
    # Set up mock
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "test output"
    mock_subprocess.run.return_value = mock_result

    result = run_kubectl(["get", "pods"], capture=True)
    assert isinstance(result, Success)
    assert result.data == "test output"


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

    # Verify the output is correct
    assert isinstance(output, Success)
    assert output.data == "test output"


def test_run_kubectl_no_kubeconfig(
    mock_subprocess: MagicMock, test_config: Any
) -> None:
    """Test kubectl command without kubeconfig."""
    # Explicitly set kubeconfig to None
    test_config.set("kubeconfig", None)

    # Configure mock to return success
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "test output"
    mock_subprocess.return_value = mock_result

    output = run_kubectl(["get", "pods"], capture=True, config=test_config)

    # Verify command construction without kubeconfig
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "get", "pods"]

    # Verify the output is correct
    assert isinstance(output, Success)
    assert output.data == "test output"


def test_run_kubectl_error(mock_subprocess: MagicMock) -> None:
    """Test kubectl command error handling."""
    mock_subprocess.side_effect = Exception("test error")

    result = run_kubectl(["get", "pods"], capture=True)
    assert isinstance(result, Error)
    assert "test error" in result.error


def test_run_kubectl_not_found(mock_subprocess: MagicMock) -> None:
    """Test kubectl not found error."""
    mock_subprocess.side_effect = FileNotFoundError()

    result = run_kubectl(["get", "pods"], capture=True)
    assert isinstance(result, Error)
    assert result.error == "kubectl not found. Please install it and try again."
    assert isinstance(result.exception, FileNotFoundError)


def test_run_kubectl_called_process_error(
    mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test kubectl command error handling with CalledProcessError."""
    # Create a mock result with error
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "test error"
    mock_subprocess.return_value = mock_result

    result = run_kubectl(["get", "pods"], capture=True)
    assert isinstance(result, Error)
    assert "test error" in result.error


def test_run_kubectl_called_process_error_no_stderr(mock_subprocess: MagicMock) -> None:
    """Test kubectl command error handling with CalledProcessError but no stderr."""
    # Create a mock result with error but no stderr
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    result = run_kubectl(["get", "pods"], capture=True)
    assert isinstance(result, Error)
    assert "Command failed with exit code 1" in result.error


def test_run_kubectl_no_capture(mock_subprocess: MagicMock) -> None:
    """Test kubectl command without output capture."""
    # Create a successful mock result
    mock_result = Mock()
    mock_result.returncode = 0
    mock_subprocess.return_value = mock_result

    output = run_kubectl(["get", "pods"], capture=False)

    # Verify command was run without capture
    mock_subprocess.assert_called_once()
    assert isinstance(output, Success)
    assert output.data is None


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

    result = run_kubectl(["get", "pods"], capture=False)
    assert isinstance(result, Error)
    # In the refactored code, when capture=False, the error message is "Command failed"
    assert result.error == "Command failed"


# Test the create_kubectl_error function specifically
def test_create_kubectl_error_halt_flag() -> None:
    """Test that create_kubectl_error correctly sets halt_auto_loop flag."""
    # 1. Test recoverable errors (should have halt_auto_loop=False)
    # Explicitly type the list for mypy
    recoverable_messages: list[str | bytes] = [
        b'Error from server (NotFound): pods "my-pod" not found',
        "Error from server (Forbidden): ...",
        'unknown command "pod" for "kubectl"',
        b"error: unknown flag: --storage-class",
        'error: invalid argument "foo" for "--port"',
        "Error: Invalid argument -n for flag n",  # Example from real error
    ]
    for msg in recoverable_messages:
        err_obj = create_kubectl_error(msg)
        assert isinstance(err_obj, Error)
        assert (
            err_obj.halt_auto_loop is False
        ), f"Expected halt_auto_loop=False for recoverable error: {msg!r}"

    # 2. Test potentially halting errors (should have halt_auto_loop=True)
    # Explicitly type the list for mypy
    halting_messages: list[str | bytes] = [
        b"Unable to connect to the server: dial tcp ...",
        "error: You must be logged in to the server (Unauthorized)",
        "Some other kubectl error message",
        b"Another error message as bytes",
    ]
    for msg in halting_messages:
        err_obj = create_kubectl_error(msg)
        assert isinstance(err_obj, Error)
        assert (
            err_obj.halt_auto_loop is True
        ), f"Expected halt_auto_loop=True for halting error: {msg!r}"

    # 3. Test edge case: decoding error
    err_obj_decode = create_kubectl_error(b"\x80abc")  # Invalid utf-8 start byte
    assert isinstance(err_obj_decode, Error)
    assert err_obj_decode.error == "Failed to decode error message from kubectl."
    assert err_obj_decode.halt_auto_loop is True  # Decoding errors halt

    # 4. Test edge case: unexpected input type (int)
    err_obj_int = create_kubectl_error(123)  # type: ignore
    assert isinstance(err_obj_int, Error)
    assert "Unexpected error message type: int" in err_obj_int.error
    assert err_obj_int.halt_auto_loop is True  # Unexpected types halt

    # 5. Test edge case: unexpected input type (None)
    err_obj_none = create_kubectl_error(None)  # type: ignore
    assert isinstance(err_obj_none, Error)
    assert "Unexpected error message type: NoneType" in err_obj_none.error
    assert err_obj_none.halt_auto_loop is True  # Unexpected types halt


# --- Tests for run_kubectl_with_yaml ---

TEST_YAML_CONTENT = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: nginx
    image: nginx:1.14.2
"""

TEST_YAML_NO_DASHES = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-map
data:
  key: value
"""


# Need to mock subprocess.Popen for stdin tests
@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_success(mock_popen: MagicMock) -> None:
    """Test successful execution with YAML via stdin."""
    # Mock Popen and communicate
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"Applied", b"")  # stdout, stderr as bytes
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Success)
    assert result.data == "Applied"
    mock_popen.assert_called_once()
    mock_proc.communicate.assert_called_once()
    call_args, call_kwargs = mock_proc.communicate.call_args
    expected_bytes = b"---\n" + TEST_YAML_CONTENT.encode("utf-8")
    assert call_kwargs["input"] == expected_bytes


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_error(mock_popen: MagicMock) -> None:
    """Test error handling with YAML via stdin."""
    # Mock Popen and communicate for error
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (
        b"",
        b"Error applying",
    )  # stdout, stderr as bytes
    mock_proc.returncode = 1
    mock_popen.return_value = mock_proc

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Error)
    assert "Error applying" in result.error
    # Check that halt_auto_loop defaults to True for this type of error
    assert result.halt_auto_loop is True


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_timeout(mock_popen: MagicMock) -> None:
    """Test timeout handling with YAML via stdin."""
    # Mock Popen and communicate to raise TimeoutExpired
    mock_proc = MagicMock()
    # Side effect function defined below
    mock_proc.communicate.side_effect = communicate_side_effect_for_timeout(mock_proc)
    # Mock kill()
    mock_proc.kill = MagicMock()
    mock_popen.return_value = mock_proc

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Error)
    assert "Command timed out" in result.error
    assert isinstance(result.exception, subprocess.TimeoutExpired)
    mock_proc.kill.assert_called_once()  # Verify kill was called
    # Check communicate called twice (initial + after kill)
    assert mock_proc.communicate.call_count == 2


# Helper for the timeout test side effect
def communicate_side_effect_for_timeout(
    mock_proc: MagicMock,
) -> Callable[..., tuple[bytes, bytes]]:
    def side_effect(*args: Any, **kwargs: Any) -> tuple[bytes, bytes]:
        # First call raises TimeoutExpired
        if mock_proc.communicate.call_count == 1:
            # Reformat long line
            raise subprocess.TimeoutExpired(cmd="kubectl", timeout=30)
        # Second call (after kill) returns empty bytes
        return (b"", b"")

    return side_effect


# Use direct patch for subprocess.run for temp file tests
@patch("subprocess.run")
def test_run_kubectl_with_yaml_file_success(mock_run: MagicMock) -> None:
    """Test successful execution with YAML via temp file."""
    mock_result = Mock()
    mock_result.stdout = "Created"
    mock_result.stderr = ""
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    # Reformat long line
    with patch("os.unlink") as mock_unlink, patch("os.path.exists", return_value=True):
        args = ["create"]
        result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

        assert isinstance(result, Success)
        assert result.data == "Created"
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "-f" in call_args
        temp_file_path = call_args[call_args.index("-f") + 1]
        assert temp_file_path.endswith(".yaml")
        mock_unlink.assert_called_once_with(temp_file_path)


@patch("subprocess.run")
def test_run_kubectl_with_yaml_file_error(mock_run: MagicMock) -> None:
    """Test error handling with YAML via temp file."""
    mock_result = Mock()
    mock_result.stdout = ""
    mock_result.stderr = "Error creating"
    mock_result.returncode = 1
    mock_run.return_value = mock_result

    with patch("os.unlink") as mock_unlink, patch("os.path.exists", return_value=True):
        args = ["create"]
        result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

        assert isinstance(result, Error)
        assert "Error creating" in result.error
        assert result.halt_auto_loop is True
        mock_unlink.assert_called_once()


@patch("subprocess.run")
@patch("tempfile.NamedTemporaryFile")
def test_run_kubectl_with_yaml_file_cleanup_error(
    mock_tempfile: MagicMock, mock_run: MagicMock
) -> None:
    """Test cleanup error handling with YAML via temp file."""
    mock_result = Mock()
    mock_result.stdout = "Created"
    mock_result.stderr = ""
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    # Mock NamedTemporaryFile to control the temp path for assertion
    mock_file = MagicMock()
    mock_file.__enter__.return_value.name = "/tmp/fake_temp_file.yaml"
    mock_tempfile.return_value = mock_file

    with (
        patch("os.unlink", side_effect=OSError("Permission denied")) as mock_unlink,
        patch("os.path.exists", return_value=True),
    ):
        args = ["create"]
        result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

        assert isinstance(result, Success)
        assert result.data == "Created"
        mock_unlink.assert_called_once_with("/tmp/fake_temp_file.yaml")  # Check path


@patch("re.sub")  # Patch re.sub directly for this test
def test_run_kubectl_with_yaml_general_error(mock_re_sub: MagicMock) -> None:
    """Test general Exception handling during YAML processing."""
    mock_re_sub.side_effect = ValueError("Regex error")

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Error)
    assert "Error executing YAML command: Regex error" in result.error
    assert isinstance(result.exception, ValueError)


# Add tests for remaining coverage gaps in run_kubectl_with_yaml


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_no_dashes(mock_popen: MagicMock) -> None:
    """Test YAML via stdin when input doesn't start with ---."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"Applied", b"")
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_NO_DASHES)

    assert isinstance(result, Success)
    mock_proc.communicate.assert_called_once()
    call_args, call_kwargs = mock_proc.communicate.call_args
    # Verify --- was prepended
    expected_bytes = b"---\n" + TEST_YAML_NO_DASHES.encode("utf-8")
    assert call_kwargs["input"] == expected_bytes


@patch("subprocess.run")
def test_run_kubectl_with_yaml_file_f_already_present(
    mock_run: MagicMock,
) -> None:
    """Test YAML via temp file when -f argument is already present."""
    mock_result = Mock()
    mock_result.stdout = "AlreadyPresent"
    mock_result.stderr = ""
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    # Mock NamedTemporaryFile and os.unlink
    with (
        patch("tempfile.NamedTemporaryFile") as mock_tempfile,
        patch("os.unlink") as mock_unlink,
        patch("os.path.exists", return_value=True),
    ):
        # Setup mock temp file
        mock_file = MagicMock()
        mock_file.__enter__.return_value.name = "/tmp/dummy_file.yaml"
        mock_tempfile.return_value = mock_file

        # Provide args that already include -f (but not -f -)
        args = ["apply", "-f", "some_other_file.yaml"]
        result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

        assert isinstance(result, Success)
        assert result.data == "AlreadyPresent"
        mock_run.assert_called_once()
        # Verify the original args were used, and NO extra -f temp_path was added
        call_args = mock_run.call_args[0][0]
        assert call_args == ["kubectl", "apply", "-f", "some_other_file.yaml"]
        # Verify temp file was created and cleaned up even though not used in cmd
        mock_tempfile.assert_called_once()
        mock_unlink.assert_called_once_with("/tmp/dummy_file.yaml")


@patch("subprocess.run")
@patch("tempfile.NamedTemporaryFile")
def test_run_kubectl_with_yaml_file_cleanup_no_exist(
    mock_tempfile: MagicMock, mock_run: MagicMock
) -> None:
    """Test temp file cleanup when file doesn't exist (e.g., deleted early)."""
    mock_result = Mock()
    mock_result.stdout = "Created"
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    # Setup mock temp file
    mock_file = MagicMock()
    mock_file.__enter__.return_value.name = "/tmp/gone_file.yaml"
    mock_tempfile.return_value = mock_file

    # Mock os.path.exists to return False, os.unlink should not be called
    with patch("os.unlink") as mock_unlink, patch("os.path.exists", return_value=False):
        args = ["create"]
        result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

        assert isinstance(result, Success)
        assert result.data == "Created"
        # Verify unlink was NOT called because path didn't exist
        mock_unlink.assert_not_called()
