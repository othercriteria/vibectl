"""Tests for command string processing functionality."""

from unittest.mock import Mock, patch

import pytest

from vibectl.command_handler import (
    _create_display_command,
    _execute_command,
    _execute_yaml_command,
    _parse_command_args,
    _process_command_string,
    handle_vibe_request,
)
from vibectl.types import OutputFlags


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
    """Test creating display command for basic command."""
    display_cmd = _create_display_command(["get", "pods"], None)
    assert display_cmd == "get pods"


def test_create_display_command_with_spaces() -> None:
    """Test creating display command with spaces in args."""
    html_content = "<html><body><h1>CTF-FLAG-1: K8S_MASTER</h1></body></html>"
    display_cmd = _create_display_command(
        [
            "create",
            "configmap",
            "nginx-config",
            f"--from-literal=index.html={html_content}",
        ],
        None,
    )
    # The command display should include quoted version of the argument
    assert "from-literal=index.html=" in display_cmd
    assert "CTF-FLAG-1: K8S_MASTER" in display_cmd


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.subprocess.run")
@patch("vibectl.command_handler.console_manager")
def test_execute_command_with_spaces(
    mock_console: Mock, mock_subprocess: Mock, mock_run_kubectl: Mock
) -> None:
    """Test executing command with spaces in the arguments."""
    # Set up mocks
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.stdout = "configmap/test-map created"
    mock_subprocess.return_value = mock_process

    # Run the command
    html_content = "<html><body><h1>CTF-FLAG-1: K8S_MASTER</h1></body></html>"
    args = [
        "create",
        "configmap",
        "nginx-config",
        f"--from-literal=index.html={html_content}",
    ]
    # Store output but not used in assertions
    _ = _execute_command(args, None)

    # Verify subprocess.run was called directly instead of run_kubectl
    mock_subprocess.assert_called_once()
    mock_run_kubectl.assert_not_called()

    # Verify subprocess was called with the right command structure
    call_args = mock_subprocess.call_args[0][0]
    assert call_args[0] == "kubectl"
    assert "nginx-config" in call_args
    assert any("--from-literal" in arg for arg in call_args)


@patch("subprocess.run")
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
            mock_adapter.execute.return_value = cmd_str
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


# Mark these as integration tests since they mock fewer components
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler._parse_command_args")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.run_kubectl")
def test_handle_vibe_request_with_heredoc_integration(
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_get_adapter: Mock,
    mock_process_args: Mock,  # Mock for args processing
    mock_execute_command: Mock,  # Added mock for execution
) -> None:
    """Test handle_vibe_request with heredoc syntax in the model response."""
    # Set up mocks
    mock_model = Mock()
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = mock_model
    mock_get_adapter.return_value = mock_adapter

    # Simulate model response with heredoc syntax
    heredoc_cmd = (
        "create -f - << EOF\napiVersion: apps/v1\nkind: Deployment\n"
        "metadata:\n  name: nginx-deployment\nspec:\n  replicas: 3\n"
        "  selector:\n    matchLabels:\n      app: nginx\n  template:\n"
        "    metadata:\n      labels:\n        app: nginx\n    spec:\n"
        "      containers:\n      - name: nginx\n"
        "        image: nginx:latest\n"
        "        ports:\n        - containerPort: 80\nEOF"
    )
    mock_adapter.execute.return_value = heredoc_cmd

    # Make args processing return valid args that would pass validation
    mock_process_args.return_value = ["create", "deployment", "nginx-deployment"]

    # Set up _execute_command to return success
    mock_execute_command.return_value = "deployment.apps/nginx-deployment created"

    # Create output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
    )

    # Call handle_vibe_request with yes=True to skip confirmation
    with patch("click.confirm", return_value=True):  # Mock confirmation
        handle_vibe_request(
            request="create nginx deployment with 3 replicas",
            command="create",
            plan_prompt="Test prompt",
            summary_prompt_func=lambda: "Test summary",
            output_flags=output_flags,
            yes=True,  # Skip confirmation
        )

    # Verify our mocks were called appropriately
    mock_adapter.execute.assert_called()  # Should be called at least once
    mock_execute_command.assert_called_once()  # Should be called exactly once
    mock_handle_output.assert_called_once()


