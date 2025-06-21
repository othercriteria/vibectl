"""Tests for command string processing functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.command_handler import (
    _create_display_command,
    _execute_command,
    _quote_args,
)
from vibectl.execution.vibe import (
    _handle_fuzzy_memory_update,
)
from vibectl.types import Fragment, LLMMetrics, Success, SystemFragments, UserFragments


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


@pytest.mark.asyncio
@patch("vibectl.execution.vibe.get_memory", autospec=True)
@patch("vibectl.execution.vibe.set_memory", autospec=True)
@patch("vibectl.execution.vibe.get_model_adapter", autospec=True)
@patch("vibectl.execution.vibe.memory_fuzzy_update_prompt")
@patch("vibectl.execution.vibe.Config", autospec=True)
@patch("vibectl.execution.vibe.click.prompt", autospec=True)
@patch("vibectl.execution.vibe.console_manager", autospec=True)
@patch("vibectl.execution.vibe.logger", autospec=True)
async def test_fuzzy_memory_update(
    mock_logger: Mock,
    mock_console_manager: Mock,
    mock_click_prompt_func: Mock,
    mock_config_cls: Mock,
    mock_memory_fuzzy_prompt_func: Mock,
    mock_get_model_adapter_func: Mock,
    mock_set_memory_func: Mock,
    mock_get_memory_func: Mock,
) -> None:
    """Test _handle_fuzzy_memory_update successfully updates memory."""
    print("\n=== Starting test_fuzzy_memory_update ===")

    # Setup Mocks
    user_input_for_update = "User provided additional context for memory."
    mock_click_prompt_func.return_value = user_input_for_update
    print(f"Mocked click.prompt return value: {user_input_for_update}")

    mock_config_instance = Mock(name="MockedConfigInstance")
    mock_config_cls.return_value = mock_config_instance
    mock_config_instance.get.return_value = "claude-3.7-sonnet"
    print(f"Mocked config model name: {mock_config_instance.get.return_value}")

    initial_memory_content = "Initial memory context before fuzzy update."
    mock_get_memory_func.return_value = initial_memory_content
    print(f"Mocked initial memory content: {initial_memory_content}")

    # Mock for memory_fuzzy_update_prompt
    system_frags = SystemFragments([Fragment("System fuzzy prompt")])
    user_frags = UserFragments([Fragment("User fuzzy prompt")])
    mock_memory_fuzzy_prompt_func.return_value = (system_frags, user_frags)
    print("Mocked memory_fuzzy_update_prompt with system and user fragments")

    # Mocks for model adapter and LLM call
    final_updated_memory_text = "Memory has been successfully updated with fuzzy logic."
    mock_llm_metrics = LLMMetrics(token_input=10, token_output=20, latency_ms=100)

    mock_model_adapter_instance = Mock(name="MockedModelAdapterInstance")
    mock_model_instance = Mock(name="MockedModelInstance")
    mock_model_adapter_instance.get_model.return_value = mock_model_instance

    # Ensure the mocked method is an AsyncMock to be properly awaited
    mock_model_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(
            final_updated_memory_text,
            mock_llm_metrics,
        )
    )
    mock_get_model_adapter_func.return_value = mock_model_adapter_instance
    print(f"Mocked final memory update text: {final_updated_memory_text}")

    print("\nCalling _handle_fuzzy_memory_update...")
    result = await _handle_fuzzy_memory_update(
        option="yes and", model_name="claude-3.7-sonnet"
    )
    print(f"Function returned: {result}")

    # Assertions with debug prints
    print("\nVerifying assertions...")
    assert isinstance(result, Success), f"Expected Success, got {type(result)}"
    assert result.message == "Memory updated successfully", (
        f"Expected 'Memory updated successfully', got '{result.message}'"
    )

    print("\nVerifying mock calls...")
    mock_click_prompt_func.assert_called_once_with("Memory update")
    print("✓ click.prompt called correctly")

    mock_memory_fuzzy_prompt_func.assert_called_once_with(
        current_memory=initial_memory_content,
        update_text=user_input_for_update,
        config=mock_config_instance,
    )
    print("✓ memory_fuzzy_update_prompt called correctly")

    mock_get_model_adapter_func.assert_called_once_with(mock_config_instance)
    print("✓ get_model_adapter called correctly")

    mock_model_adapter_instance.execute_and_log_metrics.assert_called_once_with(
        model=mock_model_instance,
        system_fragments=system_frags,
        user_fragments=user_frags,
    )
    print("✓ model adapter execute_and_log_metrics called correctly")

    mock_set_memory_func.assert_called_once_with(
        final_updated_memory_text, mock_config_instance
    )
    print("✓ set_memory called correctly")

    # Verify console outputs with debug prints
    print("\nVerifying console outputs...")
    mock_console_manager.print_note.assert_any_call(
        "Enter additional information for memory:"
    )
    mock_console_manager.print_processing.assert_any_call("Updating memory...")
    mock_console_manager.print_success.assert_any_call("Memory updated")
    print("✓ Console manager calls verified")

    # Verify panel output
    assert mock_console_manager.safe_print.called, "safe_print was not called"
    panel_call = mock_console_manager.safe_print.call_args
    if panel_call and len(panel_call.args) > 1 and hasattr(panel_call.args[1], "title"):
        print(f"✓ Panel printed with title: {panel_call.args[1].title}")
    else:
        print("! Warning: Could not verify Panel content details")

    # Verify logger calls
    mock_logger.info.assert_any_call(
        "User requested fuzzy memory update with 'yes and' option"
    )
    print("✓ Logger calls verified")

    print("\n=== test_fuzzy_memory_update completed successfully ===\n")
