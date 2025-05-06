"""Tests for k8s_utils.py"""

import asyncio
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from vibectl.k8s_utils import (
    create_async_kubectl_process,
    create_kubectl_error,
    run_kubectl,
    run_kubectl_with_yaml,
)
from vibectl.types import Error, Success

# --- Tests for create_kubectl_error ---


def test_create_kubectl_error_from_string() -> None:
    error_msg = " Some error message "
    result = create_kubectl_error(error_msg)
    assert isinstance(result, Error)
    assert result.error == "Some error message"
    assert result.exception is None
    assert result.halt_auto_loop is True  # Default


def test_create_kubectl_error_from_bytes() -> None:
    error_bytes = b" Error from bytes "
    result = create_kubectl_error(error_bytes)
    assert isinstance(result, Error)
    assert result.error == "Error from bytes"
    assert result.exception is None
    assert result.halt_auto_loop is True


def test_create_kubectl_error_with_exception() -> None:
    error_msg = "Another error"
    exception = ValueError("Something went wrong")
    result = create_kubectl_error(error_msg, exception=exception)
    assert isinstance(result, Error)
    assert result.error == "Another error"
    assert result.exception == exception
    assert result.halt_auto_loop is True


@pytest.mark.parametrize(
    "error_input, expected_halt",
    [
        ("error from server (NotFound)", False),
        ("Unknown command 'delete pods --all'", False),
        ("unknown flag: --nonexistent", False),
        ("invalid argument 'foo' for '--bar'", False),
        ('The Deployment "nginx" is invalid: spec.replicas: Invalid value', False),
        ("Regular old error message", True),
        (b"Error from server (Forbidden)", False),
        (b"regular byte error", True),
    ],
)
def test_create_kubectl_error_recoverable_patterns(
    error_input: str | bytes, expected_halt: bool
) -> None:
    result = create_kubectl_error(error_input)
    assert isinstance(result, Error)
    assert result.halt_auto_loop == expected_halt


def test_create_kubectl_error_decode_error() -> None:
    """Test handling of UnicodeDecodeError when decoding bytes."""
    invalid_bytes = b"\xff\xfe"  # Invalid UTF-8 sequence
    result = create_kubectl_error(invalid_bytes)
    assert isinstance(result, Error)
    # Check that the specific fallback message is used
    assert result.error == "Failed to decode error message from kubectl."
    assert result.exception is None  # Exception is not passed in this case
    assert result.halt_auto_loop is True  # Decoding errors should halt


def test_create_kubectl_error_decode_exception() -> None:
    """Test handling of generic Exception during byte decoding."""
    # Create a mock object that simulates bytes but raises Exception on decode
    mock_bytes = MagicMock(spec=bytes)
    mock_bytes.decode.side_effect = Exception("Unexpected decoding issue")

    # Pass the mock object instead of actual bytes
    result = create_kubectl_error(mock_bytes)
    assert isinstance(result, Error)
    assert result.error == "Unexpected error processing error message from kubectl."
    assert result.exception is None  # Exception is not passed
    assert result.halt_auto_loop is True  # Unexpected errors should halt


def test_create_kubectl_error_unexpected_type() -> None:
    """Test handling of non-str/bytes input."""
    unexpected_input = 12345
    result = create_kubectl_error(unexpected_input)  # type: ignore
    assert isinstance(result, Error)
    assert result.error == "Unexpected error message type: int"
    assert result.exception is None
    assert result.halt_auto_loop is True  # Always halt for unexpected types


# --- Tests for run_kubectl ---


@patch("subprocess.run")
def test_run_kubectl_success_no_capture(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0)
    result = run_kubectl(["get", "pods"])
    assert isinstance(result, Success)
    assert result.data is None
    mock_run.assert_called_once_with(
        ["kubectl", "get", "pods"],
        capture_output=False,
        check=False,
        text=True,
        encoding="utf-8",
    )


@patch("subprocess.run")
def test_run_kubectl_success_capture(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout=" pod1 \npod2 ")
    result = run_kubectl(["get", "nodes"], capture=True)
    assert isinstance(result, Success)
    assert result.data == "pod1 \npod2"
    mock_run.assert_called_once_with(
        ["kubectl", "get", "nodes"],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )


@patch("subprocess.run")
def test_run_kubectl_failure_capture(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1, stderr=" Error message ")
    result = run_kubectl(["apply", "-f", "thing.yaml"], capture=True)
    assert isinstance(result, Error)
    assert result.error == "Error message"
    assert result.exception is None
    # Check halt_auto_loop based on error message (default True)
    assert result.halt_auto_loop is True


@patch("subprocess.run")
def test_run_kubectl_failure_no_capture(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1)
    result = run_kubectl(["delete", "pod", "my-pod"])
    assert isinstance(result, Error)
    assert result.error == "Command failed"
    assert result.exception is None
    assert result.halt_auto_loop is True


