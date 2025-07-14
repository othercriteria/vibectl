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
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import DEFAULT_CONFIG
from vibectl.types import Error, Success

# The cli_runner and mock_config fixtures are now provided by conftest.py


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Fixture providing a mocked run_kubectl function."""
    with patch("vibectl.command_handler.run_kubectl") as mock:
        # Set up default return value as a Success object
        success_instance = Success(data="mock kubectl output")
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


# Test functions for main CLI behavior and entry point


# Test initialization logic via main() entry point
@pytest.mark.asyncio
@patch("vibectl.model_adapter.validate_model_key_on_startup")
@patch("vibectl.console.console_manager")  # Patch console_manager instance
@patch("vibectl.config.Config")  # Patch Config class
@patch("vibectl.cli.init_logging")  # Patch where it's looked up (in cli.py)
async def test_cli_init_with_theme(
    mock_init_logging: Mock,
    mock_config_class: Mock,
    mock_console_manager: Mock,  # Patches the instance
    mock_validate: Mock,
) -> None:
    """Test CLI group initialization uses default theme via CliRunner."""
    # Setup Config mock instance behavior
    mock_config_instance = Mock()
    mock_config_class.return_value = mock_config_instance
    # Simulate config returning None for theme, triggering default usage
    mock_config_instance.get.side_effect = (
        lambda key, default=None: None
        if key == "theme"
        else DEFAULT_CONFIG["llm"]["model"]
        if key == "model"
        else DEFAULT_CONFIG.get(key, default)
    )  # Fallback to actual defaults

    # Setup validate mock
    mock_validate.return_value = None  # Simulate valid key (no warning)

    # Import the cli group object itself

    # Create async CLI runner directly for this test
    async_cli_runner = CliRunner()

    # Invoke the CLI without any subcommand using AsyncClick's async runner
    result = await async_cli_runner.invoke(cli)  # type: ignore[arg-type] # No args means no subcommand

    # Assertions
    assert result.exit_code == 0  # Should exit cleanly


@pytest.mark.asyncio
@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
async def test_just_general_exception(
    mock_config_class: Mock, mock_subprocess_run: Mock
) -> None:
    """Test just command handling when subprocess.run fails."""
    # Setup mock config get
    mock_config = mock_config_class.return_value
    mock_config.get.return_value = None  # No kubeconfig override
    # Setup subprocess.run to raise an exception
    error = Exception("Subprocess failed")
    mock_subprocess_run.side_effect = error

    # Call the function directly instead of via CLI command
    from vibectl.subcommands.just_cmd import run_just_command

    result = await run_just_command(("get", "pods"))

    # Verify the result is an Error object containing the exception
    assert isinstance(result, Error)
    assert (
        result.error == "Exception in 'just' subcommand"
    )  # Use the actual error message
    assert result.exception is error


@pytest.mark.asyncio
@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
async def test_just_passthrough_dash_n_after_resource(
    mock_config: Mock, mock_subprocess_run: Mock
) -> None:
    """Test 'just' passthrough: vibectl just get pods -n sandbox"""
    mock_config.return_value.get.return_value = None
    # Mock subprocess return value
    mock_subprocess_run.return_value = Mock(
        stdout="pods listed", stderr="", returncode=0
    )

    # Call the function directly instead of via CLI command
    from vibectl.subcommands.just_cmd import run_just_command

    result = await run_just_command(("get", "pods", "-n", "sandbox"))

    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "get", "pods", "-n", "sandbox"],
        check=True,
        text=True,
        capture_output=True,
    )
    # Check the result is Success
    assert isinstance(result, Success)
    assert result.data == "pods listed"


@pytest.mark.asyncio
@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
async def test_just_passthrough_dash_n_before_resource(
    mock_config: Mock, mock_subprocess_run: Mock
) -> None:
    """Test 'just' passthrough: vibectl just -n sandbox get pods"""
    mock_config.return_value.get.return_value = None
    mock_subprocess_run.return_value = Mock(
        stdout="pods listed", stderr="", returncode=0
    )

    # Call the function directly instead of via CLI command
    from vibectl.subcommands.just_cmd import run_just_command

    result = await run_just_command(("-n", "sandbox", "get", "pods"))

    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "-n", "sandbox", "get", "pods"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert isinstance(result, Success)
    assert result.data == "pods listed"


@pytest.mark.asyncio
@patch("vibectl.subcommands.just_cmd.asyncio.to_thread", new_callable=AsyncMock)
@patch("vibectl.subcommands.just_cmd.Config")
async def test_just_passthrough_dash_n_between_resource(
    mock_config: Mock, mock_to_thread: AsyncMock
) -> None:
    """Test 'just' passthrough: vibectl just get -n sandbox pods"""
    mock_config.return_value.get.return_value = None

    # Mock the result of subprocess.run
    mock_subprocess_result = Mock(stdout="pods listed", stderr="", returncode=0)

    # Configure asyncio.to_thread to return the mock result
    async def mock_to_thread_side_effect(func: Any, *args: Any, **kwargs: Any) -> Any:
        if func.__name__ == "run":  # subprocess.run
            return mock_subprocess_result
        return func(*args, **kwargs)

    mock_to_thread.side_effect = mock_to_thread_side_effect

    # Call the function directly instead of via CLI command
    from vibectl.subcommands.just_cmd import run_just_command

    result = await run_just_command(("get", "-n", "sandbox", "pods"))

    mock_to_thread.assert_called_once()
    # Verify the arguments passed to asyncio.to_thread
    call_args = mock_to_thread.call_args
    assert call_args[0][1:] == (  # Skip the function itself, check the args
        ["kubectl", "get", "-n", "sandbox", "pods"],
    )
    assert call_args[1] == {"check": True, "text": True, "capture_output": True}
    assert isinstance(result, Success)
    assert result.data == "pods listed"


@pytest.mark.asyncio
@patch("vibectl.subcommands.just_cmd.subprocess.run")
@patch("vibectl.subcommands.just_cmd.Config")
async def test_just_passthrough_namespace_long_flag(
    mock_config: Mock, mock_subprocess_run: Mock
) -> None:
    """Test 'just' passthrough: vibectl just get pods --namespace sandbox"""
    mock_config.return_value.get.return_value = None
    mock_subprocess_run.return_value = Mock(
        stdout="pods listed", stderr="", returncode=0
    )

    # Call the function directly instead of via CLI command
    from vibectl.subcommands.just_cmd import run_just_command

    result = await run_just_command(("get", "pods", "--namespace", "sandbox"))

    mock_subprocess_run.assert_called_once_with(
        ["kubectl", "get", "pods", "--namespace", "sandbox"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert isinstance(result, Success)
    assert result.data == "pods listed"


def test_cli_no_subcommand_shows_welcome() -> None:
    """Test that the welcome message is only shown when no subcommand is invoked."""
    # Import the function under test
    from vibectl.cli import show_welcome_if_no_subcommand

    # Test both with and without subcommand to verify behavior
    for has_subcommand in [False, True]:
        # Create fresh mocks for each test case
        mock_console = MagicMock()
        mock_logger = MagicMock()

        # Setup mock context
        mock_ctx = MagicMock()
        mock_ctx.invoked_subcommand = "some-command" if has_subcommand else None

        # Patch the dependencies
        with (
            patch("vibectl.cli.console_manager", mock_console),
            patch("vibectl.cli.logger", mock_logger),
        ):
            # Call the function with our mock context
            show_welcome_if_no_subcommand(mock_ctx)

            # Check if welcome message was shown or not based on invoked_subcommand
            if has_subcommand:
                mock_console.print_vibe_welcome.assert_not_called()
            else:
                mock_console.print_vibe_welcome.assert_called_once()
