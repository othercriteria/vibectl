"""Tests for the CLI interface.

This module tests the CLI interface of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to:
1. kubectl (use mock_run_kubectl)
2. Command output processing (use mock_handle_command_output)
3. LLM/vibe requests (use mock_handle_vibe_request)

For most CLI tests, use the cli_test_mocks fixture which provides all three.
"""

import subprocess
from typing import Generator
from unittest.mock import Mock, call, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.prompt import describe_resource_prompt


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture providing a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config() -> Generator[Mock, None, None]:
    """Fixture providing a mocked Config instance."""
    with patch("vibectl.cli.Config", autospec=True) as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Fixture providing a mocked console manager."""
    with patch("vibectl.cli.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Fixture providing a mocked run_kubectl function."""
    with patch("vibectl.cli.run_kubectl") as mock:
        yield mock


@pytest.fixture
def mock_handle_command_output() -> Generator[Mock, None, None]:
    """Fixture providing a mocked handle_command_output function."""
    with patch("vibectl.cli.handle_command_output") as mock:
        yield mock


def test_cli_version(cli_runner: CliRunner) -> None:
    """Test the --version flag."""
    result = cli_runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


def test_cli_help(cli_runner: CliRunner) -> None:
    """Test the --help flag."""
    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "vibectl - A vibes-based alternative to kubectl" in result.output


def test_cli_init_with_theme(
    cli_runner: CliRunner, mock_run_kubectl: Mock, mock_handle_command_output: Mock
) -> None:
    """Test CLI initialization with a configured theme.

    This test verifies theme initialization during CLI startup. It requires both:
    - mock_run_kubectl: To prevent real kubectl calls from the get command
    - mock_handle_command_output: To prevent real output processing

    The test uses a real command (get pods) to trigger the callback, as --help would
    not exercise the full CLI initialization path.
    """
    with patch("vibectl.cli.Config") as mock_config_class:
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        mock_config.get.return_value = "dark"

        with patch("vibectl.cli.console_manager") as mock_console:
            # Use get pods as a command that will trigger the callback
            mock_run_kubectl.return_value = "test output"
            result = cli_runner.invoke(cli, ["get", "pods"])
            assert result.exit_code == 0
            mock_config.get.assert_called_once_with("theme", "default")
            mock_console.set_theme.assert_called_once_with("dark")
            mock_handle_command_output.assert_called_once()


def test_cli_init_theme_error(cli_runner: CliRunner) -> None:
    """Test CLI initialization handles theme errors gracefully."""
    with patch("vibectl.cli.Config") as mock_config_class:
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        mock_config.get.side_effect = Exception("Theme error")

        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0  # Should not fail on theme error