@patch("subprocess.run")
def test_run_kubectl_failure_no_stderr(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1, stderr="")
    result = run_kubectl(["delete", "pod", "my-pod"], capture=True)
    assert isinstance(result, Error)
    assert result.error == "Command failed with exit code 1"
    assert result.exception is None
    assert result.halt_auto_loop is True


@patch("subprocess.run")
def test_run_kubectl_failure_recoverable(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=1, stderr="error from server (NotFound)"
    )
    result = run_kubectl(["get", "pod", "nonexistent"], capture=True)
    assert isinstance(result, Error)
    assert result.error == "error from server (NotFound)"
    assert result.exception is None
    assert result.halt_auto_loop is False  # Recoverable error


@patch("subprocess.run")
def test_run_kubectl_file_not_found(mock_run: MagicMock) -> None:
    mock_run.side_effect = FileNotFoundError("kubectl not found")
    result = run_kubectl(["version"])
    assert isinstance(result, Error)
    assert result.error == "kubectl not found. Please install it and try again."
    assert isinstance(result.exception, FileNotFoundError)
    assert result.halt_auto_loop is True


@patch("vibectl.k8s_utils.Config")
@patch("subprocess.run")
def test_run_kubectl_with_config(mock_run: MagicMock, mock_config: MagicMock) -> None:
    mock_config.return_value.get.return_value = "/path/to/my/kubeconfig"

    mock_run.return_value = MagicMock(returncode=0)

    result = run_kubectl(["get", "svc"], config=mock_config.return_value)

    assert isinstance(result, Success)
    mock_config.return_value.get.assert_called_once_with("kubeconfig")
    mock_run.assert_called_once_with(
        ["kubectl", "get", "svc", "--kubeconfig", "/path/to/my/kubeconfig"],
        capture_output=False,
        check=False,
        text=True,
        encoding="utf-8",
    )


@patch("vibectl.k8s_utils.Config")
@patch("subprocess.run")
def test_run_kubectl_without_config(
    mock_run: MagicMock, mock_config: MagicMock
) -> None:
    # Ensure Config() returns a mock that returns None for kubeconfig
    mock_config.return_value.get.return_value = None

    mock_run.return_value = MagicMock(returncode=0)

    result = run_kubectl(["get", "ns"])  # No config passed

    assert isinstance(result, Success)
    mock_config.return_value.get.assert_called_once_with("kubeconfig")
    mock_run.assert_called_once_with(
        ["kubectl", "get", "ns"],  # No --kubeconfig arg
        capture_output=False,
        check=False,
        text=True,
        encoding="utf-8",
    )


@patch("subprocess.run")
def test_run_kubectl_called_process_error(mock_run: MagicMock) -> None:
    """Test handling of CalledProcessError exception."""
    error = subprocess.CalledProcessError(
        returncode=1,
        cmd=["kubectl", "fail"],
        stderr=b"Specific error from CalledProcessError",
    )
    mock_run.side_effect = error
    result = run_kubectl(["fail"])
    assert isinstance(result, Error)
    # create_kubectl_error gets the stderr bytes
    assert result.error == "Specific error from CalledProcessError"
    assert (
        result.exception is None
    )  # create_kubectl_error does not store the original exception in this path
    # This error doesn't match recoverable patterns, should halt
    assert result.halt_auto_loop is True


@patch("subprocess.run")
def test_run_kubectl_generic_exception(mock_run: MagicMock) -> None:
    """Test handling of generic exceptions during subprocess.run."""
    error = OSError("Disk is full or something")
    mock_run.side_effect = error
    result = run_kubectl(["whatever"])
    assert isinstance(result, Error)
    assert result.error == "Disk is full or something"
    assert result.exception == error  # Generic exceptions are passed through
    assert result.halt_auto_loop is True


# --- Tests for run_kubectl_with_yaml ---

YAML_CONTENT = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: test-container
    image: busybox
"""

MULTI_YAML_CONTENT = """
apiVersion: v1
kind: Namespace
metadata:
  name: test-ns
---
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: test-ns
spec:
  containers:
  - name: test-container
    image: busybox