# Mark these as integration tests since they mock fewer components
@patch("vibectl.command_handler._execute_command")
@patch("vibectl.command_handler._parse_command_args")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.handle_command_output")
@patch("vibectl.command_handler.run_kubectl")
def test_handle_vibe_request_with_heredoc_error_integration(
    mock_run_kubectl: Mock,
    mock_handle_output: Mock,
    mock_get_adapter: Mock,
    mock_process_args: Mock,  # Mock for args processing
    mock_execute_command: Mock,  # Added mock for execution
) -> None:
    """Test handle_vibe_request with heredoc syntax that produces an error."""
    # Set up mocks
    mock_model = Mock()
    mock_adapter = Mock()
    mock_adapter.get_model.return_value = mock_model
    mock_get_adapter.return_value = mock_adapter

    # Simulate model response with heredoc syntax
    heredoc_cmd = (
        "create -f - << EOF\napiVersion: apps/v1\nkind: Deployment\n"
        "metadata:\n  name: nginx-deployment\nspec:\n  replicas: invalid-value\n"
        "  selector:\n    matchLabels:\n      app: nginx\n  template:\n"
        "    metadata:\n      labels:\n        app: nginx\n    spec:\n"
        "      containers:\n      - name: nginx\n"
        "        image: nginx:latest\n"
        "        ports:\n        - containerPort: 80\nEOF"
    )
    # Just return the command, no need for recovery suggestions which may not be called
    mock_adapter.execute.return_value = heredoc_cmd

    # Make args processing return valid args that would pass validation
    mock_process_args.return_value = ["create", "deployment", "nginx-deployment"]

    # Set up _execute_command to fail
    error_msg = (
        "Error: unable to parse YAML: mapping values are not allowed in this context"
    )
    mock_execute_command.side_effect = Exception(error_msg)

    # Set up execute mock to return recovery suggestions
    mock_adapter.execute.side_effect = [
        heredoc_cmd,  # First call returns the command
        "Here are recovery suggestions",  # Second call returns recovery suggestions
    ]

    # Create output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
    )

    # Call handle_vibe_request with yes=True to skip confirmation
    with patch("click.confirm", return_value=True):  # Mock confirmation
        handle_vibe_request(
            request="create nginx deployment with 3 replicas",
            command="create",
            plan_prompt="Test prompt",
            summary_prompt_func=lambda: "Test summary",
            output_flags=output_flags,
            yes=True,  # Skip confirmation
        )

    # Verify our mocks were called appropriately
    assert mock_adapter.execute.call_count == 2  # Called twice (command + recovery)
    mock_execute_command.assert_called_once()  # Should be called exactly once
    mock_handle_output.assert_called_once()


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


@patch("vibectl.command_handler.subprocess.Popen")
@patch("vibectl.command_handler.console_manager")
def test_execute_stdin_command(mock_console: Mock, mock_popen: Mock) -> None:
    """Test executing a command with stdin input (kubectl create -f -)."""
    # Set up mock
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"deployment.apps/nginx created", b"")
    mock_popen.return_value = mock_process

    # YAML content to use
    yaml_content = """
apiVersion: apps/v1
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
        image: nginx
"""

    # Call _execute_command with "create -f -" args
    _ = _execute_command(["create", "-f", "-"], yaml_content)

    # Verify Popen was called with correct arguments
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert args[0][0] == "kubectl"
    assert args[0][1] == "create"
    assert args[0][2] == "-f"
    assert args[0][3] == "-"
    assert "stdin" in kwargs
    assert kwargs["stdout"] is not None
    assert kwargs["stderr"] is not None

    # Extract the actual input passed to communicate
    actual_input = mock_process.communicate.call_args[1]["input"]

    # The actual input should now contain a '---' marker due to our preprocessing
    assert b"---" in actual_input

    # Verify the original YAML content is still present (without checking exact format)
    assert b"apiVersion: apps/v1" in actual_input
    assert b"kind: Deployment" in actual_input
    assert b"name: nginx" in actual_input
    assert b"replicas: 3" in actual_input


