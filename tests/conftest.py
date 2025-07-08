"""
Fixtures for pytest.

This file contains fixtures that can be used across all tests.
"""

import os
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
)
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture
from rich.console import Console

from vibectl.command_handler import OutputFlags
from vibectl.config import Config
from vibectl.console import ConsoleManager
from vibectl.model_adapter import StreamingMetricsCollector
from vibectl.types import Error, LLMMetrics, MetricsDisplayMode, Success

# Define UnknownModelError at the module level if it can't be imported
try:
    from llm import UnknownModelError  # type: ignore
except ImportError:
    # Fallback if direct import fails or for older llm versions
    class UnknownModelError(Exception):  # type: ignore
        pass


import asyncio  # Added for new async test helpers


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
        handler_mock.return_value = Success(data="test output")
        cli_mock.return_value = Success(data="test output")

        # Create a special side_effect that intelligently handles different cases
        def mock_side_effect(
            cmd: list[str], capture: bool = False, config: object = None
        ) -> Success:
            # Default success case
            return Success(data="test output")

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
        # Set default return value to be a Success object
        handler_mock.return_value = Success(data="test output")

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
        mock_config_instance = Mock(spec=Config)

        def custom_get(key: str, default: Any = None) -> Any:
            if key == "memory_max_chars":
                return default
            return default if default is not None else Mock()

        mock_config_instance.get.side_effect = custom_get

        mock_config_class.return_value = mock_config_instance
        yield mock_config_instance


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
def mock_configure_output_flags(mocker: MockerFixture) -> Generator[Mock, None, None]:
    """Mock the configure_output_flags function for control over flags.

    Returns:
        Mock: Mocked configure_output_flags function that returns OutputFlags instance.
    """
    mock = mocker.patch("vibectl.command_handler.configure_output_flags")
    mock.return_value = OutputFlags(
        show_vibe=True,
        show_metrics=MetricsDisplayMode.ALL,
        show_raw_output=False,
        show_kubectl=False,
        warn_no_output=True,
        model_name="test-model",
        warn_no_proxy=True,
    )
    yield mock


@pytest.fixture
def mock_configure_memory_flags() -> Generator[Mock, None, None]:
    """Mock the configure_memory_flags function."""
    # The function is defined in vibectl.memory
    with patch("vibectl.memory.configure_memory_flags") as mock:
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
        mock_run_kubectl.return_value = Success(data="test output")
        mock_handle_output.return_value = Success(data="test output")
        mock_handle_vibe_cli.return_value = Success(data="test vibe output")
        mock_handle_vibe_get.return_value = Success(data="test vibe output")

        # Helper for setting up error responses
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            error_msg = stderr if stderr else "Command failed"
            mock_run_kubectl.return_value = Error(error=error_msg)

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
    with (
        patch("vibectl.command_handler.run_kubectl") as mock,
        patch("vibectl.command_handler.get_model_adapter") as mock_get_adapter_func,
        patch("vibectl.model_adapter.get_model") as mock_model_adapter_get_model,
        patch("vibectl.command_handler.model_adapter.get_model") as mock_cmd_model_get,
        patch(
            "vibectl.command_handler._process_vibe_output", new_callable=AsyncMock
        ) as mock_process_vibe,
    ):
        # Set up default mock behavior
        mock.return_value = Success(data="test output")

        # Provide a lightweight stub adapter that satisfies get_model but
        # does minimal work
        stub_adapter = MagicMock(name="cli_stub_model_adapter")

        # get_model returns a simple Mock to satisfy downstream calls
        stub_adapter.get_model.return_value = Mock(name="stub-llm-model")

        # execute_and_log_metrics returns a successful dummy tuple to bypass
        # real parsing
        stub_adapter.execute_and_log_metrics = AsyncMock(
            return_value=(
                '{"action": {"action_type": "THOUGHT", "text": "noop"}}',
                None,
            )
        )

        mock_get_adapter_func.return_value = stub_adapter

        # Helper for setting up error responses
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            error_msg = stderr if stderr else "Command failed"
            mock.return_value = Error(error=error_msg)

        # Add the helper method to the mock
        mock.set_error_response = set_error_response

        # The direct helper used by _process_vibe_output bypasses
        # get_model_adapter and calls vibectl.model_adapter.get_model(...)
        # directly.  Patch this to return a stub model so that wait command
        # tests do not attempt to resolve real model names.
        mock_model_adapter_get_model.return_value = Mock(name="stub-llm-model-direct")

        mock_cmd_model_get.return_value = mock_model_adapter_get_model.return_value

        mock_process_vibe.return_value = (
            None  # Skip vibe processing during wait CLI tests
        )

        yield mock


