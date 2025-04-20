"""Tests for the CLI interface.

This module tests the CLI interface of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to:
1. kubectl (use mock_run_kubectl)
2. Command output processing (use mock_handle_command_output)
3. LLM/vibe requests (use mock_handle_vibe_request)

For most CLI tests, use the cli_test_mocks fixture which provides all three.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli

# The cli_runner and mock_config fixtures are now provided by conftest.py


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Fixture providing a mocked run_kubectl function."""
    with patch("vibectl.command_handler.run_kubectl") as mock:
        # Set up default return value as a Success object
        success_instance = Mock()
        with patch("vibectl.types.Success") as mock_success:
            mock_success.return_value = success_instance
            success_instance.data = "mock kubectl output"
            mock.return_value = success_instance
            yield mock


@pytest.fixture
def mock_handle_command_output() -> Generator[Mock, None, None]:
    """Fixture providing a mocked handle_command_output function."""
    with patch("vibectl.command_handler.handle_command_output") as mock:
        yield mock


@pytest.fixture(scope="module")
def patch_kubectl_and_llm() -> Generator[None, None, None]:
    """Global fixture to ensure kubectl and LLM calls are mocked.

    This fixture patches both the direct import in cli.py and
    the source function in command_handler.py to ensure all
    calls are properly mocked regardless of import path.
    """
    with (
        patch("vibectl.command_handler.run_kubectl") as cli_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cli_mock_handle_output,
        patch("vibectl.command_handler.handle_vibe_request") as cli_mock_handle_vibe,
        patch("vibectl.model_adapter.get_model_adapter") as mock_adapter,
        patch("vibectl.types.Success") as mock_success,
    ):
        # Set up the model adapter mock
        adapter_instance = Mock()
        mock_adapter.return_value = adapter_instance

        # Set up the model mock
        mock_model = Mock()
        adapter_instance.get_model.return_value = mock_model
        adapter_instance.execute.return_value = "Test response"

        # Set up kubectl mocks to return success by default
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "kubectl result"
        cli_mock_run_kubectl.return_value = success_instance

        # Set up handler mocks for command_output and vibe_request
        output_success = Mock()
        output_success.data = "command output result"
        cli_mock_handle_output.return_value = output_success

        vibe_success = Mock()
        vibe_success.data = "vibe result"
        cli_mock_handle_vibe.return_value = vibe_success

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
            patch("vibectl.types.Success") as mock_success,
        ):
            # Set up mock return value to return a Success object
            success_instance = Mock()
            mock_success.return_value = success_instance
            success_instance.data = "test output"
            cmd_mock_run_kubectl.return_value = success_instance

            # Make handle_command_output return a Success object
            cmd_mock_handle_output.return_value = success_instance

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