"""


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_success(mock_popen: MagicMock) -> None:
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"pod/test-pod created", b"")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    result = run_kubectl_with_yaml(["apply", "-f", "-"], YAML_CONTENT)

    assert isinstance(result, Success)
    assert result.data == "pod/test-pod created"
    mock_popen.assert_called_once()
    # Check command includes 'kubectl apply -f -'
    call_args = mock_popen.call_args[0][0]
    assert call_args[:3] == ["kubectl", "apply", "-f"]
    assert call_args[-1] == "-"
    # Check stdin was written to
    mock_process.communicate.assert_called_once()
    written_bytes = mock_process.communicate.call_args[1]["input"]
    # Check if the input starts with ---, handles potential initial whitespace
    assert written_bytes.strip().startswith(b"---")
    assert YAML_CONTENT.encode("utf-8") in written_bytes


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_multi_doc_success(mock_popen: MagicMock) -> None:
    mock_process = MagicMock()
    mock_process.communicate.return_value = (
        b"namespace/test-ns created\npod/test-pod created",
        b"",
    )
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    result = run_kubectl_with_yaml(["apply", "-f", "-"], MULTI_YAML_CONTENT)

    assert isinstance(result, Success)
    assert result.data == "namespace/test-ns created\npod/test-pod created"
    mock_popen.assert_called_once()
    mock_process.communicate.assert_called_once()
    written_bytes = mock_process.communicate.call_args[1]["input"]
    # Ensure multi-doc format is preserved or correctly handled
    assert b"---\napiVersion" in written_bytes
    assert MULTI_YAML_CONTENT.encode("utf-8") in written_bytes


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_failure(mock_popen: MagicMock) -> None:
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"", b"Error applying YAML")
    mock_process.returncode = 1
    mock_popen.return_value = mock_process

    result = run_kubectl_with_yaml(["create", "-f", "-"], YAML_CONTENT)

    assert isinstance(result, Error)
    assert result.error == "Error applying YAML"
    assert result.halt_auto_loop is True  # Default halt


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_timeout(mock_popen: MagicMock) -> None:
    mock_process = MagicMock()
    mock_process.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd="kubectl apply", timeout=30),
        (b"", b"Timeout"),
    ]
    mock_process.returncode = -9  # SIGKILL often results in -9
    mock_popen.return_value = mock_process

    result = run_kubectl_with_yaml(["apply", "-f", "-"], YAML_CONTENT)

    assert isinstance(result, Error)
    assert result.error == "Command timed out after 30 seconds"
    assert isinstance(result.exception, subprocess.TimeoutExpired)
    mock_process.kill.assert_called_once()
    assert mock_process.communicate.call_count == 2


@patch("tempfile.NamedTemporaryFile")
@patch("subprocess.run")
@patch("os.unlink")
@patch("os.path.exists")
def test_run_kubectl_with_yaml_tempfile_success(
    mock_exists: MagicMock,
    mock_unlink: MagicMock,
    mock_run: MagicMock,
    mock_tempfile: MagicMock,
) -> None:
    # Mock the temporary file context manager
    mock_temp_file = MagicMock()
    mock_temp_file.name = "/tmp/testfile.yaml"
    mock_tempfile.return_value.__enter__.return_value = mock_temp_file
    mock_exists.return_value = True  # Assume file exists for cleanup

    # Mock subprocess run
    mock_run.return_value = MagicMock(
        returncode=0, stdout="pod/test-pod configured", stderr=""
    )

    result = run_kubectl_with_yaml(
        ["apply"], YAML_CONTENT
    )  # No '-f -', should use temp file

    assert isinstance(result, Success)
    assert result.data == "pod/test-pod configured"
    # Check tempfile was used
    mock_tempfile.assert_called_once_with(mode="w", suffix=".yaml", delete=False)
    mock_temp_file.write.assert_called_once_with(
        "---\n" + YAML_CONTENT
    )  # Check prepended '---'
    # Check subprocess call
    mock_run.assert_called_once()
    cmd_called = mock_run.call_args[0][0]
    assert cmd_called == ["kubectl", "apply", "-f", "/tmp/testfile.yaml"]
    # Check cleanup
    mock_exists.assert_called_once_with("/tmp/testfile.yaml")
    mock_unlink.assert_called_once_with("/tmp/testfile.yaml")


@patch("tempfile.NamedTemporaryFile")
@patch("subprocess.run")
@patch("os.unlink")
@patch("os.path.exists")
def test_run_kubectl_with_yaml_tempfile_failure(
    mock_exists: MagicMock,
    mock_unlink: MagicMock,
    mock_run: MagicMock,
    mock_tempfile: MagicMock,
) -> None:
    mock_temp_file = MagicMock()
    mock_temp_file.name = "/tmp/fail.yaml"
    mock_tempfile.return_value.__enter__.return_value = mock_temp_file
    mock_exists.return_value = True

    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Temp file error")

    result = run_kubectl_with_yaml(["create"], YAML_CONTENT)

    assert isinstance(result, Error)
    assert result.error == "Temp file error"
    mock_exists.assert_called_once_with("/tmp/fail.yaml")
    mock_unlink.assert_called_once_with("/tmp/fail.yaml")


@patch("tempfile.NamedTemporaryFile")
@patch("subprocess.run")
@patch("os.unlink")
@patch("os.path.exists")
def test_run_kubectl_with_yaml_tempfile_cleanup_error(
    mock_exists: MagicMock,
    mock_unlink: MagicMock,
    mock_run: MagicMock,
    mock_tempfile: MagicMock,
) -> None:
    mock_temp_file = MagicMock()
    mock_temp_file.name = "/tmp/cleanup_fail.yaml"
    mock_tempfile.return_value.__enter__.return_value = mock_temp_file
    mock_exists.return_value = True
    mock_unlink.side_effect = OSError("Permission denied")  # Simulate cleanup failure

    mock_run.return_value = MagicMock(
        returncode=0, stdout="Deleted successfully", stderr=""
    )

    # We expect success from run, but the cleanup failure should be logged (not crash)
    result = run_kubectl_with_yaml(["delete"], YAML_CONTENT)

    assert isinstance(result, Success)  # Command itself succeeded
    assert result.data == "Deleted successfully"
    mock_exists.assert_called_once_with("/tmp/cleanup_fail.yaml")
    mock_unlink.assert_called_once_with("/tmp/cleanup_fail.yaml")
    # We can't easily assert logger calls here without more setup,
    # but coverage will show the except block was hit.


@patch("tempfile.NamedTemporaryFile")
def test_run_kubectl_with_yaml_tempfile_creation_error(
    mock_tempfile: MagicMock,
) -> None:
    mock_tempfile.side_effect = OSError("Disk full")

    result = run_kubectl_with_yaml(["apply"], YAML_CONTENT)

    assert isinstance(result, Error)
    assert "Error executing YAML command: Disk full" in result.error
    assert isinstance(result.exception, OSError)


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_already_starts_with_dashes(
    mock_popen: MagicMock,
) -> None:
    """Test stdin execution when input YAML already starts with ---."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"pod/test-pod created", b"")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    yaml_with_dashes = "---" + YAML_CONTENT  # Start with dashes

    result = run_kubectl_with_yaml(["apply", "-f", "-"], yaml_with_dashes)

    assert isinstance(result, Success)
    mock_process.communicate.assert_called_once()
    written_bytes = mock_process.communicate.call_args[1]["input"]
    # Should NOT prepend another --- if it already starts with it
    assert written_bytes == yaml_with_dashes.encode("utf-8")


