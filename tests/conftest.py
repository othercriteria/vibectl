"""
Fixtures for pytest.

This file contains fixtures that can be used across all tests.
"""

import os
from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner
from rich.console import Console

from vibectl.command_handler import OutputFlags
from vibectl.config import Config
from vibectl.console import ConsoleManager
from vibectl.memory import clear_memory


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Fixture providing patched run_kubectl function for all tests."""
    # We need to patch BOTH the CLI import AND the command_handler module
    # The CLI imports from command_handler, and most tests call the CLI module directly
    with (
        patch("vibectl.command_handler.run_kubectl") as cli_mock,
        patch("vibectl.command_handler.run_kubectl") as handler_mock,
    ):
        # Set up default mock behavior for successful cases
        handler_mock.return_value = "test output"
        cli_mock.return_value = "test output"

        # Create a special side_effect that intelligently handles different cases
        def mock_side_effect(
            cmd: list[str], capture: bool = False, config: object = None
        ) -> str | None:
            # Default success case
            return "test output"

        # Make the CLI mock delegate to the handler mock to ensure consistent behavior
        handler_mock.side_effect = mock_side_effect
        cli_mock.side_effect = handler_mock

        # Return the handler mock since that's the one that gets used by the CLI code
        yield handler_mock


@pytest.fixture
def mock_handle_command_output() -> Generator[Mock, None, None]:
    """Fixture providing patched handle_command_output function for all tests."""
    # Again patch both paths for consistency
    with (
        patch("vibectl.command_handler.handle_command_output") as cli_mock,
        patch("vibectl.command_handler.handle_command_output") as handler_mock,
    ):
        # Keep calls in sync
        # Return handler_mock as that's the implementation used
        cli_mock.side_effect = handler_mock
        yield handler_mock


@pytest.fixture
def test_console() -> ConsoleManager:
    """Fixture providing a ConsoleManager instance for testing.

    This instance has the console and error_console properties set to record
    output for verification in tests.
    """
    console_manager = ConsoleManager()
    # Get theme and create new Console instances that record output
    theme = console_manager.themes["default"]
    console_manager.console = Console(record=True, theme=theme)
    console_manager.error_console = Console(stderr=True, record=True, theme=theme)
    return console_manager


@pytest.fixture(autouse=True, scope="session")
def ensure_test_config_env(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    """Ensure all tests use a separate config directory.

    This prevents tests from interfering with the user's actual configuration.
    """
    # Create a dedicated test config directory
    config_dir = tmp_path_factory.mktemp("vibectl-test-config")

    # Save the original environment
    old_config_dir = os.environ.get("VIBECTL_CONFIG_DIR")

    # Set the test config directory
    os.environ["VIBECTL_CONFIG_DIR"] = str(config_dir)

    try:
        yield
    finally:
        # Restore the original environment
        if old_config_dir:
            os.environ["VIBECTL_CONFIG_DIR"] = old_config_dir
        else:
            if "VIBECTL_CONFIG_DIR" in os.environ:
                del os.environ["VIBECTL_CONFIG_DIR"]


@pytest.fixture
def mock_config() -> Generator[Mock, None, None]:
    """Provide a mocked Config instance."""
    with patch("vibectl.command_handler.Config") as mock_config_class:
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        yield mock_config


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Provide a mocked ConsoleManager instance."""
    with patch("vibectl.command_handler.console_manager") as mock_console:
        yield mock_console


