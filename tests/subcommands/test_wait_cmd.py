"""Tests for the CLI wait command.

This module tests the CLI wait command of vibectl. All tests in this module
should use appropriate mocking to prevent real calls to kubectl and LLM services.
"""

from collections.abc import Generator
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
    """Patch vibectl.command_handler.run_kubectl so no real kubectl is executed."""
    with patch("vibectl.command_handler.run_kubectl") as run_kubectl_mock:
        run_kubectl_mock.return_value = Success(data="test wait output")

        # Helper for tests to simulate error responses
        def set_error_response(stderr: str = "test error") -> None:
            error_msg = stderr or "Command failed"
            run_kubectl_mock.return_value = Error(error=error_msg)

        run_kubectl_mock.set_error_response = set_error_response  # type: ignore[attr-defined]

        yield run_kubectl_mock


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


@pytest.fixture(autouse=True)
def _disable_vibe(monkeypatch: Any) -> None:
    """Force show_vibe=False and a dummy model for all tests in this module.

    We need to patch *both* the original function in ``vibectl.command_handler`` **and**
    the already imported alias inside ``vibectl.subcommands.wait_cmd``.  The latter
    was imported with ``from vibectl.command_handler import configure_output_flags``
    at module import time, so patching only the source module would leave the alias
    unchanged and allow Vibe processing (and therefore real LLM calls) to slip
    through in some error-handling code paths.
    """

    def _flags(**_kwargs: Any) -> OutputFlags:  # Accept any params from caller
        return OutputFlags(
            model_name="dummy-model",
            show_raw_output=False,
            show_vibe=False,
            show_kubectl=False,
            show_metrics=MetricsDisplayMode.NONE,
            show_streaming=False,
            warn_no_output=False,
            warn_no_proxy=False,
        )

    # Patch both the original and the re-exported alias used by wait_cmd
    monkeypatch.setattr("vibectl.command_handler.configure_output_flags", _flags)
    monkeypatch.setattr("vibectl.subcommands.wait_cmd.configure_output_flags", _flags)


@pytest.mark.asyncio
async def test_wait_basic(
    mock_run_kubectl_for_cli: MagicMock,
    mock_memory: Mock,
    mock_get_adapter: MagicMock,
) -> None:
    """Test wait command with basic arguments."""
    runner = CliRunner()
    from vibectl.types import Success

    # Set up mock kubectl output
    mock_run_kubectl_for_cli.return_value = Success(data="pod/nginx condition met")

    # Invoke CLI synchronously - pytest-asyncio handles the loop
    result = await runner.invoke(
        cli,  # type: ignore[arg-type]
        ["wait", "pod/nginx", "--for=condition=Ready", "--no-live-display"],
        catch_exceptions=True,  # Ensure click.Exit is caught
    )

    # Check results
    assert result.exit_code == 0
    # Ensure run_kubectl was invoked
    mock_run_kubectl_for_cli.assert_called()


@pytest.mark.asyncio
async def test_wait_with_args(
    mock_run_kubectl_for_cli: MagicMock,
    mock_memory: Mock,
    mock_get_adapter: MagicMock,
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
    # Ensure run_kubectl was invoked
    mock_run_kubectl_for_cli.assert_called()


@patch("vibectl.subcommands.wait_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_wait_with_flags(
    mock_configure_flags: Mock,
    mock_run_kubectl_for_cli: MagicMock,
    mock_memory: Mock,
    mock_get_adapter: MagicMock,
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
    # Ensure run_kubectl was invoked
    mock_run_kubectl_for_cli.assert_called()


@pytest.mark.asyncio
async def test_wait_error_handling(
    mock_run_kubectl_for_cli: MagicMock,
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
    # Ensure run_kubectl was invoked
    mock_run_kubectl_for_cli.assert_called()
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
) -> None:
    """Test that the wait command properly handles missing vibe request."""
    runner = CliRunner()
    # Invoke and verify non-zero exit code
    cmd_obj = cli.commands["wait"]
    result = await runner.invoke(
        cmd_obj,
        ["vibe"],
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    # TODO: Check error message in console output? CliRunner is bypassed.


@pytest.mark.asyncio
async def test_wait_with_live_display_asyncio(
    mock_run_kubectl_for_cli: MagicMock,
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
        new_callable=AsyncMock,
    ) as mock_wait_live_display:
        mock_wait_live_display.side_effect = mock_wait_live_display_async
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
        new_callable=AsyncMock,
    ) as mock_wait_live_display:
        mock_wait_live_display.side_effect = mock_error_live_display_async
        # Invoke and verify non-zero exit code
        cmd_obj = cli.commands["wait"]
        result = await runner.invoke(
            cmd_obj,
            [
                "pod/nginx",
                "--for=condition=Ready",
                "--timeout=1s",
                "--live-display",
            ],
            catch_exceptions=True,
        )
        assert result.exit_code != 0
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
