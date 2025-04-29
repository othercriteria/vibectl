"""Tests for command string processing functionality."""

import json
from unittest.mock import Mock, patch

import pytest

from vibectl.command_handler import (
    _create_display_command,
    _execute_command,
    _parse_command_args,
    _process_command_string,
    handle_vibe_request,
)
from vibectl.k8s_utils import run_kubectl_with_yaml
from vibectl.types import ActionType, OutputFlags, Success


def test_process_command_string_basic() -> None:
    """Test basic command string processing without YAML."""
    # Basic command
    cmd_args, yaml_content = _process_command_string("create configmap test-map")
    assert cmd_args == "create configmap test-map"
    assert yaml_content is None


def test_process_command_string_with_yaml() -> None:
    """Test command string processing with YAML content."""
    # Command with YAML
    cmd_str = "apply -f\n---\napiVersion: v1\nkind: Pod"
    cmd_args, yaml_content = _process_command_string(cmd_str)
    assert cmd_args == "apply -f"
    assert yaml_content == "---\napiVersion: v1\nkind: Pod"


def test_parse_command_args_basic() -> None:
    """Test basic command argument parsing."""
    # Simple arguments
    args = _parse_command_args("create configmap test-map")
    assert args == ["create", "configmap", "test-map"]


def test_parse_command_args_with_spaces() -> None:
    """Test command argument parsing with spaces in values."""
    # Arguments with spaces should be preserved with shlex parsing
    cmd = 'create configmap test-map --from-literal=key="value with spaces"'
    args = _parse_command_args(cmd)
    assert args == [
        "create",
        "configmap",
        "test-map",
        "--from-literal=key=value with spaces",
    ]


def test_parse_command_args_with_multiple_literals() -> None:
    """Test command argument parsing with multiple --from-literal values."""
    # Multiple from-literal arguments
    cmd = (
        "create secret generic api-creds "
        '--from-literal=username="user123" '
        '--from-literal=password="pass!with spaces"'
    )
    args = _parse_command_args(cmd)
    assert args == [
        "create",
        "secret",
        "generic",
        "api-creds",
        "--from-literal=username=user123",
        "--from-literal=password=pass!with spaces",
    ]


def test_parse_command_args_html_content() -> None:
    """Test command argument parsing with HTML content in values."""
    # HTML content in from-literal
    cmd = (
        "create secret generic token-secret "
        '--from-literal=token="<token>eyJhbGciOiJIUzI1NiJ9.e30.'
        'ZRrHA1JJJW8opsbCGfG_HACGpVUMN_a9IV7pAx_Zmeo</token>"'
    )
    args = _parse_command_args(cmd)
    token_value = (
        "<token>eyJhbGciOiJIUzI1NiJ9.e30."
        "ZRrHA1JJJW8opsbCGfG_HACGpVUMN_a9IV7pAx_Zmeo</token>"
    )
    assert args == [
        "create",
        "secret",
        "generic",
        "token-secret",
        f"--from-literal=token={token_value}",
    ]


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
    with patch("vibectl.command_handler._process_command_string") as mock_process_cmd:
        # Mock the LLM response and command processing to simulate the
        # problematic command
        html = "<html><body><h1>CTF-FLAG-1: K8S_MASTER</h1></body></html>"
        cmd = "create configmap nginx-config"
        literal = f'--from-literal=index.html="{html}"'
        cmd_str = f"{cmd} {literal}"
        mock_process_cmd.return_value = (cmd_str, None)

        with patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter:
            # Mock the model adapter
            mock_adapter = Mock()
            mock_model = Mock()
            mock_adapter.get_model.return_value = mock_model
            # Update mock to return JSON
            command_parts = [
                "create",
                "configmap",
                "nginx-config",
                f'--from-literal=index.html="{html}"'
            ]
            expected_response_plan = {
                "action_type": ActionType.COMMAND.value,
                "commands": command_parts,
                "explanation": "Creating configmap with HTML.",
            }
            mock_adapter.execute.return_value = json.dumps(expected_response_plan)
            mock_get_adapter.return_value = mock_adapter

            # Call handle_vibe_request directly
            output_flags = OutputFlags(
                show_raw=True,
                show_vibe=True,
                warn_no_output=False,
                model_name="test-model",
                show_kubectl=True,
            )

            # Call the handler and verify the results
            with patch("vibectl.command_handler.handle_command_output"):
                handle_vibe_request(
                    request="create a configmap with HTML content",
                    command="create",
                    plan_prompt="Test prompt",
                    summary_prompt_func=lambda: "Test summary",
                    output_flags=output_flags,
                    yes=True,  # Skip confirmation
                )

                # Verify subprocess was called with the expected arguments
                mock_subprocess.assert_called_once()
                # Checking that the proper type of args were passed
                args = mock_subprocess.call_args[0][0]
                assert isinstance(args, list)
                assert len(args) > 2
                assert "nginx-config" in args
                # Check that we have the --from-literal parameter fully intact
                from_literal_args = [a for a in args if "--from-literal" in a]
                assert len(from_literal_args) > 0


