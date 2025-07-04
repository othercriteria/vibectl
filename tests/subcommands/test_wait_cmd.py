"""Tests for the CLI wait command.

This module tests the CLI wait command of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to kubectl and LLM services.
"""

from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# from click.testing import CliRunner # Old import
from asyncclick.testing import CliRunner  # New import

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags
from vibectl.subcommands import wait_cmd as wait_cmd_module
from vibectl.types import Error, MetricsDisplayMode, Result, Success


@pytest.fixture
def mock_run_kubectl_for_cli() -> Generator[MagicMock, None, None]:
    """Mock run_kubectl to avoid actual kubectl calls.

    This fixture specifically patches both the CLI import path and command_handler path.
    """
    with (
        patch("vibectl.command_handler.run_kubectl") as cli_mock,
        patch("vibectl.command_handler.handle_command_output") as handler_mock,
    ):
        # Set up default responses
        handler_mock.return_value = Success(data="test wait output")
        cli_mock.return_value = Success(data="test wait output")

        # Make CLI mock delegate to handler mock for consistent behavior
        cli_mock.side_effect = handler_mock

        # Add error response helper
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            error_msg = stderr if stderr else "Command failed"
            error_obj = Error(error=error_msg)
            handler_mock.return_value = error_obj
            cli_mock.return_value = error_obj

        handler_mock.set_error_response = set_error_response

        yield handler_mock


@pytest.fixture
def mock_handle_output_for_cli() -> Generator[MagicMock, None, None]:
    """Mock handle_command_output for testing."""
    with (
        patch("vibectl.command_handler.handle_command_output") as cli_mock,
        patch("vibectl.command_handler.handle_command_output") as handler_mock,
    ):
        # Make CLI mock delegate to handler mock
        cli_mock.side_effect = handler_mock

        yield handler_mock


