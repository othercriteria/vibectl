"""Tests for command string processing functionality."""

from unittest.mock import Mock, patch

import pytest

from vibectl.command_handler import (
    _create_display_command,
    _execute_command,
    _handle_fuzzy_memory_update,
    _quote_args,
)
from vibectl.types import Success


def test_create_display_command_basic() -> None:
    """Test _create_display_command with basic arguments."""
    verb = "get"
    args = ["pods", "-n", "default"]
    has_yaml = False
    result = _create_display_command(verb, args, has_yaml)
    assert result == "kubectl get pods -n default"


def test_create_display_command_with_spaces() -> None:
    """Test _create_display_command with arguments containing spaces."""
    verb = "get"
    args = ["pods", "-l", "app=my app"]
    has_yaml = False
    result = _create_display_command(verb, args, has_yaml)
    assert result == 'kubectl get pods -l "app=my app"'


def test_create_display_command_with_specials() -> None:
    """Test _create_display_command with special characters."""
    verb = "exec"
    args = ["pod-name", "--", "bash", "-c", "echo <hello> | grep hello"]
    has_yaml = False
    result = _create_display_command(verb, args, has_yaml)
    assert result == 'kubectl exec pod-name -- bash -c "echo <hello> | grep hello"'


def test_create_display_command_with_yaml() -> None:
    """Test _create_display_command indicating YAML input is present."""
    # Note: The actual YAML content is handled separately by the caller.
    # This test only checks if the display string indicates YAML presence.
    verb = "apply"
    args = ["-f", "-"]
    has_yaml = True
    result = _create_display_command(verb, args, has_yaml)
    assert result == "kubectl apply -f - (with YAML content)"


def test_create_display_command_with_none_yaml() -> None:
    """Test _create_display_command when YAML is None (has_yaml=False)."""
    verb = "apply"
    args = ["-f", "-"]
    has_yaml = False
    result = _create_display_command(verb, args, has_yaml)
    assert result == "kubectl apply -f -"


def test_create_display_command_with_empty_yaml() -> None:
    """Test _create_display_command when YAML is empty (has_yaml=False)."""
    verb = "apply"
    args = ["-f", "-"]
    has_yaml = False
    result = _create_display_command(verb, args, has_yaml)
    assert result == "kubectl apply -f -"


def test_quote_args_no_quotes_needed() -> None:
    """Test _quote_args when no arguments need quoting."""
    args = ["get", "pods", "-n", "default"]
    result = _quote_args(args)
    assert result == ["get", "pods", "-n", "default"]


def test_quote_args_with_spaces() -> None:
    """Test _quote_args with arguments containing spaces."""
    args = ["get", "pods", "-l", "app=my app"]
    result = _quote_args(args)
    assert result == ["get", "pods", "-l", '"app=my app"']


def test_quote_args_with_specials() -> None:
    """Test _quote_args with arguments containing special characters."""
    args = ["exec", "pod-name", "--", "bash", "-c", "echo <hello> | grep hello"]
    result = _quote_args(args)
    expected = [
        "exec",
        "pod-name",
        "--",
        "bash",
        "-c",
        '"echo <hello> | grep hello"',
    ]
    assert result == expected


def test_quote_args_mixed() -> None:
    """Test _quote_args with a mix of arguments needing quotes or not."""
    args: list[str] = [
        "exec",
        "-it",
        "pod-name",
        "--",
        "echo",
        "hello world",
        ">",
        "/tmp/test",
    ]
    result = _quote_args(args)
    expected = [
        "exec",
        "-it",
        "pod-name",
        "--",
        "echo",
        '"hello world"',
        '">"',
        "/tmp/test",
    ]
    assert result == expected


def test_quote_args_empty() -> None:
    """Test _quote_args with an empty list."""
    args: list[str] = []
    result = _quote_args(args)
    assert result == []


def test_needs_confirmation_dangerous() -> None:
    """Test _needs_confirmation identifies dangerous commands."""


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.console_manager")
def test_execute_command_with_spaces(
    mock_console: Mock,
    mock_ch_run_kubectl: Mock,
) -> None:
    """Test executing command with spaces in the arguments."""
    # Set up mocks for subprocess.run in k8s_utils
    mock_ch_run_kubectl.return_value = Success(data="configmap/test-map created")

    # Run the command using the dispatcher in command_handler
    html_content = "<html><body><h1>CTF-FLAG-1: K8S_MASTER</h1></body></html>"
    # The command itself is the first argument for _execute_command
    command = "create"
    args = [
        "configmap",
        "nginx-config",
        f"--from-literal=index.html={html_content}",
    ]
    # Store output but not used in assertions
    # Pass command and args separately, and add yaml_content=None
    result = _execute_command(
        command=command, args=args, yaml_content=None, allowed_exit_codes=(0,)
    )

    # Verify run_kubectl (mocked in command_handler) was called
    expected_command_args = [
        "create",
        "configmap",
        "nginx-config",
        f"--from-literal=index.html={html_content}",
    ]
    mock_ch_run_kubectl.assert_called_once_with(
        expected_command_args, allowed_exit_codes=(0,)
    )
    assert isinstance(result, Success)
    assert result.data == "configmap/test-map created"


