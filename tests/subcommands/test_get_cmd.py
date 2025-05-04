"""Tests for the 'get' subcommand logic in vibectl/subcommands/get_cmd.py.

Fixtures used are provided by conftest.py and ../fixtures.py.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags, handle_standard_command
from vibectl.subcommands import get_cmd
from vibectl.types import Error, Success, Truncation

# Assuming common fixtures like cli_runner, mock_run_kubectl, etc. are available
# from conftest.py or fixtures.py


def test_get_basic(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test basic get command functionality."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

        result = cli_runner.invoke(cli, ["get", "pods"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
        cmd_mock_handle_output.assert_called_once()


def test_get_with_args(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with additional arguments."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

        result = cli_runner.invoke(cli, ["get", "pods", "-n", "default"])
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
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output"),
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = ""  # Empty output
        cmd_mock_run_kubectl.return_value = success_instance

        result = cli_runner.invoke(cli, ["get", "pods"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


def test_get_with_flags(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with output flags."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output"),
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

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
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


def test_get_with_show_kubectl_flag(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with --show-kubectl flag."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output"),
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        result = cli_runner.invoke(cli, ["get", "pods", "--show-kubectl"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


def test_get_vibe_basic(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test basic get vibe command."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)
    assert result.exit_code == 0
    # Assert on the get_cmd mock
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is False
    assert kwargs["output_flags"].show_vibe is True
    assert kwargs["output_flags"].model_name == "model-xyz-1.2.3"
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_output_flags(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with output flags."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(
            cli, ["get", "vibe", "pods", "--raw", "--no-vibe"], catch_exceptions=False
        )
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods --raw --no-vibe"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is True
    assert kwargs["output_flags"].show_vibe is False
    assert kwargs["output_flags"].model_name == "model-xyz-1.2.3"
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_model_flag(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with model flag."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",  # This is set by the test
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(
            cli,
            ["get", "vibe", "pods", "--model", "test-model"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].model_name == "test-model"
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_no_output_flags(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with no output flags."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(
            cli,
            ["get", "vibe", "pods", "--no-raw", "--no-vibe"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods --no-raw --no-vibe"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is False
    assert kwargs["output_flags"].show_vibe is False
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_env_flags(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with environment flags."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is False
    assert kwargs["output_flags"].show_vibe is True
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_default_flags(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with default flags."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)
    assert result.exit_code == 0
    # Assert on the get_cmd mock
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is False
    assert kwargs["output_flags"].show_vibe is True
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


@pytest.fixture
def mock_summary_prompt() -> Callable[[], str]:
    """Mock summary prompt function."""
    return lambda: "Test Prompt: {output}"


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.command_handler.output_processor")
@patch("vibectl.command_handler.update_memory")
def test_handle_standard_command_basic(
    mock_update_memory: MagicMock,
    mock_processor: MagicMock,
    mock_get_adapter: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    test_config: Any,
    standard_output_flags: OutputFlags,
) -> None:
    """Test basic command handling (moved from test_standard_command.py)."""
    # Patch Config._save_config to prevent file I/O
    with (
        patch("vibectl.config.Config._save_config"),
        patch("vibectl.command_handler.Config") as mock_config_class,
    ):
        # Set up the config mock to return our test_config
        mock_config_class.return_value = test_config

        # Set test kubeconfig
        test_config.set("kubeconfig", "/test/kubeconfig")

        # Configure mock to return success
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test output"
        mock_subprocess.return_value = mock_result

        # Setup output processor mock to return Truncation
        mock_processor.process_auto.return_value = Truncation(
            original="test output", truncated="processed output"
        )

        # Ensure the get_model_adapter returns our mock_llm
        mock_get_adapter.return_value = mock_llm

        # Set up model adapter response for summary
        mock_model = Mock()
        mock_llm.get_model.return_value = mock_model
        mock_llm.execute.return_value = "Summarized output"

        # Run command
        handle_standard_command(
            command="get",
            resource="pods",
            args=(),
            output_flags=standard_output_flags,
            summary_prompt_func=lambda: "Test prompt: {output}",
        )

        # Verify command construction
        mock_subprocess.assert_called_once()
        cmd_args = mock_subprocess.call_args[0][0]

        # Don't check exact order, just make sure all parts are there
        assert "kubectl" in cmd_args
        assert "get" in cmd_args
        assert "pods" in cmd_args

    # Verify kwargs
    kwargs = mock_subprocess.call_args[1]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True

    # Verify model adapter was called with processed output
    mock_llm.execute.assert_called_once()
    # Check the prompt passed to the LLM
    prompt_arg = mock_llm.execute.call_args[0][1]
    assert "processed output" in prompt_arg

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.memory.include_memory_in_prompt")
@patch("vibectl.command_handler.update_memory")
@patch("vibectl.command_handler.output_processor")
def test_handle_standard_command(
    mock_processor: MagicMock,
    mock_update_memory: MagicMock,
    mock_include_memory: MagicMock,
    mock_get_adapter: MagicMock,
    mock_subprocess: MagicMock,
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_summary_prompt: Callable[[], str],
    test_config: Any,
    standard_output_flags: OutputFlags,
) -> None:
    """Test standard command handling (moved from test_standard_command.py)."""
    # Setup output processor mock to return Truncation
    mock_processor.process_auto.return_value = Truncation(
        original="test output", truncated="processed output"
    )

    # Ensure the get_model_adapter returns our mock_llm
    mock_get_adapter.return_value = mock_llm

    # Setup model
    mock_model = Mock()
    mock_llm.get_model.return_value = mock_model

    # Ensure memory functions are properly mocked
    mock_include_memory.side_effect = lambda x: x()

    # Ensure no kubeconfig is set
    test_config.set("kubeconfig", None)

    # Configure mock subprocess to return success
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "test output"
    mock_subprocess.return_value = mock_result

    # Set up model adapter response for summary
    mock_llm.execute.return_value = "Summarized output"

    # Run command
    handle_standard_command(
        command="get",
        resource="pods",
        args=(),
        output_flags=standard_output_flags,
        summary_prompt_func=mock_summary_prompt,
    )

    # Verify kubectl was called
    mock_subprocess.assert_called_once()
    cmd = mock_subprocess.call_args[0][0]
    assert cmd == ["kubectl", "get", "pods"]

    # Verify model adapter was called with processed output
    mock_llm.execute.assert_called_once()
    # Check the prompt passed to the LLM
    prompt_arg = mock_llm.execute.call_args[0][1]
    assert "processed output" in prompt_arg

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


# Tests moved from tests/test_cli.py


def test_cli_get_basic(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test basic get command functionality via CLI entrypoint."""
    # Note: This test mocks vibectl.command_handler.run_kubectl but in the CLI code,
    # vibectl.command_handler.run_kubectl is actually called.
    # We need to patch both to make this test reliable.
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

        # Invoke CLI
        result = cli_runner.invoke(cli, ["get", "pods"])

        # Check results - using command_handler mocks
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
        cmd_mock_handle_output.assert_called_once()


