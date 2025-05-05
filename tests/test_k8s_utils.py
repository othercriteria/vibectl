"""Tests for k8s_utils.py"""

import asyncio
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibectl.config import Config  # Import Config for testing run_kubectl with config
from vibectl.k8s_utils import (
    create_async_kubectl_process,
    create_kubectl_error,
    run_kubectl,
    run_kubectl_with_yaml,
)
from vibectl.types import Error, Success

# --- Tests for create_kubectl_error ---


def test_create_kubectl_error_recoverable_patterns() -> None:
    """Test that recoverable error patterns result in halt_auto_loop=False."""
    # Explicitly type hint the list
    recoverable_messages: list[str | bytes] = [
        b'Error from server (NotFound): pods "my-pod" not found',
        "Error from server (Forbidden): ...",
        'unknown command "pod" for "kubectl"',
        b"error: unknown flag: --storage-class",
        'error: invalid argument "foo" for "--port"',
        "Error: Invalid argument -n for flag n",
        "Error from server (Conflict): error when patching ...",  # Example Conflict
        "Error from server (AlreadyExists): ...",  # Example AlreadyExists
        b"error: is invalid: spec.containers[0].image",  # Example 'is invalid' error
    ]
    for msg in recoverable_messages:
        err_obj = create_kubectl_error(msg)
        assert isinstance(err_obj, Error)
        assert (
            err_obj.halt_auto_loop is False
        ), f"Expected halt_auto_loop=False for recoverable error: {msg!r}"
        # Conditional decoding for assertion
        expected_content = (
            msg.decode("utf-8", "ignore") if isinstance(msg, bytes) else msg
        )
        assert (
            expected_content.strip() in err_obj.error
        )  # Check msg content is in error string


def test_create_kubectl_error_halting_patterns() -> None:
    """Test that non-recoverable error patterns result in halt_auto_loop=True."""
    # Explicitly type hint the list
    halting_messages: list[str | bytes] = [
        b"Unable to connect to the server: dial tcp ...",
        "error: You must be logged in to the server (Unauthorized)",
        "Some other kubectl error message",
        b"Another error message as bytes",
        "The connection to the server localhost:8080 was refused - ...",
        "error: no context exists with the name: non-existent-context",
    ]
    for msg in halting_messages:
        err_obj = create_kubectl_error(msg)
        assert isinstance(err_obj, Error)
        assert (
            err_obj.halt_auto_loop is True
        ), f"Expected halt_auto_loop=True for halting error: {msg!r}"
        # Conditional decoding for assertion
        expected_content = (
            msg.decode("utf-8", "ignore") if isinstance(msg, bytes) else msg
        )
        assert expected_content.strip() in err_obj.error


def test_create_kubectl_error_with_exception() -> None:
    """Test passing an exception object."""
    exc = ValueError("Original error")
    err_obj = create_kubectl_error("Some message", exception=exc)
    assert isinstance(err_obj, Error)
    assert err_obj.exception is exc
    assert "Some message" in err_obj.error
    assert err_obj.halt_auto_loop is True  # Defaults to True if pattern doesn't match


def test_create_kubectl_error_decoding_error() -> None:
    """Test behavior with invalid UTF-8 bytes."""
    err_obj = create_kubectl_error(b"\x80abc")  # Invalid start byte
    assert isinstance(err_obj, Error)
    assert err_obj.error == "Failed to decode error message from kubectl."
    assert err_obj.halt_auto_loop is True


def test_create_kubectl_error_unexpected_type_none() -> None:
    """Test behavior with None input."""
    err_obj = create_kubectl_error(None)  # type: ignore
    assert isinstance(err_obj, Error)
    assert "Unexpected error message type: NoneType" in err_obj.error
    assert err_obj.halt_auto_loop is True


def test_create_kubectl_error_unexpected_type_int() -> None:
    """Test behavior with int input."""
    err_obj = create_kubectl_error(123)  # type: ignore
    assert isinstance(err_obj, Error)
    assert "Unexpected error message type: int" in err_obj.error
    assert err_obj.halt_auto_loop is True


# --- Tests for run_kubectl ---