def test_get_no_output(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command when kubectl returns no output."""
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
        cmd_mock_handle_output.return_value = success_instance

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
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,  # Add Success mock
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

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


def test_get_with_show_kubectl_flag(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with show_kubectl flag."""
    with (
        patch(
            "vibectl.subcommands.get_cmd.configure_output_flags"
        ) as mock_configure_flags,
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,  # Add Success mock
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

        # Mock the configure_output_flags function
        mock_configure_flags.return_value = Mock(
            show_raw=False, show_vibe=True, warn_no_output=True, model_name="test-model"
        )

        result = cli_runner.invoke(
            cli,
            [
                "get",
                "pods",
                "--show-kubectl",
            ],
        )

        # Check results
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


def test_get_with_no_show_kubectl_flag(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
) -> None:
    """Test get command with no_show_kubectl flag."""
    with (
        patch(
            "vibectl.subcommands.get_cmd.configure_output_flags"
        ) as mock_configure_flags,
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
        patch("vibectl.types.Success") as mock_success,  # Add Success mock
    ):
        # Set up mock return value to return a Success object
        success_instance = Mock()
        mock_success.return_value = success_instance
        success_instance.data = "test output"
        cmd_mock_run_kubectl.return_value = success_instance

        # Make handle_command_output return a Success object
        cmd_mock_handle_output.return_value = success_instance

        # Mock the configure_output_flags function
        mock_configure_flags.return_value = Mock(
            show_raw=False, show_vibe=True, warn_no_output=True, model_name="test-model"
        )

        result = cli_runner.invoke(
            cli,
            [
                "get",
                "pods",
                "--no-show-kubectl",
            ],
        )

        # Check results
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(["get", "pods"], capture=True)


@patch("vibectl.subcommands.get_cmd.handle_vibe_request")
def test_get_vibe_request(mock_handle_vibe_get: Mock, cli_runner: CliRunner) -> None:
    """Test get command with vibe request."""
    result = cli_runner.invoke(cli, ["get", "vibe", "show", "me", "all", "pods"])
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "show me all pods"
    assert kwargs["command"] == "get"


def test_get_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test get vibe command without a request."""
    with patch("vibectl.console.console_manager"):
        result = cli_runner.invoke(cli, ["get", "vibe"])
        assert result.exit_code == 1
        assert "Error: Missing request after 'vibe'" in result.output


def test_get_error_handling(cli_runner: CliRunner, mock_run_kubectl: Mock) -> None:
    """Test get command error handling."""
    # Patch handle_standard_command instead of run_kubectl to use the new Result type
    with patch(
        "vibectl.subcommands.get_cmd.handle_standard_command"
    ) as mock_handle_standard:
        # Set up mock to return an Error
        from vibectl.types import Error

        mock_error = Error(error="Test error")
        mock_handle_standard.return_value = mock_error

        # Invoke the CLI and test error handling
        result = cli_runner.invoke(cli, ["get", "pods"])

        # Verify the command was called
        mock_handle_standard.assert_called_once()

        # Check that the command failed with a non-zero exit code
        assert result.exit_code != 0


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
        Exception("Failed to get instructions"),  # custom_instructions
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


@patch("vibectl.cli.validate_model_key_on_startup")
@patch("vibectl.cli.console_manager")
@patch("vibectl.cli.Config")
def test_cli_validates_model_key_on_startup(
    mock_config_class: Mock,
    mock_console: Mock,
    mock_validate: Mock,
    cli_runner: CliRunner,
    patch_kubectl_and_llm: Any,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
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
    patch_kubectl_and_llm: Any,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
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


@patch("vibectl.cli.Config")
def test_warn_no_proxy_config(mock_config_class: Mock, cli_runner: CliRunner) -> None:
    """Test setting and unsetting warn_no_proxy configuration."""
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Test setting to false
    result = cli_runner.invoke(cli, ["config", "set", "warn_no_proxy", "false"])
    assert result.exit_code == 0
    mock_config.set.assert_called_with("warn_no_proxy", "false")
    mock_config.save.assert_called()

    # Reset mock for next test
    mock_config.reset_mock()

    # Test setting to true
    result = cli_runner.invoke(cli, ["config", "set", "warn_no_proxy", "true"])
    assert result.exit_code == 0
    mock_config.set.assert_called_with("warn_no_proxy", "true")
    mock_config.save.assert_called()

    # Reset mock for next test
    mock_config.reset_mock()

    # Test unsetting (should revert to default of True)
    result = cli_runner.invoke(cli, ["config", "unset", "warn_no_proxy"])
    assert result.exit_code == 0
    mock_config.unset.assert_called_with("warn_no_proxy")


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_passthrough_dash_n_after_resource(
    mock_config: Mock, mock_subprocess_run: Mock
) -> None:
    """Test 'just' passthrough: vibectl just get pods -n sandbox"""
    mock_config.return_value.get.return_value = None
    result = CliRunner().invoke(cli, ["just", "get", "pods", "-n", "sandbox"])
    assert result.exit_code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "get", "pods", "-n", "sandbox"],
        check=True,
        text=True,
        capture_output=True,
    )


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_passthrough_dash_n_before_resource(
    mock_config: Mock, mock_subprocess_run: Mock
) -> None:
    """Test 'just' passthrough: vibectl just -n sandbox get pods"""
    mock_config.return_value.get.return_value = None
    result = CliRunner().invoke(cli, ["just", "-n", "sandbox", "get", "pods"])
    assert result.exit_code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "-n", "sandbox", "get", "pods"],
        check=True,
        text=True,
        capture_output=True,
    )


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_passthrough_dash_n_between_resource(
    mock_config: Mock, mock_subprocess_run: Mock
) -> None:
    """Test 'just' passthrough: vibectl just get -n sandbox pods"""
    mock_config.return_value.get.return_value = None
    result = CliRunner().invoke(cli, ["just", "get", "-n", "sandbox", "pods"])
    assert result.exit_code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "get", "-n", "sandbox", "pods"],
        check=True,
        text=True,
        capture_output=True,
    )


@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
def test_just_passthrough_namespace_long_flag(
    mock_config: Mock, mock_subprocess_run: Mock
) -> None:
    """Test 'just' passthrough: vibectl just get pods --namespace sandbox"""
    mock_config.return_value.get.return_value = None
    result = CliRunner().invoke(cli, ["just", "get", "pods", "--namespace", "sandbox"])
    assert result.exit_code == 0
    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "get", "pods", "--namespace", "sandbox"],
        check=True,
        text=True,
        capture_output=True,
    )