@pytest.fixture
def mock_subprocess(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock subprocess.run to prevent execution of actual commands.

    This fixture provides a consistent mock for subprocess.run across all tests.
    The mock is configured with default successful output and can be customized
    for specific test needs.

    Returns:
        Mock: Mocked subprocess.run function that returns a successful result.
            Default values:
            - stdout: "test output"
            - stderr: ""
            - returncode: 0
    """
    mock = MagicMock()
    mock_process = Mock()
    mock_process.stdout = "test output"
    mock_process.stderr = ""
    mock_process.returncode = 0
    mock.return_value = mock_process
    monkeypatch.setattr("subprocess.run", mock)
    return mock


@pytest.fixture
def mock_configure_output_flags() -> Generator[Mock, None, None]:
    """Mock the configure_output_flags function for control over flags.

    Returns:
        Mock: Mocked configure_output_flags function that returns OutputFlags instance.
    """
    with patch("vibectl.command_handler.configure_output_flags") as mock:
        # Return an OutputFlags instance instead of a tuple
        mock.return_value = OutputFlags(
            show_raw=False,
            show_vibe=True,
            warn_no_output=True,
            model_name="claude-3.7-sonnet",
        )
        yield mock


@pytest.fixture
def cli_test_mocks() -> Generator[tuple[Mock, Mock, Mock, Mock], None, None]:
    """Provide common mocks required for CLI tests to prevent unmocked calls."""
    with (
        patch("vibectl.command_handler.run_kubectl") as mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
        patch("vibectl.command_handler.handle_vibe_request") as mock_handle_vibe_cli,
        patch(
            "vibectl.subcommands.get_cmd.handle_vibe_request"
        ) as mock_handle_vibe_get,
    ):
        # Default to successful output
        mock_run_kubectl.return_value = "test output"

        # Helper for setting up error responses
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            mock_run_kubectl.return_value = (
                f"Error: {stderr}" if stderr else "Error: Command failed"
            )

        # Add the helper method to the mock
        mock_run_kubectl.set_error_response = set_error_response

        # Remove the shared side effect; let each mock be independent
        yield (
            mock_run_kubectl,
            mock_handle_output,
            mock_handle_vibe_cli,
            mock_handle_vibe_get,
        )


@pytest.fixture
def mock_run_kubectl_for_cli() -> Generator[Mock, None, None]:
    """Fixture providing patched run_kubectl function specifically for CLI tests."""
    with patch("vibectl.command_handler.run_kubectl") as mock:
        # Set up default mock behavior
        mock.return_value = "test output"

        # Helper for setting up error responses
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            mock.return_value = (
                f"Error: {stderr}" if stderr else "Error: Command failed"
            )

        # Add the helper method to the mock
        mock.set_error_response = set_error_response

        yield mock


@pytest.fixture
def mock_handle_output_for_cli() -> Generator[Mock, None, None]:
    """Fixture providing patched handle_command_output function specifically
    for CLI tests."""
    with patch("vibectl.command_handler.handle_command_output") as mock:
        yield mock


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Create a test configuration instance with a temporary directory.

    This ensures tests don't interfere with the user's actual configuration.

    Args:
        tmp_path: Pytest fixture providing a temporary directory path

    Returns:
        Config: A Config instance using a temporary directory
    """
    return Config(base_dir=tmp_path / "vibectl-test-config")


@pytest.fixture
def cli_runner(tmp_path: Path) -> CliRunner:
    """Fixture providing a Click CLI test runner with isolation.

    This ensures CLI tests don't modify the user's actual configuration.

    Args:
        tmp_path: Pytest fixture providing a temporary directory path

    Returns:
        CliRunner: A Click test runner with an isolated environment
    """
    # No need to set VIBECTL_CONFIG_DIR as it's already set by ensure_test_config_env
    return CliRunner()


@pytest.fixture
def mock_llm() -> Generator[MagicMock, None, None]:
    """Mock the LLM model for testing.

    This fixture provides a complete mock of the LLM functionality including:
    - Mock LLM module
    - Mock model with response handling
    - Mock adapter with proper interface
    """
    with (
        patch("vibectl.model_adapter.get_model_adapter") as mock_get_adapter,
        patch("vibectl.command_handler.get_model_adapter") as cmd_mock_get_adapter,
    ):
        # Create a mock adapter that implements ModelAdapter
        mock_adapter = Mock()

        # Set up the get_model method to return a mock model
        def get_model(model_name: str) -> Mock:
            # Create a mock model with proper response handling
            mock_model = Mock()

            # Set up the prompt method to handle different test scenarios
            def model_prompt(prompt_text: str) -> Mock:
                # Create a mock response that implements ModelResponse
                mock_response = Mock()

                # Set up the text method based on the prompt
                def get_text() -> str:
                    if "empty response test" in prompt_text:
                        return ""
                    elif "error test" in prompt_text:
                        return "ERROR: Test error"
                    elif "yaml test" in prompt_text:
                        return "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod"
                    elif "{command}" in prompt_text:
                        # Handle command parameter in prompt
                        return "Test response"
                    else:
                        return "Test response"

                mock_response.text = Mock(side_effect=get_text)
                return mock_response

            mock_model.prompt = Mock(side_effect=model_prompt)
            return mock_model

        # Configure the adapter mock
        mock_adapter.get_model = Mock(side_effect=get_model)

        # Set up the adapter's execute method to handle different test scenarios
        def adapter_execute(model: Mock, prompt_text: str) -> str:
            response = model.prompt(prompt_text)
            if hasattr(response, "text"):
                from typing import Protocol, cast

                class ResponseWithText(Protocol):
                    def text(self) -> str: ...

                return cast("ResponseWithText", response).text()
            return str(response)

        mock_adapter.execute = Mock(side_effect=adapter_execute)

        # Set up both mocks to return the same adapter
        mock_get_adapter.return_value = mock_adapter
        cmd_mock_get_adapter.return_value = mock_adapter

        yield mock_adapter


@pytest.fixture
def mock_summary_prompt() -> Callable[[], str]:
    """Mock summary prompt function."""
    return lambda: "Test Prompt: {output}"


@pytest.fixture
def prevent_exit() -> Generator[MagicMock, None, None]:
    """Prevent sys.exit from exiting the tests.

    This fixture is useful for testing error cases where sys.exit would normally
    terminate the test.
    """
    with patch("sys.exit") as mock_exit:
        yield mock_exit


@pytest.fixture
def mock_kubectl_output() -> str:
    """Mock kubectl output for testing."""
    return "test output"


@pytest.fixture
def standard_output_flags() -> "OutputFlags":
    """Provide a standard set of OutputFlags for tests.

    Returns:
        OutputFlags: Standard output flags configuration for testing.
    """
    return OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-sonnet",
        show_kubectl=False,
    )