@patch("subprocess.run")
def test_run_kubectl_success_capture(mock_run: MagicMock) -> None:
    """Test successful execution with capture=True."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_result.stdout = "kubectl output here\n"  # Include newline
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    result = run_kubectl(["get", "pods"], capture=True)
    assert isinstance(result, Success)
    assert result.data == "kubectl output here"  # Should be stripped
    mock_run.assert_called_once_with(
        ["kubectl", "get", "pods"],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )


@patch("subprocess.run")
def test_run_kubectl_success_no_capture(mock_run: MagicMock) -> None:
    """Test successful execution with capture=False."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    result = run_kubectl(["get", "pods"], capture=False)
    assert isinstance(result, Success)
    assert result.data is None  # No data captured
    mock_run.assert_called_once_with(
        ["kubectl", "get", "pods"],
        capture_output=False,
        check=False,
        text=True,
        encoding="utf-8",
    )


@patch("subprocess.run")
def test_run_kubectl_with_kubeconfig(mock_run: MagicMock, test_config: Config) -> None:
    """Test command includes kubeconfig when provided."""
    test_config.set("kubeconfig", "/path/to/test.kubeconfig")
    mock_result = MagicMock(
        spec=subprocess.CompletedProcess, returncode=0, stdout="Success"
    )
    mock_run.return_value = mock_result

    run_kubectl(["config", "view"], capture=True, config=test_config)
    mock_run.assert_called_once()
    called_args = mock_run.call_args[0][0]
    assert called_args == [
        "kubectl",
        "config",
        "view",
        "--kubeconfig",
        "/path/to/test.kubeconfig",
    ]


@patch("subprocess.run")
def test_run_kubectl_without_kubeconfig(
    mock_run: MagicMock, test_config: Config
) -> None:
    """Test command does not include kubeconfig when not set."""
    test_config.set("kubeconfig", None)  # Explicitly set to None
    mock_result = MagicMock(
        spec=subprocess.CompletedProcess, returncode=0, stdout="Success"
    )
    mock_run.return_value = mock_result

    run_kubectl(["config", "view"], capture=True, config=test_config)
    mock_run.assert_called_once()
    called_args = mock_run.call_args[0][0]
    assert called_args == ["kubectl", "config", "view"]


@patch("subprocess.run")
def test_run_kubectl_file_not_found(mock_run: MagicMock) -> None:
    """Test FileNotFoundError handling."""
    mock_run.side_effect = FileNotFoundError("kubectl not found")

    result = run_kubectl(["get", "pods"], capture=True)
    assert isinstance(result, Error)
    assert result.error == "kubectl not found. Please install it and try again."
    assert isinstance(result.exception, FileNotFoundError)
    assert result.halt_auto_loop is True


@patch("subprocess.run")
def test_run_kubectl_called_process_error_with_stderr(mock_run: MagicMock) -> None:
    """Test CalledProcessError handling when stderr is present."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = 'Error from server (NotFound): pods "blah" not found'
    mock_run.return_value = mock_result

    result = run_kubectl(["get", "pod", "blah"], capture=True)
    assert isinstance(result, Error)
    assert 'Error from server (NotFound): pods "blah" not found' in result.error
    # This specific error should be recoverable
    assert result.halt_auto_loop is False


@patch("subprocess.run")
def test_run_kubectl_called_process_error_no_stderr_capture(
    mock_run: MagicMock,
) -> None:
    """Test CalledProcessError handling when stderr is empty and capture=True."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 127  # Example non-zero code
    mock_result.stdout = ""
    mock_result.stderr = ""  # Empty stderr
    mock_run.return_value = mock_result

    result = run_kubectl(["invalid-command"], capture=True)
    assert isinstance(result, Error)
    # Should use the generic message including return code
    assert "Command failed with exit code 127" in result.error
    # Default to halting if specific pattern not matched
    assert result.halt_auto_loop is True