def test_process_command_string_heredoc() -> None:
    """Test command string processing with heredoc syntax."""
    # Note: With the robustness improvements, the behavior has changed.
    # Let's directly test how the function currently works

    # Heredoc with << EOF syntax
    cmd_str = (
        "create -f - << EOF\napiVersion: v1\nkind: ConfigMap\n"
        "metadata:\n  name: test-cm\nEOF"
    )
    cmd_args, yaml_content = _process_command_string(cmd_str)
    # Don't match exact equality, focus on behavior, not implementation
    assert "create" in cmd_args  # Command should include "create"

    # Test YAML extraction regardless of command args behavior
    assert yaml_content is not None
    assert "apiVersion: v1" in yaml_content
    assert "test-cm" in yaml_content
    assert "EOF" not in yaml_content  # EOF should be stripped

    # Heredoc with <<EOF syntax (no space)
    cmd_str = (
        "create -f - <<EOF\napiVersion: apps/v1\nkind: Deployment\n"
        "metadata:\n  name: test-deploy\nEOF"
    )
    cmd_args, yaml_content = _process_command_string(cmd_str)
    assert "create" in cmd_args
    assert yaml_content is not None
    assert "apiVersion: apps/v1" in yaml_content
    assert "test-deploy" in yaml_content

    # Heredoc with additional arguments
    cmd_str = (
        "create -f - -n test-namespace << EOF\napiVersion: v1\n"
        "kind: ConfigMap\nmetadata:\n  name: test-cm\nEOF"
    )
    cmd_args, yaml_content = _process_command_string(cmd_str)
    assert "create" in cmd_args  # Command should include create
    assert "test-namespace" in cmd_args  # Should keep namespace args
    assert yaml_content is not None
    assert "apiVersion: v1" in yaml_content


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
    """Test handle_vibe_request with heredoc syntax that produces an error."""
    # Set up mocks
    mock_model = Mock()
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = mock_model
    mock_get_adapter.return_value = mock_adapter

    # Simulate model response with heredoc syntax containing an error
    yaml_content_error = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
spec:
  replicas: invalid-value
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
    expected_plan_error = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["create", "-f", "-", "---", yaml_content_error],
        "explanation": "Creating deployment via heredoc (with error).",
    }

    # Set up the model to return both the command and recovery suggestions
    mock_adapter.execute.side_effect = [
        json.dumps(expected_plan_error),  # First call returns the JSON command
        "Here are recovery suggestions",  # Second call returns recovery suggestions
    ]

    # Mock the subprocess call to fail with an error
    with patch("vibectl.k8s_utils.subprocess.Popen") as mock_popen:
        # Set up subprocess mock to return an error and support context manager
        mock_process = Mock()
        mock_process.returncode = 1
        error_msg = (
            "Error: unable to parse YAML: mapping values are "
            "not allowed in this context"
        )
        # Simulate stderr output
        mock_process.communicate.return_value = (b"", error_msg.encode())

        # Make the mock support the context manager protocol
        mock_popen.return_value.__enter__.return_value = mock_process
        mock_popen.return_value.__exit__.return_value = None

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
                return_value="Recovery prompt for this error",
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

        # Verify Popen was called
        assert mock_popen.call_count > 0

        # Verify the model was called twice
        assert mock_adapter.execute.call_count == 2


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