@pytest.fixture
def mock_get_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter factory at vibectl.model_adapter.get_model_adapter,
    vibectl.command_handler.get_model_adapter, and
    vibectl.execution.vibe.get_model_adapter.
    Yields the mock adapter INSTANCE.
    """
    # Create a mock adapter instance that will be returned by the patched factories
    mock_adapter_instance = MagicMock()

    # Set up a default mock model object that the adapter instance's get_model
    # will return
    default_mock_model = Mock(name="mock-llm-model-from-adapter-fixture")

    def get_model_side_effect(model_name_arg: str) -> Mock:
        """Return a mock model for *any* requested model name.

        Tests may request assorted model names (e.g. "claude-3.7-sonnet") via
        CLI flags or default settings.  Rather than enumerating every possible
        string we simply return a fresh ``Mock`` instance for unknown names to
        avoid raising ``UnknownModelError`` and keep the tests isolated from
        the real model registry.
        """
        if model_name_arg in {"test-model", "mock-llm-model-from-adapter-fixture"}:
            return (
                default_mock_model
                if model_name_arg != "test-model"
                else Mock(name="test-model")
            )

        # For any other model name, return a generic mock model instance so
        # that code paths depending on a model can proceed without hitting the
        # real LLM registry.
        return Mock(name=f"mock-model-{model_name_arg}")

    mock_adapter_instance.get_model.side_effect = get_model_side_effect

    # CRITICAL: Mock async methods with AsyncMock
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=(
            "Default mock LLM response",
            LLMMetrics(
                token_input=10,
                token_output=20,
                latency_ms=100,
                total_processing_duration_ms=120,
            ),
        )
    )

    # Setup for stream_execute
    # stream_execute should be a AsyncMock that returns an async iterator.
    mock_adapter_instance.stream_execute = AsyncMock(
        name="stream_execute_mock_on_adapter_instance"
    )

    # Setup for stream_execute_and_log_metrics
    # stream_execute_and_log_metrics should return a tuple of (async iterator, metrics)
    mock_adapter_instance.stream_execute_and_log_metrics = AsyncMock(
        name="stream_execute_and_log_metrics_mock_on_adapter_instance"
    )

    async def default_async_stream_generator() -> AsyncIterator[str]:
        # Default stream for tests if not overridden in a specific test
        yield "Stream chunk 1"
        yield "Stream chunk 2"

    # When mock_adapter_instance.stream_execute is called, it should return an
    # actual async iterator.
    mock_adapter_instance.stream_execute.return_value = default_async_stream_generator()

    # When mock_adapter_instance.stream_execute_and_log_metrics is called,
    # it should return a tuple of (async iterator, StreamingMetricsCollector)
    # for metrics
    async def default_async_stream_generator_for_metrics() -> AsyncIterator[str]:
        # Default stream for tests if not overridden in a specific test
        yield "Stream chunk 1"
        yield "Stream chunk 2"

    # Import and create a proper StreamingMetricsCollector mock
    # Create mock metrics collector
    mock_metrics_collector = MagicMock(spec=StreamingMetricsCollector)
    mock_metrics_collector.get_metrics = AsyncMock(return_value=LLMMetrics())
    mock_metrics_collector.is_completed = True

    mock_adapter_instance.stream_execute_and_log_metrics.return_value = (
        default_async_stream_generator_for_metrics(),
        mock_metrics_collector,
    )

    with (
        patch(
            "vibectl.model_adapter.get_model_adapter",
            return_value=mock_adapter_instance,
        ),
        patch(
            "vibectl.command_handler.get_model_adapter",
            return_value=mock_adapter_instance,
        ),
        patch(
            "vibectl.execution.vibe.get_model_adapter",
            return_value=mock_adapter_instance,
        ),
        patch("vibectl.memory.get_model_adapter", return_value=mock_adapter_instance),
        # Add other paths if get_model_adapter is imported elsewhere directly
    ):
        yield mock_adapter_instance


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
        def adapter_execute(model: Mock, prompt_text: str, **kwargs: Any) -> str:
            """Simulate execution, return text or error, accept extra kwargs."""
            # Check for forced error attribute on the mock model
            if isinstance(model, Mock) and hasattr(model, "force_error"):
                return "ERROR: Test error"
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
def mock_summary_prompt() -> Callable[..., str]:
    """Mock summary prompt function that safely ignores extra parameters."""

    def _prompt(*_args: Any, **_kwargs: Any) -> str:  # Accepts any params
        return "Test Prompt: {output}"

    return _prompt


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


@pytest.fixture(scope="session")
def default_output_flags() -> OutputFlags:
    """Provides a default OutputFlags instance for tests."""
    return OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.ALL,
        show_kubectl=True,
        warn_no_proxy=True,
    )


@pytest.fixture(scope="session")
def no_vibe_output_flags() -> OutputFlags:
    """Provides an OutputFlags instance with show_vibe=False."""
    return OutputFlags(
        show_vibe=False,
        show_metrics=MetricsDisplayMode.ALL,
        show_raw_output=True,
        show_kubectl=False,
        warn_no_output=True,
        model_name="test-model",
        warn_no_proxy=True,
    )


@pytest.fixture
def mock_memory(mocker: MockerFixture) -> Generator[dict[str, Mock], None, None]:
    """Mock for memory functions to avoid file I/O operations in tests.

    Use this fixture in tests that need to verify memory operations
    instead of using real memory functions.
    """
    # Create a regular Mock instead of AsyncMock for async functions
    # We'll handle the async nature in the side_effect
    the_mock_update_function = AsyncMock(name="shared_update_memory_mock")

    # Configure the mock to return proper LLMMetrics when called
    # This ensures that when update_memory is called, it returns metrics
    # with proper types
    async def update_memory_side_effect(*args: Any, **kwargs: Any) -> LLMMetrics:
        from vibectl.types import LLMMetrics

        return LLMMetrics(
            token_input=0,
            token_output=0,
            latency_ms=0.0,  # Ensure this is a float, not a mock
            total_processing_duration_ms=0.0,
        )

    the_mock_update_function.side_effect = update_memory_side_effect

    # Patch at source and common usage points
    mocker.patch("vibectl.memory.update_memory", new=the_mock_update_function)
    mocker.patch("vibectl.execution.vibe.update_memory", new=the_mock_update_function)
    mocker.patch(
        "vibectl.command_handler.update_memory",
        new=the_mock_update_function,
        create=True,
    )  # create=True if it might not exist

    mock_get = mocker.patch("vibectl.memory.get_memory")
    mock_set = mocker.patch("vibectl.memory.set_memory")
    mock_clear = mocker.patch("vibectl.memory.clear_memory")

    mock_get.return_value = ""  # Default to empty memory

    yield {
        "set": mock_set,
        "get": mock_get,
        "clear": mock_clear,
        "update": the_mock_update_function,  # Return the shared mock for assertions
    }


@pytest.fixture(autouse=True)
def reset_memory(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Reset memory between tests without file I/O.

    This optimized version does not actually write to the config file,
    making it much faster than the original implementation.

    For tests marked with @pytest.mark.fast, memory reset is skipped entirely.
    """
    # Skip memory reset for tests marked as "fast"
    if request.node.get_closest_marker("fast"):
        yield
        return

    from unittest.mock import patch

    from vibectl.memory import clear_memory, set_memory

    # Use the original clear_memory function for tests that expect it to work properly
    # This ensures tests that directly test clear_memory functionality still pass
    if "test_memory" in request.node.nodeid or "test_config" in request.node.nodeid:
        clear_memory()
        yield
        clear_memory()
        return

    # For all other tests, use the optimized version with no file I/O
    with patch("vibectl.config.Config._save_config"):
        from vibectl.config import Config

        config = Config()
        set_memory("", config)
        yield


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