@pytest.fixture
def mock_output_flags_for_vibe_request() -> "OutputFlags":
    """Provide OutputFlags specifically for vibe request tests.

    Returns:
        OutputFlags: Output flags configuration for vibe request tests.
    """
    return OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-sonnet",
        show_kubectl=False,
    )


@pytest.fixture
def mock_memory() -> Generator[MagicMock, None, None]:
    """Mock memory functions to avoid actual LLM API calls.

    This fixture prevents actual API calls to LLMs during tests, which would:
    - Add cost for each test run
    - Make tests flaky due to API dependencies
    - Significantly slow down test execution

    Memory functions involve both file operations and LLM calls, but the LLM calls
    are the primary concern for test stability and performance.
    """
    with (
        patch("vibectl.command_handler.update_memory") as mock_update_memory,
        patch("vibectl.memory.get_memory") as mock_get_memory,
        patch("vibectl.memory.include_memory_in_prompt") as mock_include_memory,
    ):
        # Set default return values
        mock_get_memory.return_value = "Test memory context"

        # Make include_memory_in_prompt just return the original prompt
        mock_include_memory.side_effect = lambda prompt_func: prompt_func()

        yield mock_update_memory


@pytest.fixture(autouse=True)
def no_coroutine_warnings() -> Generator[None, None, None]:
    """Suppress RuntimeWarning about coroutines never being awaited."""
    import warnings

    # Save original filters as a list
    original_filters = list(warnings.filters)

    # Suppress coroutine warnings using the specific filter pattern
    warnings.filterwarnings("ignore", message="coroutine '.*' was never awaited")

    yield

    # Restore original filters
    warnings.filters = original_filters


@pytest.fixture
def mock_command_handler_logger() -> Generator[Mock, None, None]:
    """Patch the logger in vibectl.command_handler for logging assertions."""
    from vibectl import command_handler

    with patch.object(command_handler, "logger") as mock_logger:
        yield mock_logger


@pytest.fixture(autouse=True)
def reset_memory() -> Generator[None, None, None]:
    clear_memory()
    yield
    clear_memory()


@pytest.fixture
def mock_run_kubectl_version_cmd() -> Generator[Mock, None, None]:
    with patch("vibectl.subcommands.version_cmd.run_kubectl") as mock:
        yield mock


@pytest.fixture
def mock_handle_command_output_version_cmd() -> Generator[Mock, None, None]:
    with patch("vibectl.subcommands.version_cmd.handle_command_output") as mock:
        yield mock


@pytest.fixture
def mock_model_adapter_logger() -> Generator[Mock, None, None]:
    """Patch the logger in vibectl.model_adapter for logging assertions."""
    import vibectl.model_adapter as model_adapter

    with patch.object(model_adapter, "logger") as mock_logger:
        yield mock_logger
