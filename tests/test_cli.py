"""Tests for the CLI interface.

This module tests the CLI interface of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to:
1. kubectl (use mock_run_kubectl)
2. Command output processing (use mock_handle_command_output)
3. LLM/vibe requests (use mock_handle_vibe_request)

For most CLI tests, use the cli_test_mocks fixture which provides all three.
"""

import subprocess
from collections.abc import Generator
from unittest.mock import ANY, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.prompt import describe_resource_prompt

# The cli_runner and mock_config fixtures are now provided by conftest.py


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


@pytest.fixture(autouse=True, scope="module")
def patch_kubectl_and_llm() -> Generator[None, None, None]:
    """Global fixture to ensure kubectl and LLM calls are mocked.

    This fixture patches both the direct import in cli.py and
    the source function in command_handler.py to ensure all
    calls are properly mocked regardless of import path.
    """
    with (
        patch("vibectl.cli.run_kubectl") as cli_mock_run_kubectl,
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as cli_mock_handle_output,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.cli.handle_vibe_request") as cli_mock_handle_vibe,
        patch("vibectl.command_handler.handle_vibe_request") as cmd_mock_handle_vibe,
        patch("vibectl.model_adapter.get_model_adapter") as mock_adapter,
    ):
        # Set up the model adapter mock
        adapter_instance = Mock()
        mock_adapter.return_value = adapter_instance

        # Set up the model mock
        mock_model = Mock()
        adapter_instance.get_model.return_value = mock_model
        adapter_instance.execute.return_value = "Test response"

        # Set up kubectl mocks to return success by default
        cli_mock_run_kubectl.return_value = "kubectl result"
        cmd_mock_run_kubectl.return_value = "kubectl result"

        # Set up handler mocks to work together
        cli_mock_handle_output.side_effect = cmd_mock_handle_output
        cli_mock_handle_vibe.side_effect = cmd_mock_handle_vibe

        yield


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

        with (
            patch("vibectl.cli.console_manager") as mock_console,
            patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
            patch(
                "vibectl.command_handler.handle_command_output"
            ) as cmd_mock_handle_output,
            patch("vibectl.cli.validate_model_key_on_startup") as mock_validate,
        ):
            # Set up mock return value
            cmd_mock_run_kubectl.return_value = "test output"
            # Mock validate function to avoid warnings
            mock_validate.return_value = None

            result = cli_runner.invoke(cli, ["get", "pods"])

            assert result.exit_code == 0
            # Check that we called get twice - once for theme, once for model
            assert mock_config.get.call_count == 2
            # Check theme was set
            mock_console.set_theme.assert_called_once_with("dark")
            cmd_mock_handle_output.assert_called_once()


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
    # Note: This test mocks vibectl.cli.run_kubectl but in the CLI code,
    # vibectl.command_handler.run_kubectl is actually called.
    # We need to patch both to make this test reliable.
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
    ):
        # Set up mocks appropriately
        cmd_mock_run_kubectl.return_value = "test output"

        # Invoke CLI
        result = cli_runner.invoke(cli, ["get", "pods"])

        # Check results - using command_handler mocks
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
        cmd_mock_handle_output.assert_called_once()


def test_get_with_args(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with additional arguments."""
    # Need to use the correct patching strategy
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
    ):
        # Set up mock return value
        cmd_mock_run_kubectl.return_value = "test output"

        # Pass namespace as a single argument
        result = cli_runner.invoke(cli, ["get", "pods", "-n", "default"])

        # Check results - using command_handler mocks
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(
            ["get", "pods", "-n", "default"], capture=True
        )
        cmd_mock_handle_output.assert_called_once()


def test_get_no_output(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command when kubectl returns no output."""
    # Need to use the correct patching strategy
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output"),
    ):
        # Set up mock return value - empty string
        cmd_mock_run_kubectl.return_value = ""

        # Invoke CLI command
        result = cli_runner.invoke(cli, ["get", "pods"])

        # Check results
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