@pytest.fixture
def memory_mock() -> Generator[dict[str, Mock], None, None]:
    """Mock for memory functions to avoid file I/O operations in tests.

    Use this fixture in tests that need to verify memory operations
    instead of using real memory functions.
    """
    with (
        patch("vibectl.memory.set_memory") as mock_set_memory,
        patch("vibectl.memory.get_memory") as mock_get_memory,
        patch("vibectl.memory.clear_memory") as mock_clear_memory,
        patch("vibectl.memory.update_memory") as mock_update_memory,
    ):
        # Setup default returns
        mock_get_memory.return_value = "Mocked memory content"

        yield {
            "set": mock_set_memory,
            "get": mock_get_memory,
            "clear": mock_clear_memory,
            "update": mock_update_memory,
        }


@pytest.fixture
def in_memory_config() -> Generator[Config, None, None]:
    """Create a Config instance that doesn't perform file I/O.

    This fixture provides a Config object that has been patched to avoid
    all file operations, making it much faster for tests that need Config
    but don't need to persist changes to disk.
    """
    from unittest.mock import patch

    from vibectl.config import Config

    # Create a config in memory with patched file operations
    with patch.object(Config, "_save_config", return_value=None):
        # Create config with initialization but no file operations
        config = Config()
        yield config


@pytest.fixture
def fast_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Callable[..., Awaitable[None]], None, None]:
    """Replace asyncio.sleep with an awaitable noop that yields control once.

    This avoids real delays while keeping the coroutine awaitable, so tests run
    quickly without RuntimeWarning for un-awaited coroutines.
    """
    orig_sleep = asyncio.sleep  # Capture original before patching

    async def _fast_sleep(delay: float, *args: Any, **kwargs: Any) -> None:
        """A drop-in replacement for asyncio.sleep that returns after one loop tick."""
        # Yield control to the scheduler briefly
        await orig_sleep(0)

    # Apply patch for the duration of the test
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    yield _fast_sleep  # Make replacement accessible to tests if needed
    # monkeypatch automatically restores the original function on fixture teardown


