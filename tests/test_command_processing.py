"""Tests for command string processing functionality."""

from unittest.mock import Mock, patch

from vibectl.command_handler import (
    _create_display_command,
    _execute_command,
    _process_command_args,
    _process_command_string,
)


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


def test_process_command_args_basic() -> None:
    """Test basic command argument processing."""
    # Simple arguments
    args = _process_command_args("create configmap test-map", "create")
    assert args == ["create", "configmap", "test-map"]


def test_process_command_args_with_spaces() -> None:
    """Test command argument processing with spaces in values."""
    # Arguments with spaces should be preserved with shlex parsing
    cmd = 'create configmap test-map --from-literal=key="value with spaces"'
    args = _process_command_args(cmd, "create")
    assert args == [
        "create",
        "configmap",
        "test-map",
        "--from-literal=key=value with spaces",
    ]


def test_process_command_args_with_multiple_literals() -> None:
    """Test command argument processing with multiple --from-literal values."""
    # Multiple from-literal arguments
    cmd = (
        'create configmap test-map --from-literal=key1="value1" '
        '--from-literal=key2="value with spaces"'
    )
    args = _process_command_args(cmd, "create")
    assert args == [
        "create",
        "configmap",
        "test-map",
        "--from-literal=key1=value1",
        "--from-literal=key2=value with spaces",
    ]


def test_process_command_args_html_content() -> None:
    """Test command argument processing with HTML content in values."""
    # HTML content in from-literal
    cmd = (
        "create configmap nginx-config "
        '--from-literal=index.html="<html><body>'
        '<h1>CTF-FLAG-1: K8S_MASTER</h1></body></html>"'
    )
    args = _process_command_args(cmd, "create")
    html_value = "<html><body><h1>CTF-FLAG-1: K8S_MASTER</h1></body></html>"
    assert args == [
        "create",
        "configmap",
        "nginx-config",
        f"--from-literal=index.html={html_value}",
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
    from vibectl.command_handler import handle_vibe_request

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
            from vibectl.types import OutputFlags

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