@pytest.fixture
def mock_asyncio_for_wait() -> Generator[MagicMock, None, None]:
    """Mock asyncio functionality for wait command tests to avoid coroutine warnings."""
    # Create a mock event loop
    mock_loop = MagicMock()
    mock_loop.run_until_complete.side_effect = lambda coro: "pod/nginx condition met"
    mock_loop.is_running.return_value = False

    # Create synchronous (non-async) mocks to avoid coroutine warnings
    def mock_sleep(delay: float, *args: Any, **kwargs: Any) -> None:
        """Mock sleep as a regular function to avoid coroutine warnings."""
        return None

    def mock_wait_for(coro: Any, timeout: float) -> Any:
        """Mock wait_for as a regular function to avoid coroutine warnings."""
        return None

    def mock_to_thread(func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Mock to_thread as a regular function to avoid coroutine warnings."""
        return "pod/nginx condition met"

    def mock_create_task(coro: Any) -> MagicMock:
        """Mock create_task to return a MagicMock instead of a Task object."""
        # If we get a coroutine, close it to prevent warnings
        if hasattr(coro, "close"):
            coro.close()
        task = MagicMock()
        task.done.return_value = False
        task.cancel.return_value = None
        task.cancelled.return_value = False
        task.result.return_value = None
        return task

    # Use a patch context manager to replace all asyncio functions we use
    with (
        # Mock asyncio functions
        patch("asyncio.get_event_loop", return_value=mock_loop),
        patch("asyncio.new_event_loop", return_value=mock_loop),
        patch("asyncio.set_event_loop"),
        # Replace all async functions with synchronous versions
        patch("asyncio.sleep", mock_sleep),
        patch("asyncio.wait_for", mock_wait_for),
        patch("asyncio.to_thread", mock_to_thread),
        patch("asyncio.create_task", mock_create_task),
        # Replace asyncio exceptions with regular Exception to avoid awaiting issues
        patch("asyncio.CancelledError", Exception),
        patch("asyncio.TimeoutError", Exception),
        # Also mock any direct asyncio imports in the test module
        patch("asyncio.create_task", mock_create_task),
        patch("asyncio.Future", MagicMock),
    ):
        yield mock_loop


@pytest.fixture
def mock_console(monkeypatch: Any) -> Generator[MagicMock, None, None]:
    """Mock console manager for CLI tests."""
    mock = MagicMock()

    # Add console attribute for direct print calls
    mock.console = MagicMock()

    with (
        patch("vibectl.cli.console_manager", mock),
        patch("vibectl.command_handler.console_manager", mock),
    ):
        yield mock


@pytest.mark.asyncio
async def test_wait_basic(
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with basic arguments."""
    runner = CliRunner()
    from vibectl.types import Success

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = Success(data="pod/nginx condition met")

    # Configure mock_asyncio_for_wait to return our result
    mock_asyncio_for_wait.run_until_complete.return_value = Success(
        data="pod/nginx condition met"
    )

    # Invoke CLI synchronously - pytest-asyncio handles the loop
    result = await runner.invoke(
        cli,  # type: ignore[arg-type]
        ["wait", "pod/nginx", "--for=condition=Ready", "--no-live-display"],
        catch_exceptions=True,  # Ensure click.Exit is caught
    )

    # Check results
    assert result.exit_code == 0
    # Run kubectl will be called via asyncio.to_thread
    mock_handle_output_for_cli.assert_called_once()


@pytest.mark.asyncio
async def test_wait_with_args(
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with additional arguments."""
    runner = CliRunner()
    from vibectl.types import Success

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = Success(data="pod/nginx condition met")

    # Invoke CLI synchronously
    result = await runner.invoke(
        cli,  # type: ignore[arg-type]
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--timeout=30s",
            "-n",
            "default",
            "--no-live-display",
        ],
    )

    # Check results
    assert result.exit_code == 0
    # Run kubectl will be called via asyncio.to_thread
    mock_handle_output_for_cli.assert_called_once()


@patch("vibectl.subcommands.wait_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_wait_with_flags(
    mock_configure_flags: Mock,
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with vibectl-specific flags."""
    runner = CliRunner()
    from vibectl.types import Success

    # Configure output flags
    mock_configure_flags.return_value = OutputFlags(
        show_raw_output=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="claude-3.7-haiku",
        show_metrics=MetricsDisplayMode.ALL,
    )

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = Success(data="pod/nginx condition met")

    # Invoke CLI synchronously
    result = await runner.invoke(
        cli,  # type: ignore[arg-type]
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--show-raw-output",
            "--model",
            "claude-3.7-haiku",
            "--no-live-display",
        ],
    )

    # Check results
    assert result.exit_code == 0
    # Check that we used the configured output flags
    mock_configure_flags.assert_called_once()
    mock_handle_output_for_cli.assert_called_once()


@pytest.mark.asyncio
async def test_wait_error_handling(
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command error handling."""
    runner = CliRunner()
    # Set up mock kubectl output for a timeout or error
    mock_run_kubectl_for_cli.set_error_response("timed out waiting for the condition")

    # Invoke CLI synchronously
    result = await runner.invoke(
        cli,  # type: ignore[arg-type]
        [
            "wait",
            "pod/nginx",
            "--for=condition=Ready",
            "--timeout=1s",
            "--no-live-display",
        ],
    )

    # Check results - CLI should exit with non-zero status for errors
    assert result.exit_code == 1
    # Make sure the error is being processed
    assert "timed out waiting for the condition" in result.output


@patch("vibectl.subcommands.wait_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("sys.exit")
@pytest.mark.asyncio
async def test_wait_vibe_request(
    mock_sys_exit: MagicMock,
    mock_handle_vibe: AsyncMock,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
) -> None:
    """Test wait command with vibe request."""
    runner = CliRunner()
    mock_handle_vibe.return_value = Success(message="Planned and executed")

    cmd_obj = cli.commands["wait"]
    result = await runner.invoke(
        cmd_obj,
        ["vibe", "wait until the deployment myapp is ready", "--no-live-display"],
        catch_exceptions=True,
    )
    mock_handle_vibe.assert_called_once()
    assert result.exit_code == 0
    assert result.exception is None
    mock_sys_exit.assert_any_call(0)


@patch("vibectl.subcommands.wait_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("sys.exit")
@pytest.mark.asyncio
async def test_wait_vibe_request_error(
    mock_sys_exit: MagicMock,
    mock_handle_vibe: AsyncMock,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
) -> None:
    """Test wait command vibe request error handling."""
    runner = CliRunner()
    mock_handle_vibe.return_value = Error(error="LLM planning failed")

    cmd_obj = cli.commands["wait"]
    result = await runner.invoke(
        cmd_obj,  # type: ignore[arg-type]
        ["vibe", "some complex wait request", "--no-live-display"],
        catch_exceptions=True,
    )
    assert "LLM planning failed" in result.output
    mock_sys_exit.assert_any_call(1)


@pytest.mark.asyncio
async def test_wait_vibe_no_request(
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_asyncio_for_wait: MagicMock,
) -> None:
    """Test that the wait command properly handles missing vibe request."""
    runner = CliRunner()
    # Invoke directly, expect error
    cmd_obj = cli.commands["wait"]
    with pytest.raises(SystemExit) as exc_info:
        # Use await directly
        await runner.invoke(
            cmd_obj,
            ["vibe"],
            catch_exceptions=False,  # Allow SystemExit to propagate for pytest.raises
        )
    assert exc_info.value.code != 0
    # TODO: Check error message in console output? CliRunner is bypassed.


@pytest.mark.asyncio
async def test_wait_with_live_display_asyncio(
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with live display using asyncio."""
    runner = CliRunner()
    from unittest.mock import patch

    from vibectl.types import Success

    result_value = Success(data="pod/nginx condition met")
    mock_run_kubectl_for_cli.return_value = result_value

    # Mock the async worker function with type hints
    async def mock_wait_live_display_async(*args: Any, **kwargs: Any) -> Result:
        return Success()

    with patch.object(
        wait_cmd_module,
        "handle_wait_with_live_display",
        new=mock_wait_live_display_async,
    ) as mock_wait_live_display:
        # Invoke directly
        cmd_obj = cli.commands["wait"]
        try:
            # Use await directly
            await runner.invoke(
                cmd_obj,
                ["pod/nginx", "--for=condition=Ready", "--live-display"],
                catch_exceptions=True,
            )
            mock_wait_live_display.assert_called_once()
        except SystemExit as e:
            pytest.fail(f"Command exited unexpectedly with code {e.code}")
        except Exception as e:
            pytest.fail(f"Command raised unexpected exception: {e}")


@pytest.mark.asyncio
async def test_wait_with_live_display_error_asyncio(
    mock_run_kubectl_for_cli: MagicMock,
    mock_handle_output_for_cli: MagicMock,
    mock_asyncio_for_wait: MagicMock,
    mock_memory: Mock,
) -> None:
    """Test wait command with live display handling errors using asyncio."""
    runner = CliRunner()
    from unittest.mock import patch

    from vibectl.types import Error

    error_response = Error(error="timed out waiting for the condition")
    mock_run_kubectl_for_cli.return_value = error_response

    # Mock the async worker function
    async def mock_error_live_display_async(*args: Any, **kwargs: Any) -> Result:
        return Error(error="timed out")

    with patch.object(
        wait_cmd_module,
        "handle_wait_with_live_display",
        new=mock_error_live_display_async,
    ) as mock_wait_live_display:
        # Invoke directly, expect error exit
        cmd_obj = cli.commands["wait"]
        with pytest.raises(SystemExit) as exc_info:
            # Use await directly
            await runner.invoke(
                cmd_obj,
                [
                    "pod/nginx",
                    "--for=condition=Ready",
                    "--timeout=1s",
                    "--live-display",
                ],
                catch_exceptions=False,  # Allow SystemExit to propagate
            )
        assert exc_info.value.code != 0
        mock_wait_live_display.assert_called_once()


@patch("vibectl.subcommands.wait_cmd.handle_standard_command")
@patch("sys.exit")
@pytest.mark.asyncio
async def test_wait_standard_command(
    mock_sys_exit: MagicMock,
    mock_handle_standard: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
) -> None:
    """Test wait command execution path without live display."""
    runner = CliRunner()
    mock_handle_standard.return_value = Success(message="Wait completed standard")

    cmd_obj = cli.commands["wait"]
    result = await runner.invoke(
        cmd_obj,
        [
            "deployment/app",
            "--for=jsonpath='{.status}'=Running",
            "--no-live-display",
        ],
        catch_exceptions=True,
    )
    mock_handle_standard.assert_called_once()
    assert result.exit_code == 0
    assert result.exception is None
    mock_sys_exit.assert_any_call(0)


@patch("vibectl.subcommands.wait_cmd.handle_standard_command")
@patch("sys.exit")
@pytest.mark.asyncio
async def test_wait_standard_command_error(
    mock_sys_exit: MagicMock,
    mock_handle_standard: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_configure_memory_flags: MagicMock,
) -> None:
    """Test error handling in the standard wait command path."""
    runner = CliRunner()
    mock_handle_standard.return_value = Error(error="Standard command failed")

    cmd_obj = cli.commands["wait"]
    result = await runner.invoke(
        cmd_obj,  # type: ignore[arg-type]
        [
            "job/myjob",
            "--for=condition=Complete",
            "--no-live-display",
        ],
        catch_exceptions=True,
    )
    assert "Standard command failed" in result.output
    mock_sys_exit.assert_any_call(1)