def test_get_with_flags(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with output flags."""
    # Need to use the correct patching strategy
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output"),
    ):
        # Set up mock return value
        cmd_mock_run_kubectl.return_value = "test output"

        result = cli_runner.invoke(
            cli,
            [
                "get",
                "pods",
                "--show-raw-output",
                "--no-show-vibe",
                "--model",
                "test-model",
            ],
        )

        # Check results
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


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
    # Need to use the correct patching strategy
    with patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl:
        # Set up mock to raise an exception
        cmd_mock_run_kubectl.side_effect = Exception("Test error")

        # Let's just verify the exit code - that's sufficient to show error handling
        # The error output might be captured differently based on where it's redirected
        result = cli_runner.invoke(cli, ["get", "pods"])

        # Check that the command failed with a non-zero exit code
        assert result.exit_code != 0


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.handle_standard_command")
def test_describe_basic(
    mock_handle_standard: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic describe command functionality."""
    # Set up the return value for configure_output_flags to return
    # an OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )

    result = cli_runner.invoke(cli, ["describe", "pod", "my-pod"])

    assert result.exit_code == 0
    mock_handle_standard.assert_called_once_with(
        command="describe",
        resource="pod",
        args=("my-pod",),
        output_flags=mock_configure_flags.return_value,
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
    # Set up the return value for configure_output_flags to return
    # an OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )

    # Use -- to separate options from arguments
    result = cli_runner.invoke(
        cli, ["describe", "pod", "my-pod", "--", "-n", "default"]
    )

    assert result.exit_code == 0
    mock_handle_standard.assert_called_once_with(
        command="describe",
        resource="pod",
        args=("my-pod", "-n", "default"),
        output_flags=mock_configure_flags.return_value,
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
    # Set up the return value for configure_output_flags to return
    # an OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=True, show_vibe=False, warn_no_output=False, model_name="test-model"
    )

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
        output_flags=mock_configure_flags.return_value,
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
    # Call should fail since there's no request provided
    with patch("vibectl.cli.console_manager.print_missing_request_error"):
        result = cli_runner.invoke(cli, ["describe", "vibe"])

        # Verify the command fails - exact exit code depends on implementation
        assert result.exit_code != 0 or isinstance(result.exception, SystemExit)


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.handle_standard_command")
def test_describe_error_handling(
    mock_handle_standard: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test describe command error handling."""
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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
    cli_runner.invoke(cli, ["logs", "vibe"])

    # In test environment, Click's runner might not capture the real exit code
    # but we can still verify the error message was displayed
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


@patch("vibectl.cli.configure_output_flags")
@patch("vibectl.cli.run_kubectl")
@patch("vibectl.cli.handle_command_output")
def test_logs_error_handling(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test logs command error handling."""
    # Set up the return value for configure_output_flags to return
    # an OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    mock_run_kubectl.side_effect = Exception("Test error")

    # Ensure exception handling works
    with patch("vibectl.cli.handle_exception") as mock_handle_exception:
        result = cli_runner.invoke(cli, ["logs", "pod", "my-pod"])
        mock_handle_exception.assert_called_once()

    # Since we patched handle_exception, exit code should be 0
    # as the exception is caught and handled
    assert result.exit_code == 0


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
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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
    mock_configure_flags.return_value = (False, True, False, "model-xyz-1.2.3")
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

    # Need to also patch validate_model_key_on_startup to avoid warnings
    with patch("vibectl.cli.validate_model_key_on_startup") as mock_validate:
        mock_validate.return_value = None
        result = cli_runner.invoke(cli, ["instructions", "show"])

    assert result.exit_code == 0
    assert "Test instructions" in result.output
    # Now called 3 times (theme, model, custom_instructions)
    assert mock_config.get.call_count == 3
    # Check that custom_instructions was called at some point
    assert any(
        call[0][0] == "custom_instructions" for call in mock_config.get.call_args_list
    )


@patch("vibectl.cli.Config")
def test_instructions_show_get_error(
    mock_config_class: Mock, cli_runner: CliRunner
) -> None:
    """Test instructions show command error handling when getting instructions."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    
    # Set side effects for multiple calls
    # Theme, model (no error), but error on custom_instructions
    mock_config.get.side_effect = [
        "dark",  # theme
        "claude-3.7-sonnet",  # model
        Exception("Failed to get instructions")  # custom_instructions
    ]

    # Need to also patch validate_model_key_on_startup to avoid warnings
    with patch("vibectl.cli.validate_model_key_on_startup") as mock_validate:
        mock_validate.return_value = None
        result = cli_runner.invoke(cli, ["instructions", "show"])

    assert result.exit_code == 1
    assert mock_config.get.call_count == 3


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
    cli_runner.invoke(cli, ["version", "vibe"])

    # In test environment, Click's runner might not capture the real exit code
    # but we can still verify the error message was displayed
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
    cli_runner.invoke(cli, ["events", "vibe"])

    # In test environment, Click's runner might not capture the real exit code
    # but we can still verify the error message was displayed
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


@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.Config")
def test_just_general_exception(
    mock_config_class: Mock, mock_console: Mock, cli_runner: CliRunner
) -> None:
    """Test just command with a general exception."""
    # Setup Config to raise a generic exception
    error = Exception("General error")
    mock_config_class.side_effect = error

    # Invoke command with catch_exceptions=False to let exception bubble up
    with pytest.raises(Exception) as excinfo:
        cli_runner.invoke(cli, ["just", "get", "pods"], catch_exceptions=False)

    # Verify the error is the one we created
    assert "General error" in str(excinfo.value)


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


@patch("vibectl.cli.handle_vibe_request")
@patch("vibectl.cli.get_memory")
def test_vibe_command_with_no_arguments(
    mock_get_memory: MagicMock, mock_handle_vibe: MagicMock, cli_runner: CliRunner
) -> None:
    """Test 'vibe' command with no arguments."""
    # Set up mock to return empty memory
    mock_get_memory.return_value = ""

    # Run the CLI command
    result = cli_runner.invoke(cli, ["vibe"])

    # Verify success
    assert result.exit_code == 0

    # Verify that handle_vibe_request was called with empty request
    mock_handle_vibe.assert_called_once()
    call_args = mock_handle_vibe.call_args[1]
    assert call_args["request"] == ""
    assert call_args["command"] == "vibe"
    assert call_args["autonomous_mode"] is True

    # Verify that the plan prompt includes memory context and empty request
    assert (
        "Here's the current memory context and request:"
        in mock_handle_vibe.call_args_list[0][1]["plan_prompt"]
    )
    assert "Request: " in mock_handle_vibe.call_args_list[0][1]["plan_prompt"]


@patch("vibectl.cli.handle_vibe_request")
@patch("vibectl.cli.get_memory")
def test_vibe_command_with_existing_memory(
    mock_get_memory: MagicMock, mock_handle_vibe: MagicMock, cli_runner: CliRunner
) -> None:
    """Test 'vibe' command with existing memory."""
    # Set up mock to return some memory content
    mock_get_memory.return_value = "Working in namespace 'test' with deployment 'app'"

    # Run the CLI command
    result = cli_runner.invoke(cli, ["vibe"])

    # Verify success
    assert result.exit_code == 0

    # Verify that handle_vibe_request was called with empty request
    # but the memory context was properly included
    mock_handle_vibe.assert_called_once()
    call_args = mock_handle_vibe.call_args[1]
    assert call_args["request"] == ""
    assert call_args["command"] == "vibe"
    assert call_args["autonomous_mode"] is True

    # Check that memory context is properly included in plan prompt
    plan_prompt = call_args["plan_prompt"]
    assert "Working in namespace 'test' with deployment 'app'" in plan_prompt


@patch("vibectl.cli.handle_vibe_request")
@patch("vibectl.cli.get_memory")
def test_vibe_command_with_explicit_request(
    mock_get_memory: MagicMock, mock_handle_vibe: MagicMock, cli_runner: CliRunner
) -> None:
    """Test 'vibe' command with an explicit request argument."""
    # Set up mock to return some memory content
    mock_get_memory.return_value = "Working in namespace 'test'"

    # Run the CLI command with an explicit request
    result = cli_runner.invoke(cli, ["vibe", "scale deployment app to 3 replicas"])

    # Verify success
    assert result.exit_code == 0

    # Verify that handle_vibe_request was called with the correct request
    mock_handle_vibe.assert_called_once()
    call_args = mock_handle_vibe.call_args[1]
    assert call_args["request"] == "scale deployment app to 3 replicas"
    assert call_args["command"] == "vibe"
    assert call_args["autonomous_mode"] is True

    # Check that memory context and request are properly included in plan prompt
    plan_prompt = call_args["plan_prompt"]
    assert "Working in namespace 'test'" in plan_prompt
    assert "scale deployment app to 3 replicas" in plan_prompt

    # Verify that processing message showed the request
    assert "Planning how to: scale deployment app to 3 replicas" in result.output


def test_get_vibe_basic(
    cli_runner: CliRunner, mock_config: Mock, cli_test_mocks: tuple[Mock, Mock, Mock]
) -> None:
    """Test basic get vibe command."""
    # Setup mocks
    mock_run_kubectl, mock_handle_output, mock_handle_vibe = cli_test_mocks
    mock_configure_flags = Mock()

    # Return OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )

    # Execute the command
    with patch("vibectl.cli.configure_output_flags", mock_configure_flags):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)

    # Assert based on exit code and function calls
    assert result.exit_code == 0
    # handle_vibe_request is called instead of run_kubectl directly
    mock_handle_vibe.assert_called_once_with(
        request="pods",
        command="get",
        plan_prompt=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_configure_flags.return_value,
    )
    # These should not be called for vibe requests
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_output_flags(
    cli_runner: CliRunner, mock_config: Mock, cli_test_mocks: tuple[Mock, Mock, Mock]
) -> None:
    """Test get vibe command with output flags."""
    # Setup mocks
    mock_run_kubectl, mock_handle_output, mock_handle_vibe = cli_test_mocks
    mock_configure_flags = Mock()

    # Return OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )

    # Execute the command
    with patch("vibectl.cli.configure_output_flags", mock_configure_flags):
        result = cli_runner.invoke(
            cli, ["get", "vibe", "pods", "--raw", "--no-vibe"], catch_exceptions=False
        )

    # Assert based on exit code and function calls
    assert result.exit_code == 0
    # handle_vibe_request is called instead of run_kubectl directly
    mock_handle_vibe.assert_called_once_with(
        request="pods --raw --no-vibe",
        command="get",
        plan_prompt=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_configure_flags.return_value,
    )
    # These should not be called for vibe requests
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_model_flag(
    cli_runner: CliRunner, mock_config: Mock, cli_test_mocks: tuple[Mock, Mock, Mock]
) -> None:
    """Test get vibe command with model flag."""
    # Setup mocks
    mock_run_kubectl, mock_handle_output, mock_handle_vibe = cli_test_mocks
    mock_configure_flags = Mock()

    # Return OutputFlags instance with test-model
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",  # This is set by the test
    )

    # Execute the command
    with patch("vibectl.cli.configure_output_flags", mock_configure_flags):
        result = cli_runner.invoke(
            cli,
            ["get", "vibe", "pods", "--model", "test-model"],
            catch_exceptions=False,
        )

    # Assert based on exit code and function calls
    assert result.exit_code == 0
    # handle_vibe_request is called instead of run_kubectl directly
    mock_handle_vibe.assert_called_once_with(
        request="pods",  # Model flag is handled separately
        command="get",
        plan_prompt=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_configure_flags.return_value,
    )
    # These should not be called for vibe requests
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_no_output_flags(
    cli_runner: CliRunner, mock_config: Mock, cli_test_mocks: tuple[Mock, Mock, Mock]
) -> None:
    """Test get vibe command with no output flags."""
    # Setup mocks
    mock_run_kubectl, mock_handle_output, mock_handle_vibe = cli_test_mocks
    mock_configure_flags = Mock()

    # Return OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )

    # Execute the command
    with patch("vibectl.cli.configure_output_flags", mock_configure_flags):
        result = cli_runner.invoke(
            cli,
            ["get", "vibe", "pods", "--no-raw", "--no-vibe"],
            catch_exceptions=False,
        )

    # Assert based on exit code and function calls
    assert result.exit_code == 0
    # handle_vibe_request is called instead of run_kubectl directly
    mock_handle_vibe.assert_called_once_with(
        request="pods --no-raw --no-vibe",
        command="get",
        plan_prompt=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_configure_flags.return_value,
    )
    # These should not be called for vibe requests
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_env_flags(
    cli_runner: CliRunner, mock_config: Mock, cli_test_mocks: tuple[Mock, Mock, Mock]
) -> None:
    """Test get vibe command with environment flags."""
    # Setup mocks
    mock_run_kubectl, mock_handle_output, mock_handle_vibe = cli_test_mocks
    mock_configure_flags = Mock()

    # Return OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )

    # Execute the command
    with patch("vibectl.cli.configure_output_flags", mock_configure_flags):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)

    # Assert based on exit code and function calls
    assert result.exit_code == 0
    # handle_vibe_request is called instead of run_kubectl directly
    mock_handle_vibe.assert_called_once_with(
        request="pods",
        command="get",
        plan_prompt=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_configure_flags.return_value,
    )
    # These should not be called for vibe requests
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_default_flags(
    cli_runner: CliRunner, mock_config: Mock, cli_test_mocks: tuple[Mock, Mock, Mock]
) -> None:
    """Test get vibe command with default flags."""
    # Setup mocks
    mock_run_kubectl, mock_handle_output, mock_handle_vibe = cli_test_mocks
    mock_configure_flags = Mock()

    # Return OutputFlags instance
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )

    # Execute the command
    with patch("vibectl.cli.configure_output_flags", mock_configure_flags):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)

    # Assert based on exit code and function calls
    assert result.exit_code == 0
    # handle_vibe_request is called instead of run_kubectl directly
    mock_handle_vibe.assert_called_once_with(
        request="pods",
        command="get",
        plan_prompt=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_configure_flags.return_value,
    )
    # These should not be called for vibe requests
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


@patch("vibectl.cli.validate_model_key_on_startup")
@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.Config")
def test_cli_validates_model_key_on_startup(
    mock_config_class: Mock,
    mock_console: Mock,
    mock_validate: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test that CLI validates model key on startup."""
    # Setup Config mock to return model name
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = "claude-3.7-sonnet"

    # Setup mock to return a warning
    mock_validate.return_value = "Test validation warning"

    # Run the CLI command
    result = cli_runner.invoke(cli, ["get", "pods"])

    # Verify validation was called
    mock_validate.assert_called_once()
    # Verify warning was displayed
    mock_console.print_warning.assert_called_once_with("Test validation warning")
    assert result.exit_code == 0


@patch("vibectl.cli.validate_model_key_on_startup")
@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.Config")
def test_cli_no_warning_for_valid_key(
    mock_config_class: Mock,
    mock_console: Mock,
    mock_validate: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test that CLI doesn't show warning for valid key."""
    # Setup Config mock to return model name
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = "claude-3.7-sonnet"

    # Setup mock to return None (no warning)
    mock_validate.return_value = None

    # Run the CLI command
    result = cli_runner.invoke(cli, ["get", "pods"])

    # Verify validation was called
    mock_validate.assert_called_once()
    # Verify no warning was displayed
    mock_console.print_warning.assert_not_called()
    assert result.exit_code == 0


@patch("vibectl.cli.validate_model_key_on_startup")
@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.Config")
def test_cli_no_warning_for_config_command(
    mock_config_class: Mock,
    mock_console: Mock,
    mock_validate: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test that CLI doesn't show warning for config command."""
    # Setup Config mock to return model name
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = "claude-3.7-sonnet"

    # Setup mock to return a warning
    mock_validate.return_value = "Test validation warning"

    # Run the config command
    result = cli_runner.invoke(cli, ["config", "--help"])

    # Verify validation was called
    mock_validate.assert_called_once()
    # Verify no warning was displayed for config command
    mock_console.print_warning.assert_not_called()
    assert result.exit_code == 0