# --- Tests for create_async_kubectl_process ---


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_success(
    mock_create_subprocess: MagicMock,
) -> None:
    mock_process = MagicMock(spec=asyncio.subprocess.Process)
    mock_create_subprocess.return_value = mock_process

    cmd_args = ["get", "pods", "--watch"]
    process = await create_async_kubectl_process(cmd_args)

    assert process == mock_process
    mock_create_subprocess.assert_awaited_once_with(
        "kubectl",
        "get",
        "pods",
        "--watch",  # Command args directly after kubectl
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@patch("vibectl.k8s_utils.Config")
@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_with_kubeconfig(
    mock_create_subprocess: MagicMock, mock_config: MagicMock
) -> None:
    mock_config.return_value.get.return_value = "/custom/path/kubeconfig"

    mock_process = MagicMock(spec=asyncio.subprocess.Process)
    mock_create_subprocess.return_value = mock_process

    cmd_args = ["logs", "my-pod", "-f"]
    process = await create_async_kubectl_process(
        cmd_args, config=mock_config.return_value
    )

    assert process == mock_process
    mock_config.return_value.get.assert_called_once_with("kubeconfig")
    mock_create_subprocess.assert_awaited_once_with(
        "kubectl",
        "--kubeconfig",
        "/custom/path/kubeconfig",
        "logs",
        "my-pod",
        "-f",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_no_capture(
    mock_create_subprocess: MagicMock,
) -> None:
    mock_process = MagicMock(spec=asyncio.subprocess.Process)
    mock_create_subprocess.return_value = mock_process

    cmd_args = ["exec", "-it", "mypod", "--", "bash"]
    process = await create_async_kubectl_process(
        cmd_args, capture_stdout=False, capture_stderr=False
    )

    assert process == mock_process
    mock_create_subprocess.assert_awaited_once_with(
        "kubectl",
        "exec",
        "-it",
        "mypod",
        "--",
        "bash",
        stdout=None,  # Not captured
        stderr=None,  # Not captured
    )


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_file_not_found(
    mock_create_subprocess: MagicMock,
) -> None:
    mock_create_subprocess.side_effect = FileNotFoundError("kubectl not found")

    with pytest.raises(
        FileNotFoundError, match="kubectl not found. Please install it."
    ):
        await create_async_kubectl_process(["version"])


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_other_exception(
    mock_create_subprocess: MagicMock,
) -> None:
    mock_create_subprocess.side_effect = RuntimeError("Something else failed")

    with pytest.raises(RuntimeError, match="Something else failed"):
        await create_async_kubectl_process(["config", "view"])