@pytest.fixture
async def background_tasks() -> AsyncGenerator[list[asyncio.Task[Any]], None]:
    """Fixture that tracks asyncio tasks and ensures they are cleaned up.

    Tests should append any long-lived tasks created with asyncio.create_task
    to the returned list.  After the test, all tasks are cancelled/awaited to
    prevent leaks and spurious warnings.
    """
    tasks: list[asyncio.Task] = []
    try:
        yield tasks
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# --------------------------------------------------------------------------------------
# Temporary compatibility alias for get_model_adapter after removal from vibe module.
# This sets the attribute ONLY within the test environment so existing patch() targets
# still resolve.  Production code no longer relies on this alias.
# --------------------------------------------------------------------------------------
import importlib  # noqa: E402

try:
    vibe_module = importlib.import_module("vibectl.execution.vibe")
    if not hasattr(vibe_module, "get_model_adapter"):  # type: ignore[attr-defined]
        from vibectl.model_adapter import get_model_adapter as _get_model_adapter

        # Expose as attribute for legacy patch targets used by tests.
        vibe_module.get_model_adapter = _get_model_adapter  # type: ignore[attr-defined]

    # Ensure the central path used by run_llm routes via the vibe alias so
    # tests that patch "vibectl.execution.vibe.get_model_adapter" continue to
    # intercept the call.
    # Use a delegating wrapper so that if tests patch vibe_module.get_model_adapter
    # AFTER this code runs, subsequent calls from run_llm (which re-import the
    # symbol fresh each invocation) will still flow through the patched object.
    from typing import Any

    import vibectl.model_adapter as _model_adapter_mod

    def _delegating_get_adapter(*args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        return vibe_module.get_model_adapter(*args, **kwargs)  # type: ignore[attr-defined]

    _model_adapter_mod.get_model_adapter = _delegating_get_adapter  # type: ignore[attr-defined]
except ModuleNotFoundError:  # Defensive: should never happen in test env
    pass