@patch("subprocess.run")
def test_run_kubectl_called_process_error_no_capture(mock_run: MagicMock) -> None:
    """Test CalledProcessError handling when capture=False."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 1
    # stdout/stderr aren't captured or used when capture=False in the error path
    mock_run.return_value = mock_result

    result = run_kubectl(["get", "pods"], capture=False)
    assert isinstance(result, Error)
    # Simplified error message when not capturing
    assert result.error == "Command failed"
    # Error message "Command failed" doesn't match recoverable patterns
    assert result.halt_auto_loop is True


@patch("subprocess.run")
def test_run_kubectl_generic_exception(mock_run: MagicMock) -> None:
    """Test handling of unexpected exceptions during subprocess.run."""
    mock_run.side_effect = OSError("Disk full")

    result = run_kubectl(["get", "pods"], capture=True)
    assert isinstance(result, Error)
    assert "Disk full" in result.error
    assert isinstance(result.exception, OSError)
    assert result.halt_auto_loop is True  # Generic exceptions should halt


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


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_success(mock_popen: MagicMock) -> None:
    """Test successful execution with YAML via stdin ('-f -')."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"pod/test-pod created", b"")
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Success)
    assert result.data == "pod/test-pod created"
    mock_popen.assert_called_once_with(
        ["kubectl", "apply", "-f", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    mock_proc.communicate.assert_called_once()
    call_args, call_kwargs = mock_proc.communicate.call_args
    # Expect --- to be prepended
    expected_bytes = b"---\n" + TEST_YAML_CONTENT.encode("utf-8")
    assert call_kwargs["input"] == expected_bytes


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_no_dashes_input(mock_popen: MagicMock) -> None:
    """Test stdin execution when input YAML doesn't start with ---."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"configmap/test-map created", b"")
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    args = ["create", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_NO_DASHES)

    assert isinstance(result, Success)
    assert result.data == "configmap/test-map created"
    mock_proc.communicate.assert_called_once()
    call_args, call_kwargs = mock_proc.communicate.call_args
    # Expect --- to be prepended
    expected_bytes = b"---\n" + TEST_YAML_NO_DASHES.encode("utf-8")
    assert call_kwargs["input"] == expected_bytes


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_error(mock_popen: MagicMock) -> None:
    """Test error handling with YAML via stdin."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (
        b"",
        b"Error from server (Invalid): error validating data: unknown "
        b'field "spec.container"',
    )
    mock_proc.returncode = 1
    mock_popen.return_value = mock_proc

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, "invalid yaml")

    assert isinstance(result, Error)
    assert "Error from server (Invalid)" in result.error
    assert result.halt_auto_loop is False  # This specific error is recoverable


@patch("subprocess.Popen")
def test_run_kubectl_with_yaml_stdin_timeout(mock_popen: MagicMock) -> None:
    """Test timeout handling with YAML via stdin."""
    mock_proc = MagicMock()
    mock_proc.communicate.side_effect = subprocess.TimeoutExpired(
        cmd="kubectl apply", timeout=30
    )
    mock_proc.kill = MagicMock()
    mock_popen.return_value = mock_proc

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Error)
    # Update assertion to match the wrapped error message
    expected_error_substring = (
        "Error executing YAML command: Command 'kubectl apply' timed "
        "out after 30 seconds"
    )
    assert expected_error_substring in result.error
    assert isinstance(result.exception, subprocess.TimeoutExpired)
    mock_proc.kill.assert_called_once()  # Verify kill was called
    assert result.halt_auto_loop is True  # Timeouts should halt