def test_cli_get_with_args(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with additional arguments via CLI entrypoint."""
    # Need to use the correct patching strategy
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

        # Pass namespace as a single argument
        result = cli_runner.invoke(cli, ["get", "pods", "-n", "default"])

        # Check results - using command_handler mocks
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(
            ["get", "pods", "-n", "default"], capture=True
        )
        cmd_mock_handle_output.assert_called_once()


def test_cli_get_no_output(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command when kubectl returns no output via CLI entrypoint."""
    # Need to use the correct patching strategy
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,  # Add Success mock
    ):
        # Set up mock return value to return a Success object with empty data
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = ""  # Empty output
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        # Ensure handle_command_output returns a Success object to prevent errors
        cmd_mock_handle_output.return_value = success_instance

        # Invoke CLI
        result = cli_runner.invoke(cli, ["get", "pods"])

        # Check results
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
        # handle_command_output should NOT be called with empty kubectl output
        cmd_mock_handle_output.assert_not_called()


def test_cli_get_with_flags(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with output flags via CLI entrypoint."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,  # Use the mock here
        patch("vibectl.types.Success") as mock_success,  # Add Success mock
    ):
        # Setup mocks
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance
        cmd_mock_handle_output.return_value = success_instance  # Mock return value

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
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
        cmd_mock_handle_output.assert_called_once()  # Verify output handler called


