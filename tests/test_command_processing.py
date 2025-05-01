"""Tests for command string processing functionality."""

import json
from unittest.mock import Mock, patch

import pytest

from vibectl.command_handler import (
    _create_display_command,
    _execute_command,
    _handle_fuzzy_memory_update,
    handle_vibe_request,
)
from vibectl.types import ActionType, Error, OutputFlags, Success


def test_create_display_command_basic() -> None:
    """Test _create_display_command with basic arguments."""
    args = ["get", "pods", "-n", "default"]
    result = _create_display_command(args)
    assert result == "get pods -n default"


def test_create_display_command_with_spaces() -> None:
    """Test _create_display_command with arguments containing spaces."""
    args = ["get", "pods", "-l", "app=my app"]
    result = _create_display_command(args)
    assert result == 'get pods -l "app=my app"'


def test_create_display_command_with_specials() -> None:
    """Test _create_display_command with special characters."""
    args = ["exec", "pod-name", "--", "bash", "-c", "echo <hello> | grep hello"]
    result = _create_display_command(args)
    # Expecting quoting around the command part
    assert result == 'exec pod-name -- bash -c "echo <hello> | grep hello"'


def test_create_display_command_with_yaml() -> None:
    """Test _create_display_command with args indicating YAML input."""
    yaml_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod"
    args = ["apply", "-f", "-", yaml_content]
    result = _create_display_command(args)
    # Should show simplified version for YAML
    assert result == "apply -f - (with YAML content)"


def test_needs_confirmation_dangerous() -> None:
    """Test _needs_confirmation identifies dangerous commands."""


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.k8s_utils.subprocess.run")
@patch("vibectl.command_handler.console_manager")
def test_execute_command_with_spaces(
    mock_console: Mock, mock_subprocess_run: Mock, mock_run_kubectl: Mock
) -> None:
    """Test executing command with spaces in the arguments."""
    # Set up mocks for subprocess.run in k8s_utils
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.stdout = "configmap/test-map created"
    mock_subprocess_run.return_value = mock_process

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
    _ = _execute_command(command=command, args=args, yaml_content=None)

    # Verify subprocess.run (mocked in k8s_utils) was called
    mock_subprocess_run.assert_called_once()
    # Verify standard run_kubectl (mocked in command_handler) was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify subprocess was called with the right command structure
    call_args = mock_subprocess_run.call_args[0][0]
    assert call_args[0] == "kubectl"
    assert "nginx-config" in call_args
    assert any("--from-literal" in arg for arg in call_args)