@patch("subprocess.run")
@patch("tempfile.NamedTemporaryFile")
@patch("os.unlink")
@patch("os.path.exists", return_value=True)
def test_run_kubectl_with_yaml_file_success(
    mock_exists: MagicMock,
    mock_unlink: MagicMock,
    mock_tempfile: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Test successful execution with YAML via temp file."""
    mock_file = MagicMock()
    mock_file.__enter__.return_value.name = "/tmp/fake_temp_file.yaml"
    mock_tempfile.return_value = mock_file

    mock_run_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_run_result.returncode = 0
    mock_run_result.stdout = "pod/test-pod created"
    mock_run_result.stderr = ""
    mock_run.return_value = mock_run_result

    args = ["create"]  # Command doesn't include -f
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Success)
    assert result.data == "pod/test-pod created"
    mock_tempfile.assert_called_once_with(mode="w", suffix=".yaml", delete=False)
    mock_run.assert_called_once()
    called_args = mock_run.call_args[0][0]
    assert called_args == ["kubectl", "create", "-f", "/tmp/fake_temp_file.yaml"]
    mock_exists.assert_called_once_with("/tmp/fake_temp_file.yaml")
    mock_unlink.assert_called_once_with("/tmp/fake_temp_file.yaml")


@patch("subprocess.run")
@patch("tempfile.NamedTemporaryFile")
@patch("os.unlink")
@patch("os.path.exists", return_value=True)
def test_run_kubectl_with_yaml_file_f_already_present(
    mock_exists: MagicMock,
    mock_unlink: MagicMock,
    mock_tempfile: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Test YAML via temp file when -f argument is already present (not '-f -')."""
    mock_file = MagicMock()
    mock_file.__enter__.return_value.name = "/tmp/dummy_temp.yaml"
    mock_tempfile.return_value = mock_file

    mock_run_result = MagicMock(
        spec=subprocess.CompletedProcess, returncode=0, stdout="Success"
    )
    mock_run.return_value = mock_run_result

    # Args already include -f pointing somewhere else
    args = ["apply", "-f", "existing_file.yaml"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Success)
    mock_run.assert_called_once()
    # Verify original args were used, no temp file added to command
    called_args = mock_run.call_args[0][0]
    assert called_args == ["kubectl", "apply", "-f", "existing_file.yaml"]
    # Verify temp file was still created and cleaned up
    mock_tempfile.assert_called_once()
    mock_exists.assert_called_once_with("/tmp/dummy_temp.yaml")
    mock_unlink.assert_called_once_with("/tmp/dummy_temp.yaml")


@patch("subprocess.run")
@patch("tempfile.NamedTemporaryFile")
@patch("os.unlink")
@patch("os.path.exists", return_value=True)
def test_run_kubectl_with_yaml_file_error(
    mock_exists: MagicMock,
    mock_unlink: MagicMock,
    mock_tempfile: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Test error handling with YAML via temp file."""
    mock_file = MagicMock()
    mock_file.__enter__.return_value.name = "/tmp/err_temp.yaml"
    mock_tempfile.return_value = mock_file

    mock_run_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_run_result.returncode = 1
    mock_run_result.stdout = ""
    mock_run_result.stderr = (
        "Error from server (BadRequest): invalid request"  # Halting error
    )
    mock_run.return_value = mock_run_result

    args = ["create"]
    result = run_kubectl_with_yaml(args, "bad yaml")

    assert isinstance(result, Error)
    assert "Error from server (BadRequest)" in result.error
    # This error matches a recoverable pattern in create_kubectl_error
    assert result.halt_auto_loop is False
    mock_exists.assert_called_once_with("/tmp/err_temp.yaml")
    mock_unlink.assert_called_once_with("/tmp/err_temp.yaml")  # Cleanup still happens


@patch("subprocess.run")
@patch("tempfile.NamedTemporaryFile")
@patch("os.unlink")
@patch("os.path.exists", return_value=False)  # Simulate file not existing for cleanup
def test_run_kubectl_with_yaml_file_cleanup_no_exist(
    mock_exists: MagicMock,
    mock_unlink: MagicMock,
    mock_tempfile: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Test cleanup logic when temp file doesn't exist."""
    mock_file = MagicMock()
    mock_file.__enter__.return_value.name = "/tmp/already_gone.yaml"
    mock_tempfile.return_value = mock_file

    mock_run_result = MagicMock(
        spec=subprocess.CompletedProcess, returncode=0, stdout="Created"
    )
    mock_run.return_value = mock_run_result

    args = ["create"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Success)
    mock_exists.assert_called_once_with("/tmp/already_gone.yaml")
    mock_unlink.assert_not_called()  # Unlink shouldn't be called if exists is false


@patch("re.sub")
def test_run_kubectl_with_yaml_general_exception(mock_re_sub: MagicMock) -> None:
    """Test handling of a general exception during YAML processing."""
    mock_re_sub.side_effect = ValueError("Unexpected regex issue")

    args = ["apply", "-f", "-"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Error)
    assert "Error executing YAML command: Unexpected regex issue" in result.error
    assert isinstance(result.exception, ValueError)
    assert result.halt_auto_loop is True


@patch("subprocess.run")
@patch("tempfile.NamedTemporaryFile")
@patch("os.unlink", side_effect=OSError("Permission denied"))
@patch("os.path.exists", return_value=True)
def test_run_kubectl_with_yaml_file_cleanup_error(
    mock_exists: MagicMock,
    mock_unlink: MagicMock,
    mock_tempfile: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Test cleanup error handling (e.g., unlink fails)."""
    mock_file = MagicMock()
    mock_file.__enter__.return_value.name = "/tmp/perm_denied.yaml"
    mock_tempfile.return_value = mock_file

    mock_run_result = MagicMock(
        spec=subprocess.CompletedProcess, returncode=0, stdout="Created"
    )
    mock_run.return_value = mock_run_result

    args = ["create"]
    result = run_kubectl_with_yaml(args, TEST_YAML_CONTENT)

    assert isinstance(result, Success)  # Command itself succeeded
    assert result.data == "Created"
    mock_exists.assert_called_once_with("/tmp/perm_denied.yaml")
    mock_unlink.assert_called_once_with("/tmp/perm_denied.yaml")
    # Warning should be logged, but test passes if command succeeded


# --- Tests for create_async_kubectl_process ---


@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_success(
    mock_create_subprocess: AsyncMock,
) -> None:
    """Test successful creation of an async kubectl process."""
    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_create_subprocess.return_value = mock_process

    args = ["get", "pods", "--watch"]
    process = await create_async_kubectl_process(args)

    assert process is mock_process
    mock_create_subprocess.assert_awaited_once_with(
        "kubectl",  # First arg is the command itself
        "get",
        "pods",
        "--watch",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_with_kubeconfig(
    mock_create_subprocess: AsyncMock, test_config: Config
) -> None:
    """Test async process creation includes kubeconfig when set."""
    test_config.set("kubeconfig", "/async/kube.config")
    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_create_subprocess.return_value = mock_process

    args = ["logs", "my-pod", "-f"]
    await create_async_kubectl_process(args, config=test_config)

    mock_create_subprocess.assert_awaited_once_with(
        "kubectl",
        "--kubeconfig",  # Kubeconfig should come before command args here
        "/async/kube.config",
        "logs",
        "my-pod",
        "-f",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_without_kubeconfig(
    mock_create_subprocess: AsyncMock, test_config: Config
) -> None:
    """Test async process creation without kubeconfig."""
    test_config.set("kubeconfig", None)
    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_create_subprocess.return_value = mock_process

    args = ["port-forward", "svc/my-service", "8080:80"]
    await create_async_kubectl_process(args, config=test_config)

    mock_create_subprocess.assert_awaited_once_with(
        "kubectl",  # No kubeconfig args
        "port-forward",
        "svc/my-service",
        "8080:80",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@patch("asyncio.create_subprocess_exec")
async def test_create_async_kubectl_process_no_capture(
    mock_create_subprocess: AsyncMock,
) -> None:
    """Test async process creation with stdout/stderr capture disabled."""
    mock_process = AsyncMock(spec=asyncio.subprocess.Process)
    mock_create_subprocess.return_value = mock_process

    args = ["exec", "my-pod", "--", "bash"]
    await create_async_kubectl_process(args, capture_stdout=False, capture_stderr=False)

    mock_create_subprocess.assert_awaited_once_with(
        "kubectl",
        "exec",
        "my-pod",
        "--",
        "bash",
        stdout=None,  # Check capture disabled
        stderr=None,  # Check capture disabled
    )


@patch(
    "asyncio.create_subprocess_exec", side_effect=FileNotFoundError("kubectl not found")
)
async def test_create_async_kubectl_process_file_not_found(
    mock_create_subprocess: AsyncMock,
) -> None:
    """Test FileNotFoundError during async process creation."""
    with pytest.raises(
        FileNotFoundError, match="kubectl not found. Please install it."
    ):
        await create_async_kubectl_process(["get", "nodes"])


@patch("asyncio.create_subprocess_exec", side_effect=OSError("Permission denied"))
async def test_create_async_kubectl_process_other_exception(
    mock_create_subprocess: AsyncMock,
) -> None:
    """Test other exceptions during async process creation."""
    with pytest.raises(OSError, match="Permission denied"):
        await create_async_kubectl_process(["get", "secrets"])