def test_cli_get_with_show_kubectl_flag(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with --show-kubectl flag via CLI entrypoint."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,  # Use the mock here
        patch("vibectl.types.Success") as mock_success,  # Add Success mock
    ):
        # Setup mocks
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance
        cmd_mock_handle_output.return_value = success_instance  # Mock return value

        result = cli_runner.invoke(cli, ["get", "pods", "--show-kubectl"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
        cmd_mock_handle_output.assert_called_once()  # Verify output handler called


def test_cli_get_with_no_show_kubectl_flag(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command without --show-kubectl flag via CLI entrypoint."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,
    ):
        # Setup mocks
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance
        cmd_mock_handle_output.return_value = success_instance

        result = cli_runner.invoke(cli, ["get", "pods"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)
        cmd_mock_handle_output.assert_called_once()
        # The assertion here is implicitly that no extra output happened,
        # which is covered by mocking handle_command_output.


@patch("vibectl.subcommands.get_cmd.handle_vibe_request")
def test_cli_get_vibe_request(
    mock_handle_vibe_get: Mock, cli_runner: CliRunner
) -> None:
    """Test invoking 'get vibe' from the CLI."""
    mock_handle_vibe_get.return_value = Success(message="Vibe request handled")
    result = cli_runner.invoke(cli, ["get", "vibe", "list pods"])
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    # Check the arguments passed to the mocked function
    call_args, call_kwargs = mock_handle_vibe_get.call_args
    assert call_kwargs["request"] == "list pods"
    assert call_kwargs["command"] == "get"
    # Check that output_flags are passed (existence and type)
    assert "output_flags" in call_kwargs
    assert isinstance(call_kwargs["output_flags"], OutputFlags)


def test_cli_get_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test 'get vibe' without a request string produces an error."""
    result = cli_runner.invoke(cli, ["get", "vibe"])
    assert result.exit_code != 0
    assert "Missing request" in result.output
    # Check console error output if needed, but exit code is usually sufficient


def test_cli_get_error_handling(cli_runner: CliRunner, mock_run_kubectl: Mock) -> None:
    """Test that errors from kubectl during 'get' are handled."""
    # Mock run_kubectl to return an Error (without exit_code)
    mock_run_kubectl.return_value = Error(error="kubectl failed")

    # We also need to mock handle_command_output because it's called even on error
    # to potentially summarize the error, let it return Error too (without exit_code).
    with patch("vibectl.command_handler.handle_command_output") as mock_handle_output:
        mock_handle_output.return_value = Error(error="kubectl failed")
        result = cli_runner.invoke(cli, ["get", "pods"])

    assert result.exit_code != 0
    # Check that the error from run_kubectl was propagated
    # This is implicitly checked by the non-zero exit code
    # and potentially by checking stderr if needed.


# --- Tests for --watch flag --- #


@patch("vibectl.subcommands.get_cmd.handle_watch_with_live_display")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@patch("vibectl.subcommands.get_cmd.configure_memory_flags")
@patch("vibectl.cli.validate_model_key_on_startup")
def test_get_watch_success(
    mock_validate_keys: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_watch: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test 'get --watch' calls handle_watch_with_live_display and returns Success."""
    # Set mock return value to None to suppress warning
    mock_validate_keys.return_value = None
    # Mock the output flags and watch handler return value
    mock_flags = Mock(spec=OutputFlags)
    mock_configure_output.return_value = mock_flags
    # Make the internal handler return Success
    mock_handle_watch.return_value = Success(
        message="Watch completed internally", data="Watch data"
    )

    # Invoke the command with --watch
    result = cli_runner.invoke(cli, ["get", "pods", "--watch"], catch_exceptions=False)

    # Assertions
    assert result.exit_code == 0
    mock_validate_keys.assert_called_once()
    mock_configure_memory.assert_called_once()
    mock_configure_output.assert_called_once()
    mock_handle_watch.assert_called_once()
    # We don't assert on the final_result object anymore


@patch("vibectl.subcommands.get_cmd.handle_watch_with_live_display")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@patch("vibectl.subcommands.get_cmd.configure_memory_flags")
def test_get_watch_error(
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_watch: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test that 'get --watch' handles errors from handle_watch_with_live_display."""
    # Mock the output flags and watch handler return value (Error)
    mock_flags = Mock(spec=OutputFlags)
    mock_configure_output.return_value = mock_flags
    mock_handle_watch.return_value = Error(error="Watch failed")

    # Invoke the command with -w (short flag)
    result = cli_runner.invoke(cli, ["get", "pods", "-w"], catch_exceptions=False)

    # Assertions
    assert result.exit_code != 0  # Should be non-zero exit code
    assert "Watch failed" in result.output
    mock_configure_memory.assert_called_once()
    mock_configure_output.assert_called_once()
    mock_handle_watch.assert_called_once()
    # Verify args passed to the watch handler
    args, kwargs = mock_handle_watch.call_args
    assert kwargs["command"] == "get"
    assert kwargs["resource"] == "pods"
    assert "-w" in kwargs["args"]
    assert kwargs["output_flags"] == mock_flags
    assert callable(kwargs["summary_prompt_func"])


# --- Tests for Error propagation --- #


@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@patch("vibectl.subcommands.get_cmd.configure_memory_flags")
def test_get_standard_command_error_propagation(
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_standard: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test that errors from handle_standard_command are propagated."""
    # Mock handlers
    mock_flags = Mock(spec=OutputFlags)
    mock_configure_output.return_value = mock_flags
    mock_handle_standard.return_value = Error(error="Standard command failed")

    # Invoke command
    result = cli_runner.invoke(cli, ["get", "pods"], catch_exceptions=False)

    # Assertions
    assert result.exit_code != 0
    assert "Standard command failed" in result.output
    mock_handle_standard.assert_called_once()


@patch("vibectl.subcommands.get_cmd.handle_vibe_request")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@patch("vibectl.subcommands.get_cmd.configure_memory_flags")
@patch("vibectl.subcommands.get_cmd.get_memory", return_value="mock memory")
def test_get_vibe_request_error_propagation(
    mock_get_memory: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_vibe: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test that errors from handle_vibe_request are propagated."""
    # Mock handlers
    mock_flags = Mock(spec=OutputFlags)
    mock_configure_output.return_value = mock_flags
    mock_handle_vibe.return_value = Error(error="Vibe request failed")

    # Invoke command
    result = cli_runner.invoke(
        cli, ["get", "vibe", "some request"], catch_exceptions=False
    )

    # Assertions
    assert result.exit_code != 0
    assert "Vibe request failed" in result.output
    mock_handle_vibe.assert_called_once()


# --- Test for top-level exception handling --- #


@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@patch("vibectl.subcommands.get_cmd.logger")  # Keep original patch target here
def test_get_top_level_exception(
    mock_logger: Mock,
    mock_configure_output: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test the top-level exception handler in run_get_command."""
    # Mock configure_output_flags to raise an exception
    test_exception = ValueError("Flag configuration error")
    mock_configure_output.side_effect = test_exception

    # Invoke command
    result = cli_runner.invoke(cli, ["get", "pods"], catch_exceptions=False)

    # Assertions
    assert result.exit_code != 0
    assert "Exception in 'get' subcommand" in result.output

    # Verify error was logged
    mock_logger.error.assert_called_once()
    args, kwargs = mock_logger.error.call_args
    assert "Error in 'get' subcommand:" in args[0]
    assert args[1] == test_exception
    assert kwargs.get("exc_info") is True  # Check that traceback was logged


# --- Tests for specific success/edge cases --- #


@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@patch("vibectl.subcommands.get_cmd.configure_memory_flags")
@patch("vibectl.cli.validate_model_key_on_startup")
def test_get_standard_command_success_no_data(
    mock_validate_keys: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_standard: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test success path when handle_standard_command returns Success with no data."""
    # Set mock return value to None to suppress warning
    mock_validate_keys.return_value = None
    # Mock handlers
    mock_flags = Mock(spec=OutputFlags)
    mock_configure_output.return_value = mock_flags
    # Return Success but with data=None
    mock_handle_standard.return_value = Success(
        message="Standard command ran internally", data=None
    )

    # Invoke command
    result = cli_runner.invoke(cli, ["get", "pods"], catch_exceptions=False)

    # Assertions
    assert result.exit_code == 0
    mock_validate_keys.assert_called_once()
    mock_handle_standard.assert_called_once()
    # Don't need to check configure flags again here, covered elsewhere


@patch("vibectl.subcommands.get_cmd.handle_vibe_request")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
@patch("vibectl.subcommands.get_cmd.configure_memory_flags")
@patch("vibectl.subcommands.get_cmd.get_memory", return_value="mock memory")
@patch("vibectl.cli.validate_model_key_on_startup")
def test_get_vibe_request_success_no_data(
    mock_validate_keys: Mock,
    mock_get_memory: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_vibe: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test success path when handle_vibe_request returns Success with no data."""
    # Set mock return value to None to suppress warning
    mock_validate_keys.return_value = None
    # Mock handlers
    mock_flags = Mock(spec=OutputFlags)
    mock_configure_output.return_value = mock_flags
    # Return Success but with data=None
    mock_handle_vibe.return_value = Success(
        message="Vibe request ran internally", data=None
    )

    # Invoke command
    result = cli_runner.invoke(
        cli, ["get", "vibe", "some request"], catch_exceptions=False
    )

    # Assertions
    # We mainly care that the command succeeded and called the right handler
    assert result.exit_code == 0
    mock_validate_keys.assert_called_once()
    mock_handle_vibe.assert_called_once()
    # Don't need to check configure flags again here, covered elsewhere


@patch("vibectl.subcommands.get_cmd.configure_output_flags")
def test_get_vibe_missing_request_arg(
    mock_configure_output_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test that 'get vibe' without a request string produces an error."""
    # Patch validate_model_key_on_startup and configure_memory_flags locally
    with (
        patch("vibectl.cli.validate_model_key_on_startup", return_value=None),
        patch("vibectl.memory.configure_memory_flags"),
    ):
        result = cli_runner.invoke(cli, ["get", "vibe"], catch_exceptions=False)

        # Assertions
        assert result.exit_code != 0
        assert "Missing request" in result.output
        # Check that configure steps were called before the error was raised
        mock_configure_output_flags.assert_called_once()
        # No assertion needed for configure_memory_flags mock


# --- Test added for vibe with no args ---
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
def test_run_get_command_vibe_no_args(
    mock_configure_output_flags: Mock,
) -> None:
    """Test run_get_command returns Error if resource is 'vibe' but args is empty."""
    # Arrange
    mock_configure_output_flags.return_value = Mock(spec=OutputFlags)

    # Act: Call run_get_command directly, patching memory flags locally
    with patch("vibectl.memory.configure_memory_flags"):
        final_result = get_cmd.run_get_command(
            resource="vibe",
            args=(),  # Empty args tuple
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        # Assert
        assert isinstance(final_result, Error)
        assert "Missing request after 'vibe' command" in final_result.error
        mock_configure_output_flags.assert_called_once()
        # No assertion needed for configure_memory_flags mock


# --- Tests for run_get_command internal logic --- #
@patch("vibectl.subcommands.get_cmd.handle_standard_command")
@patch("vibectl.subcommands.get_cmd.configure_output_flags")
def test_run_get_command_propagates_handler_error(
    mock_configure_output_flags: Mock,
    mock_handle_standard: Mock,
) -> None:
    """Test run_get_command returns Error if internal handler returns Error."""
    # Arrange: Mock internal handler to return an Error
    error_result = Error(error="Internal handler failure")
    mock_handle_standard.return_value = error_result
    mock_configure_output_flags.return_value = Mock(spec=OutputFlags)

    # Act: Call run_get_command directly, patching memory flags locally
    with patch("vibectl.memory.configure_memory_flags"):
        final_result = get_cmd.run_get_command(
            resource="pods",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            show_kubectl=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        # Assert: The returned result should be the exact Error object
        assert final_result is error_result
        mock_handle_standard.assert_called_once()
        mock_configure_output_flags.assert_called_once()
        # No assertion needed for configure_memory_flags mock