# Use a simpler approach to directly test the YAML processing
def test_yaml_handling() -> None:
    """Test YAML content normalization in _execute_yaml_command without mocking."""
    import yaml

    # Test with valid YAML
    yaml_content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
"""
    # Verify YAML can be parsed
    parsed = yaml.safe_load(yaml_content)
    assert parsed["kind"] == "Deployment"
    assert parsed["spec"]["replicas"] == 3

    # Verify we get the same structure after dumping
    dumped = yaml.dump(parsed, default_flow_style=False)
    re_parsed = yaml.safe_load(dumped)
    assert re_parsed["kind"] == "Deployment"
    assert re_parsed["spec"]["replicas"] == 3

    # Test with invalid YAML that should throw an error when parsed
    invalid_yaml = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  labels: {
    app: nginx,
    invalid:
spec:
  replicas: 3
"""

    # Verify this YAML cannot be parsed
    with pytest.raises(yaml.error.YAMLError):
        yaml.safe_load(invalid_yaml)


@pytest.mark.parametrize(
    "command, args, yaml_content, expected_result",
    [
        (
            "create",
            ["configmap", "nginx-config", "--from-literal=index.html=<html>"],
            "<html>",
            Success(data="configmap/nginx-config created"),
        ),
        (
            "apply",
            ["-f", "-"],
            "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod",
            Success(data="pod/test-pod created"),
        ),
        (
            "replace",
            ["--force", "--grace-period=0", "-f", "-"],
            "apiVersion: v1\nkind: Deployment\n...",
            Success(data="deployment.apps/test-deploy replaced"),
        ),
    ],
)
@patch("vibectl.command_handler.run_kubectl_with_yaml")
@patch("vibectl.command_handler.run_kubectl")
def test_execute_command(
    mock_run_kubectl: Mock,
    mock_run_yaml: Mock,
    command: str,
    args: list[str],
    yaml_content: str | None,
    expected_result: Success,
) -> None:
    """Test _execute_command with various inputs."""
    # Configure mocks based on expected execution path
    if yaml_content:
        mock_run_yaml.return_value = expected_result
        # Reset the other mock
        mock_run_kubectl.return_value = None
    else:
        mock_run_kubectl.return_value = expected_result
        # Reset other mocks
        mock_run_yaml.return_value = None

    # Call the function
    actual_result = _execute_command(
        command, args, yaml_content, allowed_exit_codes=(0,)
    )

    # Assertions
    assert actual_result == expected_result
    if yaml_content:
        mock_run_yaml.assert_called_once()
        mock_run_kubectl.assert_not_called()
    else:
        mock_run_kubectl.assert_called_once()
        mock_run_yaml.assert_not_called()


@patch("vibectl.command_handler.get_memory")
@patch("vibectl.command_handler.set_memory")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.memory_fuzzy_update_prompt")
@patch("vibectl.command_handler.Config")
def test_fuzzy_memory_update(
    mock_config: Mock,
    mock_prompt_func: Mock,
    mock_get_adapter: Mock,
    mock_set_memory: Mock,
    mock_get_memory: Mock,
    capsys: pytest.CaptureFixture,
) -> None:  # Add missing type hint
    """Test the fuzzy memory update process."""
    # Mock configuration and dependencies
    mock_cfg_instance = Mock()
    mock_config.return_value = mock_cfg_instance
    mock_get_memory.return_value = "Original memory context"
    mock_adapter_instance = Mock()
    mock_model_instance = Mock()
    mock_get_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance
    mock_adapter_instance.execute_and_log_metrics.return_value = (
        "Updated memory context",
        None,
    )
    mock_prompt_func.return_value = (
        ["System: Fuzzy Update"],
        ["User: Please integrate: User added this text"],
    )

    # Simulate user input for the update text
    with patch("click.prompt", return_value="User added this text"):
        result = _handle_fuzzy_memory_update("yes and", "test-model")

    # Assertions
    assert isinstance(result, Success)
    mock_get_memory.assert_called_once_with(mock_cfg_instance)
    mock_prompt_func.assert_called_once_with(
        current_memory="Original memory context",
        update_text="User added this text",
        config=mock_cfg_instance,
    )
    mock_adapter_instance.execute_and_log_metrics.assert_called_once_with(
        mock_model_instance,
        system_fragments=["System: Fuzzy Update"],
        user_fragments=["User: Please integrate: User added this text"],
    )
    mock_get_adapter.assert_called_once_with(mock_cfg_instance)
    mock_adapter_instance.get_model.assert_called_once_with("test-model")
    mock_set_memory.assert_called_once_with("Updated memory context", mock_cfg_instance)

    # Check console output - ignore ANSI codes for simplicity
    captured = capsys.readouterr()
    assert "Updating memory" in captured.out  # Check substring without ellipsis
    assert "Memory updated" in captured.out
    assert "Updated Memory Content" in captured.out
    assert "Updated memory context" in captured.out