def test_get_basic(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test basic get command functionality."""
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(cli, ["get", "pods"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
    mock_handle_command_output.assert_called_once()


def test_get_with_args(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with additional arguments."""
    mock_run_kubectl.return_value = "test output"

    # Pass namespace as a single argument
    result = cli_runner.invoke(cli, ["get", "pods", "-n", "default"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(
        ["get", "pods", "-n", "default"], capture=True
    )
    mock_handle_command_output.assert_called_once()


def test_get_no_output(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command when kubectl returns no output."""
    mock_run_kubectl.return_value = ""

    result = cli_runner.invoke(cli, ["get", "pods"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
    mock_handle_command_output.assert_not_called()


def test_get_with_flags(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with output flags."""
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(
        cli,
        ["get", "pods", "--show-raw-output", "--no-show-vibe", "--model", "test-model"],
    )

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
    mock_handle_command_output.assert_called_once()


@patch("vibectl.cli.handle_vibe_request")
def test_get_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test get command with vibe request."""
    result = cli_runner.invoke(cli, ["get", "vibe", "show", "me", "all", "pods"])

    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me all pods"
    assert kwargs["command"] == "get"


def test_get_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test get vibe command without a request."""
    result = cli_runner.invoke(cli, ["get", "vibe"])

    assert result.exit_code == 1
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


def test_get_error_handling(cli_runner: CliRunner, mock_run_kubectl: Mock) -> None:
    """Test get command error handling."""
    mock_run_kubectl.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["get", "pods"])

    assert result.exit_code == 1


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.handle_standard_command")
def test_describe_basic(
    mock_handle_standard: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic describe command functionality."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")

    result = cli_runner.invoke(cli, ["describe", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_handle_standard.assert_called_once_with(
        command="describe",
        resource="pod",
        args=("my-pod",),
        show_raw_output=False,
        show_vibe=True,
        model_name="claude-3.7-sonnet",
        summary_prompt_func=describe_resource_prompt,
    )


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.handle_standard_command")
def test_describe_with_args(
    mock_handle_standard: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test describe command with additional arguments."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")

    # Use -- to separate options from arguments
    result = cli_runner.invoke(
        cli, ["describe", "pod", "my-pod", "--", "-n", "default"]
    )

    assert result.exit_code == 0
    mock_handle_standard.assert_called_once_with(
        command="describe",
        resource="pod",
        args=("my-pod", "-n", "default"),
        show_raw_output=False,
        show_vibe=True,
        model_name="claude-3.7-sonnet",
        summary_prompt_func=describe_resource_prompt,
    )


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.handle_standard_command")
def test_describe_with_flags(
    mock_handle_standard: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test describe command with output flags."""
    mock_configure_flags.return_value = (True, False, False, "test-model")

    result = cli_runner.invoke(
        cli,
        [
            "describe",
            "pod",
            "my-pod",
            "--show-raw-output",
            "--no-show-vibe",
            "--model",
            "test-model",
        ],
    )

    assert result.exit_code == 0
    mock_handle_standard.assert_called_once_with(
        command="describe",
        resource="pod",
        args=("my-pod",),
        show_raw_output=True,
        show_vibe=False,
        model_name="test-model",
        summary_prompt_func=describe_resource_prompt,
    )


@patch("vibectl.cli.handle_vibe_request")
def test_describe_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test describe command with vibe request."""
    result = cli_runner.invoke(
        cli, ["describe", "vibe", "show", "me", "pod", "details"]
    )

    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me pod details"
    assert kwargs["command"] == "describe"


def test_describe_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test describe vibe command without a request."""
    result = cli_runner.invoke(cli, ["describe", "vibe"])

    assert result.exit_code == 0  # Note: Different from get, as it uses sys.exit(0)
    mock_console.print_missing_request_error.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.handle_standard_command")
def test_describe_error_handling(
    mock_handle_standard: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test describe command error handling."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_handle_standard.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["describe", "pod", "my-pod"])

    assert result.exit_code == 1  # Should exit with error code


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_logs_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic logs command functionality."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_logs_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with additional arguments."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_run_kubectl.return_value = "test output"

    # Use -- to separate options from arguments
    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod", "--", "-n", "default"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(
        ["logs", "pod", "my-pod", "-n", "default"], capture=True
    )
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_logs_with_flags(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with output flags."""
    mock_configure_flags.return_value = (True, False, False, "test-model")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(
        cli,
        [
            "logs",
            "pod",
            "my-pod",
            "--show-raw-output",
            "--no-show-vibe",
            "--model",
            "test-model",
        ],
    )

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_logs_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command when kubectl returns no output."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_run_kubectl.return_value = ""

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
@patch("vibectl.cli.console_manager")
def test_logs_truncation_warning(
    mock_console: Mock,
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command with output that might need truncation."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    # Create a large output that exceeds MAX_TOKEN_LIMIT * LOGS_TRUNCATION_RATIO
    mock_run_kubectl.return_value = "x" * (10000 * 3 + 1)  # Just over the limit

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"], capture=True)
    mock_console.print_truncation_warning.assert_called_once()
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.handle_vibe_request")
def test_logs_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test logs command with vibe request."""
    result = cli_runner.invoke(cli, ["logs", "vibe", "show", "me", "pod", "logs"])

    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me pod logs"
    assert kwargs["command"] == "logs"


def test_logs_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test logs vibe command without a request."""
    result = cli_runner.invoke(cli, ["logs", "vibe"])

    assert result.exit_code == 1
    mock_console.print_missing_request_error.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
def test_logs_error_handling(
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command error handling."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_run_kubectl.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])

    assert result.exit_code == 1  # Should exit with error code


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_create_basic(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic create command functionality."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(cli, ["create", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_create_with_args(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test create command with additional arguments."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_run_kubectl.return_value = "test output"

    # Use -- to separate options from arguments
    result = cli_runner.invoke(cli, ["create", "pod", "my-pod", "--", "-n", "default"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(
        ["create", "pod", "my-pod", "-n", "default"], capture=True
    )
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_create_with_flags(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test create command with output flags."""
    mock_configure_flags.return_value = (True, False, False, "test-model")
    mock_run_kubectl.return_value = "test output"

    result = cli_runner.invoke(
        cli,
        [
            "create",
            "pod",
            "my-pod",
            "--show-raw-output",
            "--no-show-vibe",
            "--model",
            "test-model",
        ],
    )

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_create_no_output(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test create command when kubectl returns no output."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_run_kubectl.return_value = ""

    result = cli_runner.invoke(cli, ["create", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["create", "pod", "my-pod"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.cli.handle_vibe_request")
def test_create_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test create command with vibe request."""
    result = cli_runner.invoke(cli, ["create", "vibe", "create", "a", "new", "pod"])

    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "create a new pod"
    assert kwargs["command"] == "create"


def test_create_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test create vibe command without a request."""
    result = cli_runner.invoke(cli, ["create", "vibe"])

    assert result.exit_code == 1
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
def test_create_error_handling(
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test create command error handling."""
    mock_configure_flags.return_value = (False, True, False, "claude-3.7-sonnet")
    mock_run_kubectl.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["create", "pod", "my-pod"])

    assert result.exit_code == 1  # Should exit with error code


@patch("subprocess.run")
@patch("vibectl.cli.Config")
def test_just_basic(mock_config: Mock, mock_subprocess_run: Mock) -> None:
    """Test basic just command functionality."""
    mock_config.return_value.get.return_value = None  # No kubeconfig set
    result = CliRunner().invoke(cli, ["just", "get", "pods"])
    assert result.exit_code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "get", "pods"], check=True, text=True, capture_output=True
    )


@patch("subprocess.run")
@patch("vibectl.cli.Config")
def test_just_with_kubeconfig(mock_config: Mock, mock_subprocess_run: Mock) -> None:
    """Test just command with kubeconfig."""
    mock_config.return_value.get.return_value = "/path/to/kubeconfig"
    result = CliRunner().invoke(cli, ["just", "get", "pods"])
    assert result.exit_code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "--kubeconfig", "/path/to/kubeconfig", "get", "pods"],
        check=True,
        text=True,
        capture_output=True,
    )


def test_just_no_args(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test just command without arguments."""
    result = cli_runner.invoke(cli, ["just"])

    assert result.exit_code == 1
    mock_console.print_error.assert_called_once_with(
        "Usage: vibectl just <kubectl commands>"
    )


@patch("subprocess.run")
@patch("vibectl.cli.Config")
def test_just_kubectl_not_found(
    mock_config: Mock, mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command when kubectl is not found."""
    mock_subprocess_run.side_effect = FileNotFoundError()

    result = cli_runner.invoke(cli, ["just", "get", "pods"])

    assert result.exit_code == 1
    assert "kubectl not found in PATH" in result.output


@patch("subprocess.run")
@patch("vibectl.cli.Config")
def test_just_called_process_error_with_stderr(
    mock_config: Mock, mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command with CalledProcessError and stderr."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="test error")
    mock_subprocess_run.side_effect = error

    result = cli_runner.invoke(cli, ["just", "get", "pods"])

    assert result.exit_code == 1
    assert "Error: test error" in result.output


@patch("subprocess.run")
@patch("vibectl.cli.Config")
def test_just_called_process_error_no_stderr(
    mock_config: Mock, mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command with CalledProcessError but no stderr."""
    error = subprocess.CalledProcessError(1, ["kubectl"], stderr="")
    mock_subprocess_run.side_effect = error

    result = cli_runner.invoke(cli, ["just", "get", "pods"])

    assert result.exit_code == 1
    assert "Error: Command failed with exit code 1" in result.output


@patch("vibectl.cli.Config")
def test_instructions_set_basic(mock_config_class: Mock, cli_runner: CliRunner) -> None:
    """Test basic instructions set functionality."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    result = cli_runner.invoke(cli, ["instructions", "set", "Test instructions"])

    assert result.exit_code == 0
    mock_config.set.assert_called_once_with("custom_instructions", "Test instructions")
    mock_config.save.assert_called_once()


@patch("vibectl.cli.Config")
@patch("click.edit")
def test_instructions_set_with_editor(
    mock_edit: Mock,
    mock_config_class: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test instructions set with editor."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_edit.return_value = "Editor instructions"

    result = cli_runner.invoke(cli, ["instructions", "set", "--edit"])

    assert result.exit_code == 0
    mock_edit.assert_called_once()
    mock_config.set.assert_called_once_with(
        "custom_instructions", "Editor instructions"
    )
    mock_config.save.assert_called_once()


@patch("vibectl.cli.Config")
def test_instructions_set_config_save_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test instructions set command handles config save error."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.save.side_effect = Exception("Failed to save instructions")

    result = cli_runner.invoke(cli, ["instructions", "set", "test instructions"])
    assert result.exit_code == 1
    assert "Failed to save instructions" in result.output


@patch("vibectl.cli.Config")
def test_instructions_show_basic(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test basic instructions show functionality."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = "Test instructions"

    result = cli_runner.invoke(cli, ["instructions", "show"])

    assert result.exit_code == 0
    assert "Test instructions" in result.output
    assert mock_config.get.call_count == 2
    mock_config.get.assert_has_calls(
        [call("theme", "default"), call("custom_instructions", "")]
    )


@patch("vibectl.cli.Config")
def test_instructions_show_get_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test instructions show command error handling when getting instructions."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.side_effect = [None, Exception("Failed to get instructions")]

    result = cli_runner.invoke(cli, ["instructions", "show"])

    assert result.exit_code == 1
    assert mock_config.get.call_count == 2
    mock_config.get.assert_has_calls(
        [call("theme", "default"), call("custom_instructions", "")]
    )


@patch("vibectl.cli.Config")
def test_instructions_clear_basic(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test basic instructions clear functionality."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    result = cli_runner.invoke(cli, ["instructions", "clear"])

    assert result.exit_code == 0
    mock_config.set.assert_called_once_with("custom_instructions", "")
    mock_config.save.assert_called_once()


@patch("vibectl.cli.Config")
def test_instructions_clear_unset_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test instructions clear command error handling when unsetting."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.set.side_effect = Exception("Failed to clear instructions")

    result = cli_runner.invoke(cli, ["instructions", "clear"])

    assert result.exit_code == 1
    mock_config.set.assert_called_once_with("custom_instructions", "")


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_version_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in version command."""
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["version"])

    assert result.exit_code == 1
    mock_run_kubectl.assert_called_once_with(["version", "--output=json"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_version_output_processing(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test version command output processing."""
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.return_value = "Client Version: v1.28.1\nServer Version: v1.28.2"

    result = cli_runner.invoke(cli, ["version"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["version", "--output=json"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.handle_vibe_request")
def test_version_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test version command with vibe request."""
    result = cli_runner.invoke(
        cli, ["version", "vibe", "show", "me", "version", "info"]
    )

    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me version info"
    assert kwargs["command"] == "version"


def test_version_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test version vibe command without a request."""
    result = cli_runner.invoke(cli, ["version", "vibe"])

    assert result.exit_code == 1
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_events_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in events command."""
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["events"])

    assert result.exit_code == 1
    mock_run_kubectl.assert_called_once_with(["events"], capture=True)
    mock_handle_output.assert_not_called()


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_events_output_processing(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test events command output processing."""
    mock_configure_flags.return_value = (True, True, False, "test-model")
    mock_run_kubectl.return_value = "Event data"

    result = cli_runner.invoke(cli, ["events"])

    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["events"], capture=True)
    mock_handle_output.assert_called_once()


@patch("vibectl.cli.handle_vibe_request")
def test_events_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test events command with vibe request."""
    result = cli_runner.invoke(
        cli, ["events", "vibe", "show", "me", "recent", "events"]
    )

    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me recent events"
    assert kwargs["command"] == "events"


def test_events_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test events vibe command without a request."""
    result = cli_runner.invoke(cli, ["events", "vibe"])

    assert result.exit_code == 1
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


@patch("vibectl.cli.cli")
@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.sys.exit")
def test_main_keyboard_interrupt(
    mock_exit: Mock, mock_console: Mock, mock_cli: Mock, cli_runner: CliRunner
) -> None:
    """Test main function handles keyboard interrupt."""
    mock_cli.side_effect = KeyboardInterrupt()
    mock_exit.side_effect = SystemExit(1)

    with pytest.raises(SystemExit) as exc_info:
        from vibectl.cli import main

        main()

    mock_console.print_keyboard_interrupt.assert_called_once()
    assert exc_info.value.code == 1


@patch("vibectl.cli.cli")
@patch("vibectl.cli.handle_exception")
@patch("vibectl.cli.sys.exit")
def test_main_general_error(
    mock_exit: Mock, mock_handle_exception: Mock, mock_cli: Mock, cli_runner: CliRunner
) -> None:
    """Test main function handles general errors."""
    error = Exception("Test error")
    mock_cli.side_effect = error
    mock_handle_exception.side_effect = SystemExit(1)

    with pytest.raises(SystemExit) as exc_info:
        from vibectl.cli import main

        main()

    mock_handle_exception.assert_called_once_with(error)
    assert exc_info.value.code == 1


@patch("subprocess.run")
@patch("vibectl.cli.Config")
def test_just_general_exception(
    mock_config: Mock, mock_subprocess_run: Mock, cli_runner: CliRunner
) -> None:
    """Test just command with a general exception."""
    # Setup Config to raise a generic exception
    mock_config.side_effect = Exception("General error")

    result = cli_runner.invoke(cli, ["just", "get", "pods"])

    assert result.exit_code == 1
    assert "Error: General error" in result.output


@patch("vibectl.cli.Config")
def test_instructions_set_no_text_no_edit(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test instructions set command without text and without edit flag."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    result = cli_runner.invoke(cli, ["instructions", "set"])

    assert result.exit_code == 1
    assert "Instructions cannot be empty" in result.output


def test_vibe_command(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test the vibe command that shows welcome information."""
    result = cli_runner.invoke(cli, ["vibe"])

    assert result.exit_code == 0
    mock_console.print.assert_called_once_with("Checking cluster vibes...")
    mock_console.print_vibe_welcome.assert_called_once()


def test_theme_set_invalid_theme(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test setting an invalid theme name."""
    with patch("vibectl.cli.console_manager.get_available_themes") as mock_get_themes:
        mock_get_themes.return_value = ["light", "dark"]

        # Test with invalid theme
        result = cli_runner.invoke(cli, ["theme", "set", "invalid_theme"])

        assert result.exit_code == 1
        mock_console.print_error.assert_called_once()
        # Verify the error message mentions available themes
        error_msg = mock_console.print_error.call_args[0][0]
        assert "Invalid theme" in error_msg
        assert "light" in error_msg
        assert "dark" in error_msg