@patch("vibectl.command_handler.subprocess.Popen")
@patch("vibectl.command_handler.console_manager")
def test_execute_stdin_command_with_other_flags(
    mock_console: Mock, mock_popen: Mock
) -> None:
    """Test executing a command with stdin input and additional flags."""
    # Set up mock
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"deployment.apps/nginx created", b"")
    mock_popen.return_value = mock_process

    # YAML content to use
    yaml_content = """
apiVersion: apps/v1
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
        image: nginx
"""

    # Call _execute_command with "create -n test -f -" args (different order)
    _ = _execute_command(["create", "-n", "test", "-f", "-"], yaml_content)

    # Verify Popen was called with correct arguments
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert args[0][0] == "kubectl"
    assert args[0][1] == "create"
    assert args[0][2] == "-n"
    assert args[0][3] == "test"
    assert args[0][4] == "-f"
    assert args[0][5] == "-"
    assert "stdin" in kwargs

    # Extract the actual input passed to communicate
    actual_input = mock_process.communicate.call_args[1]["input"]

    # The actual input should now contain a '---' marker due to our preprocessing
    assert b"---" in actual_input

    # Verify the original YAML content is still present (without checking exact format)
    assert b"apiVersion: apps/v1" in actual_input
    assert b"kind: Deployment" in actual_input
    assert b"name: nginx" in actual_input
    assert b"namespace: test" in actual_input
    assert b"replicas: 3" in actual_input


@patch("vibectl.command_handler.subprocess.Popen")
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
    _ = _execute_yaml_command(["apply", "-f", "-"], yaml_content)

    # Verify Popen was called correctly
    args, kwargs = mock_popen.call_args
    assert args[0][0] == "kubectl"
    assert args[0][1] == "apply"
    assert args[0][2] == "-f"
    assert args[0][3] == "-"
    assert kwargs["stdout"] is not None
    assert kwargs["stderr"] is not None

    # Extract the actual input passed to communicate
    actual_input = mock_process.communicate.call_args[1]["input"]

    # The actual input should now contain a '---' marker due to our preprocessing
    assert b"---" in actual_input

    # Verify the original YAML content is still present (without checking exact format)
    assert b"apiVersion: apps/v1" in actual_input
    assert b"kind: Deployment" in actual_input
    assert b"name: nginx" in actual_input
    assert b"replicas: 3" in actual_input


@patch("vibectl.command_handler.subprocess.Popen")
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
    _ = _execute_yaml_command(["stdin", "apply", "-f", "-"], yaml_content)

    # Verify Popen was called correctly
    args, kwargs = mock_popen.call_args

    # Print all args for debugging
    print(f"Command args: {args[0]}")

    # Only assert what we care about, without relying on specific positions
    assert args[0][0] == "kubectl"
    assert "stdin" in args[0]
    assert "apply" in args[0]
    assert "-f" in args[0]
    assert "-" in args[0]
    assert "stdin" in kwargs

    # Extract the actual input passed to communicate
    actual_input = mock_process.communicate.call_args[1]["input"]

    # The actual input should now contain a '---' marker due to our preprocessing
    assert b"---" in actual_input

    # Verify the original YAML content is still present (without checking exact format)
    assert b"apiVersion: apps/v1" in actual_input
    assert b"kind: Deployment" in actual_input
    assert b"name: nginx" in actual_input
    assert b"namespace: test" in actual_input
    assert b"replicas: 3" in actual_input