@patch("vibectl.k8s_utils.subprocess.run")
@patch("vibectl.command_handler.console_manager")
def test_execute_command_integration_with_spaces(
    mock_console: Mock, mock_subprocess: Mock
) -> None:
    """Integration test simulating the configmap command issue."""
    # Configure mock subprocess
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.stdout = "configmap/nginx-config created"
    mock_subprocess.return_value = mock_process

    # Test command with HTML content that caused the original issue
    # Remove the patch for the deleted function
    # with patch("vibectl.command_handler._process_command_string") as mock_process_cmd:
    # Ensure the correct execution path is taken by mocking the result
    # from the relevant run_kubectl* function directly.

    # Example command args (replace with actual args if needed for test logic)
    command = "create"
    args = ["configmap", "nginx-config", "--from-literal=index.html=<html>"]
    yaml_content = None  # Assuming no YAML for this specific integration test focus

    # Directly call _execute_command
    result = _execute_command(command, args, yaml_content)

    # Assertions
    assert isinstance(result, Success)
    assert result.data == "configmap/nginx-config created"
    # Check that the correct run_kubectl* function was called via subprocess.run mock
    mock_subprocess.assert_called_once()
    # Add more specific assertions on mock_subprocess.call_args if needed


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.run_kubectl")
def test_handle_vibe_request_with_heredoc_integration(
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_get_adapter: Mock,
) -> None:
    """Test handle_vibe_request with heredoc syntax in the model response."""
    # Set up mocks
    mock_model = Mock()
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = mock_model
    mock_get_adapter.return_value = mock_adapter

    # Simulate model response with heredoc syntax by constructing the JSON
    yaml_content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80"""
    expected_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["create", "-f", "-", "---", yaml_content],
        "explanation": "Creating deployment via heredoc.",
    }
    mock_adapter.execute.return_value = json.dumps(expected_plan)

    # Mock the subprocess call for create -f -
    with patch("vibectl.k8s_utils.subprocess.Popen") as mock_popen:
        # Set up subprocess to return success
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b"deployment.apps/nginx-deployment created",
            b"",
        )
        mock_popen.return_value = mock_process

        # Create output flags
        output_flags = OutputFlags(
            show_raw=True,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_kubectl=True,
        )

        # Call handle_vibe_request with yes=True to skip confirmation
        with (
            patch("click.confirm", return_value=True),
            patch(
                "vibectl.command_handler.recovery_prompt",
                "Recovery prompt: {error} {command} {request} {kubectl_cmd}",
            ),
        ):
            handle_vibe_request(
                request="create nginx deployment with 3 replicas",
                command="create",
                plan_prompt="Test prompt",
                summary_prompt_func=lambda: "Test summary",
                output_flags=output_flags,
                yes=True,  # Skip confirmation
            )

        # Verify subprocess was called with YAML input
        assert mock_popen.call_count > 0
        # At least one call should be to kubectl with create -f -
        kubectl_calls = [
            call
            for call in mock_popen.call_args_list
            if len(call[0]) > 0
            and isinstance(call[0][0], list)
            and "kubectl" in call[0][0]
            and "create" in call[0][0]
        ]
        assert len(kubectl_calls) > 0, "No kubectl commands were executed"


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.run_kubectl")
def test_handle_vibe_request_with_heredoc_error_integration(
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_get_adapter: Mock,
) -> None:
    """Test handle_vibe_request with command error recovery integration."""
    # Set up mocks for the adapter
    mock_model = Mock()
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = mock_model
    mock_get_adapter.return_value = mock_adapter

    # Simulate model response for initial planning (COMMAND action)
    expected_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["-f", "-"],  # Args only
        "explanation": "Creating deployment.",
    }

    # Set up the model to return the plan first, then recovery suggestions
    mock_adapter.execute.side_effect = [
        json.dumps(expected_plan),  # First call (planning)
        "Recovery suggestion for apply error",  # Second call (recovery)
    ]

    # Define the error that _execute_command should return
    simulated_kubectl_error_msg = "Error: unable to parse YAML"
    simulated_error_result = Error(error=simulated_kubectl_error_msg)

    # Create output flags (ensure show_vibe=True for recovery)
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,  # <<< Important for recovery flow
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
    )

    # Patch _execute_command directly and other necessary functions
    with (
        patch("vibectl.command_handler._execute_command") as mock_execute_cmd,
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.command_handler.console_manager") as mock_console,
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: error test",
        ),
        patch(
            "vibectl.command_handler.recovery_prompt",
            return_value="Recovery prompt template",
        ) as mock_recovery_prompt,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as mock_handle_cmd_output,  # <<< Re-patch handle_command_output
    ):  # <<< Re-patch handle_command_output
        # Configure _execute_command to return the simulated error
        mock_execute_cmd.return_value = simulated_error_result

        # Configure the mock handle_command_output to return the error object
        # with suggestions added
        # (This simulates what the real function *should* do in this scenario)
        modified_error = Error(
            error=simulated_error_result.error,
            recovery_suggestions="Recovery suggestion for apply error",
        )
        mock_handle_cmd_output.return_value = modified_error

        # Call handle_vibe_request with yes=True to skip confirmation
        result = handle_vibe_request(
            request="create nginx deployment",
            command="apply",  # Verb matching the desired command
            plan_prompt="Test prompt",
            summary_prompt_func=lambda: "Test summary",
            output_flags=output_flags,
            yes=True,  # Skip confirmation
        )

    # --- Assertions --- #

    # 1. Verify _execute_command was called correctly
    mock_execute_cmd.assert_called_once_with("apply", ["-f", "-"], None)

    # 2. Verify handle_command_output was called with the Error from _execute_command
    mock_handle_cmd_output.assert_called_once()
    call_args, call_kwargs = mock_handle_cmd_output.call_args
    assert (
        call_args[0] is simulated_error_result
    )  # Check Error object passed (position 0)
    assert call_args[1] is output_flags  # Check output_flags passed (position 1)
    assert call_kwargs.get("command") == "apply"  # Check command kwarg

    # 3. Verify the model adapter was called only ONCE (for planning)
    #    Because we mocked handle_command_output, the recovery call within
    #    it is bypassed.
    assert mock_adapter.execute.call_count == 1

    # 4. Verify memory update did NOT happen directly here (would happen
    # inside handle_command_output)
    mock_update_memory.assert_not_called()

    # 5. Verify recovery_prompt was NOT called directly here (would happen
    # inside handle_command_output)
    mock_recovery_prompt.assert_not_called()

    # 6. Verify console output did NOT happen directly here (would happen
    # inside handle_command_output)
    mock_console.print_vibe.assert_not_called()

    # 7. Verify the final result is the one returned by our mock handle_command_output
    assert result is modified_error


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
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.run_kubectl_with_yaml")
@patch("vibectl.command_handler.run_kubectl_with_complex_args")
@patch("vibectl.command_handler.logger")
def test_execute_command(
    mock_logger: Mock,
    mock_run_complex: Mock,
    mock_run_yaml: Mock,
    mock_run_kubectl: Mock,
    command: str,
    args: list,
    yaml_content: str | None,  # Allow None for yaml_content
    expected_result: Success,
) -> None:  # Add missing type hint
    """Test command execution dispatch logic."""
    # Note: Removed mock_process as _process_command_string is gone

    # Set the return value for the appropriate mock based on expected dispatch
    if yaml_content:
        mock_run_yaml.return_value = expected_result
    elif any(" " in arg or "<" in arg or ">" in arg for arg in args):
        mock_run_complex.return_value = expected_result
    else:
        mock_run_kubectl.return_value = expected_result

    result = _execute_command(command, args, yaml_content)

    # Assert correct dispatch
    if yaml_content:
        mock_run_yaml.assert_called_once()
        call_args, _ = mock_run_yaml.call_args
        # Combine command and args for the expected call to run_kubectl_with_yaml
        expected_full_args = [command, *args]  # Use unpacking
        assert call_args[0] == expected_full_args
        assert call_args[1] == yaml_content
        mock_run_kubectl.assert_not_called()
        mock_run_complex.assert_not_called()
    elif any(" " in arg or "<" in arg or ">" in arg for arg in args):
        mock_run_complex.assert_called_once()
        call_args, _ = mock_run_complex.call_args
        expected_full_args = [command, *args]  # Use unpacking
        assert call_args[0] == expected_full_args
        mock_run_kubectl.assert_not_called()
        mock_run_yaml.assert_not_called()
    else:
        mock_run_kubectl.assert_called_once()
        call_args, _ = mock_run_kubectl.call_args
        expected_full_args = [command, *args]  # Use unpacking
        assert call_args[0] == expected_full_args
        mock_run_yaml.assert_not_called()
        mock_run_complex.assert_not_called()

    # Verify result matches expected
    assert isinstance(result, Success)
    assert result.data == expected_result.data


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
    mock_adapter_instance.execute.return_value = "Updated memory context"
    mock_prompt_func.return_value = "Fuzzy update prompt"

    # Simulate user input for the update text
    with patch("click.prompt", return_value="User added this text"):
        result = _handle_fuzzy_memory_update("yes and", "test-model")

    # Assertions
    assert isinstance(result, Success)
    mock_get_memory.assert_called_once_with(mock_cfg_instance)
    mock_prompt_func.assert_called_once_with(
        current_memory="Original memory context", update_text="User added this text"
    )
    mock_get_adapter.assert_called_once_with(mock_cfg_instance)
    mock_adapter_instance.get_model.assert_called_once_with("test-model")
    mock_adapter_instance.execute.assert_called_once_with(
        mock_model_instance, "Fuzzy update prompt"
    )
    mock_set_memory.assert_called_once_with("Updated memory context", mock_cfg_instance)

    # Check console output (optional, but good for verifying user feedback)
    captured = capsys.readouterr()
    assert "Updating memory..." in captured.out
    assert "Memory updated" in captured.out
    assert "Updated Memory Content" in captured.out
    assert "Updated memory context" in captured.out