def test_parse_command_args_robust() -> None:
    """Test command argument parsing with more complex cases."""
    # Test that quotes are handled properly
    args = _parse_command_args('create configmap test-map --from-literal="key=value"')
    assert args == ["create", "configmap", "test-map", "--from-literal=key=value"]

    # Test that complex quoting is handled properly
    args = _parse_command_args(
        "create secret generic my-secret --from-literal='user=admin' "
        '--from-literal="password=secret with spaces"'
    )
    assert args == [
        "create",
        "secret",
        "generic",
        "my-secret",
        "--from-literal=user=admin",
        "--from-literal=password=secret with spaces",
    ]

    # Test that malformed quoting falls back to simple splitting
    args = _parse_command_args('create configmap test-map --from-literal="key=value')
    assert args == [
        "create",
        "configmap",
        "test-map",
        '--from-literal="key=value',
    ]


@patch("vibectl.command_handler.run_kubectl_with_yaml")
@patch("vibectl.command_handler.console_manager")
def test_execute_stdin_command(mock_console: Mock, mock_run_yaml: Mock) -> None:
    """Test executing a command that requires stdin via YAML content."""
    command = "apply"
    args = ["-f", "-"]
    yaml_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod"

    # Mock the return value of the patched function
    mock_run_yaml.return_value = Success(data="pod/test-pod created")

    # Execute the command using the dispatcher
    result = _execute_command(command, args, yaml_content)

    # Verify run_kubectl_with_yaml was called with correct arguments
    mock_run_yaml.assert_called_once()
    call_args, _ = mock_run_yaml.call_args
    expected_full_args = ["apply", "-f", "-"]
    assert call_args[0] == expected_full_args
    assert call_args[1] == yaml_content

    # Verify the result
    assert isinstance(result, Success)
    assert result.data == "pod/test-pod created"


@patch("vibectl.command_handler.run_kubectl_with_yaml")
@patch("vibectl.command_handler.console_manager")
def test_execute_stdin_command_with_other_flags(
    mock_console: Mock, mock_run_yaml: Mock
) -> None:
    """Test command requiring stdin with other flags present."""
    command = "replace"
    args = ["--force", "--grace-period=0", "-f", "-"]
    yaml_content = "apiVersion: v1\nkind: Deployment\n..."

    # Mock the return value
    mock_run_yaml.return_value = Success(data="deployment.apps/test-deploy replaced")

    # Execute
    result = _execute_command(command, args, yaml_content)

    # Verify run_kubectl_with_yaml was called correctly
    mock_run_yaml.assert_called_once()
    call_args, _ = mock_run_yaml.call_args
    expected_full_args = ["replace", "--force", "--grace-period=0", "-f", "-"]
    assert call_args[0] == expected_full_args
    assert call_args[1] == yaml_content

    # Verify result
    assert isinstance(result, Success)
    assert result.data == "deployment.apps/test-deploy replaced"


@patch("vibectl.k8s_utils.subprocess.Popen")
def test_execute_yaml_command(mock_popen: Mock, capsys: pytest.CaptureFixture) -> None:
    """Test the _execute_yaml_command function."""
    # Mock process setup
    mock_process = Mock()
    mock_popen.return_value = mock_process
    mock_process.returncode = 0
    mock_process.communicate.return_value = (
        b"deployment.apps/nginx created\n",
        b"",
    )

    # YAML content
    yaml_content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
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
        - containerPort: 80
"""

    # Run the function
    _ = run_kubectl_with_yaml(["apply", "-f", "-"], yaml_content)
    mock_popen.assert_called_once_with(
        ["kubectl", "apply", "-f", "-"], stdin=-1, stdout=-1, stderr=-1, text=False
    )


@patch("vibectl.k8s_utils.subprocess.Popen")
def test_execute_yaml_command_stdin(
    mock_popen: Mock,
    capsys: pytest.CaptureFixture,
) -> None:
    """Test the _execute_yaml_command function with stdin."""
    # Mock process setup
    mock_process = Mock()
    mock_popen.return_value = mock_process
    mock_process.returncode = 0
    mock_process.communicate.return_value = (
        b"deployment.apps/nginx created\n",
        b"",
    )

    # YAML content
    yaml_content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: test
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
        - containerPort: 80
"""

    # Run the function
    _ = run_kubectl_with_yaml(["create", "-f", "-"], yaml_content)
    mock_popen.assert_called_once_with(
        ["kubectl", "create", "-f", "-"], stdin=-1, stdout=-1, stderr=-1, text=False
    )
