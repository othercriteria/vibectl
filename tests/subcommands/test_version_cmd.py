"""Tests for vibectl.subcommands.version_cmd."""

from typing import cast
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import DEFAULT_CONFIG, Config
from vibectl.logutil import logger
from vibectl.subcommands.version_cmd import run_version_command
from vibectl.types import (
    Error,
    Fragment,
    MetricsDisplayMode,
    OutputFlags,
    PromptFragments,
    Success,
    SummaryPromptFragmentFunc,
    SystemFragments,
    UserFragments,
)


# Dummy summary_prompt_func for testing
@pytest.fixture
def dummy_summary_prompt_func(config: Config | None = None) -> PromptFragments:
    return PromptFragments(
        (
            SystemFragments([Fragment("System Summary")]),
            UserFragments([Fragment("User Summary")]),
        )
    )


@pytest.fixture
def default_output_flags_fixture() -> OutputFlags:
    """Provides default OutputFlags for version command tests."""
    # Ensure mock_config is used if it's available and OutputFlags needs it
    # Or directly instantiate if no complex config needed for these defaults
    return OutputFlags(
        show_raw_output=False,
        show_vibe=False,  # Typically false for version
        warn_no_output=True,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=True,
    )


@pytest.mark.asyncio
async def test_run_version_command_success() -> None:
    """Test run_version_command successful execution."""
    mock_kubectl_result = Success(
        message="kubectl version output data",
        data='{"clientVersion": {"gitVersion": "v1.2.3"}}',
    )
    mock_handle_output_result = Success(message="Processed version output")

    # Define the expected OutputFlags based on how configure_output_flags
    # would behave with no specific CLI args for the version command.
    # This often means it will use values from DEFAULT_CONFIG.
    expected_flags = OutputFlags(
        show_raw_output=cast(bool, DEFAULT_CONFIG["show_raw_output"]),
        show_vibe=cast(bool, DEFAULT_CONFIG["show_vibe"]),
        warn_no_output=cast(bool, DEFAULT_CONFIG["warn_no_output"]),
        model_name=cast(str, DEFAULT_CONFIG["model"]),
        show_metrics=MetricsDisplayMode.from_value(str(DEFAULT_CONFIG["show_metrics"])),
        show_kubectl=cast(bool, DEFAULT_CONFIG["show_kubectl"]),
        warn_no_proxy=cast(bool, DEFAULT_CONFIG["warn_no_proxy"]),
    )

    with (
        patch(
            "vibectl.subcommands.version_cmd.run_kubectl",
            return_value=mock_kubectl_result,
        ) as mock_run_kubectl,
        patch(
            "vibectl.subcommands.version_cmd.handle_command_output",
            return_value=mock_handle_output_result,
        ) as mock_handle_output,
        patch(
            "vibectl.subcommands.version_cmd.configure_output_flags",
            return_value=expected_flags,
        ) as mock_configure_output_flags,
        patch(
            "vibectl.subcommands.version_cmd.configure_memory_flags", MagicMock()
        ) as mock_configure_memory,
    ):
        result = await run_version_command(
            args=(),
            show_raw_output=None,
            show_vibe=None,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_kubectl=None,
            show_metrics=None,
            show_streaming=True,
        )

        # configure_output_flags is called by run_version_command internally
        mock_configure_output_flags.assert_called_once()
        # configure_memory_flags is also called
        mock_configure_memory.assert_called_once()

        expected_kubectl_cmd_args = ["version", "--output=json"]
        mock_run_kubectl.assert_called_once_with(expected_kubectl_cmd_args, config=ANY)

        mock_handle_output.assert_called_once()
        _call_args, call_kwargs = mock_handle_output.call_args
        # Assert against the specific instance we told configure_output_flags to return
        assert call_kwargs.get("output") == mock_kubectl_result
        assert call_kwargs.get("output_flags") == expected_flags
        assert (
            call_kwargs.get("summary_prompt_func") is not None
        )  # Check that some func is passed

        assert isinstance(result, Success)
        assert result.message == "Processed version output"
        mock_run_kubectl.assert_called_once()
        mock_handle_output.assert_called_once()


@pytest.mark.asyncio
async def test_run_version_command_normal(
    monkeypatch: pytest.MonkeyPatch,
    default_output_flags_fixture: OutputFlags,
    dummy_summary_prompt_func: SummaryPromptFragmentFunc,
) -> None:
    # Covers normal version command with output
    # Use existing fixtures where possible
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: default_output_flags_fixture,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", Mock())

    mock_handle_command_output = AsyncMock(
        return_value=Success(message="Completed from handle_output")
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output",
        mock_handle_command_output,
    )

    mock_run_kubectl = Mock(return_value=Success(data="output"))
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        mock_run_kubectl,
    )

    logger.debug("[TEST] About to call run_version_command")
    result = await run_version_command(
        args=(),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )
    logger.debug(f"[TEST] run_version_command returned: {result!r}")

    assert isinstance(result, Success)
    logger.debug(f"[TEST] result is Success. Message: {result.message}")
    # The final message comes from the mocked handle_command_output
    assert result.message == "Completed from handle_output"
    mock_run_kubectl.assert_called_once()
    mock_handle_command_output.assert_called_once()


@pytest.mark.asyncio
async def test_run_version_command_no_output(
    monkeypatch: pytest.MonkeyPatch,
    default_output_flags_fixture: OutputFlags,
    dummy_summary_prompt_func: SummaryPromptFragmentFunc,
) -> None:
    """Covers version command with no output from run_kubectl"""
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: default_output_flags_fixture,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", mock_console)
    mock_handle_command_output = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output",
        mock_handle_command_output,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        Mock(
            return_value=Success(data=None)
        ),  # run_kubectl returns Success with no data
    )

    result = await run_version_command(
        args=(),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )
    assert isinstance(result, Success)
    assert "No output from kubectl version." in result.message
    mock_handle_command_output.assert_not_called()


@pytest.mark.asyncio
async def test_run_version_command_error_in_run_kubectl(
    monkeypatch: pytest.MonkeyPatch,
    default_output_flags_fixture: OutputFlags,
    dummy_summary_prompt_func: SummaryPromptFragmentFunc,
) -> None:
    """Covers error in run_kubectl (e.g. kubectl command itself fails)"""
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: default_output_flags_fixture,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", Mock())
    mock_handle_command_output = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output",
        mock_handle_command_output,
    )

    simulated_error = Error(
        error="kubectl failed", exception=RuntimeError("kubectl failed")
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        Mock(return_value=simulated_error),
    )

    result = await run_version_command(
        args=(),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )
    assert (
        result is simulated_error
    )  # run_version_command should return the error from run_kubectl
    mock_handle_command_output.assert_not_called()


@pytest.mark.asyncio
async def test_run_version_command_vibe_path(
    monkeypatch: pytest.MonkeyPatch,
    default_output_flags_fixture: OutputFlags,
    dummy_summary_prompt_func: SummaryPromptFragmentFunc,
) -> None:
    # Covers 'vibe' path with valid request
    mock_handle_vibe = AsyncMock(return_value=Success(message="Vibe success"))
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: default_output_flags_fixture,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", mock_console)
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_vibe_request", mock_handle_vibe
    )

    result = await run_version_command(
        args=("vibe", "do", "something"),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )
    assert isinstance(result, Success)
    assert result.message == "Vibe success"
    mock_console.print_processing.assert_called_once()
    mock_handle_vibe.assert_called_once()
    # Check some key args passed to handle_vibe_request
    called_kwargs = mock_handle_vibe.call_args.kwargs
    assert called_kwargs.get("request") == "do something"
    assert called_kwargs.get("command") == "version"
    assert called_kwargs.get("output_flags") == default_output_flags_fixture


@pytest.mark.asyncio
async def test_run_version_command_vibe_missing_request(
    monkeypatch: pytest.MonkeyPatch,
    default_output_flags_fixture: OutputFlags,
    dummy_summary_prompt_func: SummaryPromptFragmentFunc,
) -> None:
    """Covers 'vibe' path with missing request"""
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: default_output_flags_fixture,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    mock_console = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.console_manager",
        mock_console,
    )
    mock_handle_vibe = AsyncMock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_vibe_request",
        mock_handle_vibe,
    )

    result = await run_version_command(
        args=("vibe",),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )
    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error
    assert result.exception is None
    mock_console.print_processing.assert_not_called()
    mock_handle_vibe.assert_not_called()  # Not called if args are invalid before it


@pytest.mark.asyncio
async def test_run_version_command_vibe_error_in_handle_vibe_request(
    monkeypatch: pytest.MonkeyPatch,
    default_output_flags_fixture: OutputFlags,
    dummy_summary_prompt_func: SummaryPromptFragmentFunc,
) -> None:
    """Covers error in handle_vibe_request"""
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: default_output_flags_fixture,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", mock_console)

    mock_vibe_handler = AsyncMock(side_effect=Exception("fail handle_vibe_request"))
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_vibe_request", mock_vibe_handler
    )

    result = await run_version_command(
        args=("vibe", "do", "something"),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )
    assert isinstance(result, Error)
    assert "Exception in handle_vibe_request" in result.error
    assert result.exception is not None
    mock_console.print_processing.assert_called_once()


@pytest.mark.asyncio
async def test_run_version_command_error_in_handle_command_output(
    monkeypatch: pytest.MonkeyPatch,
    default_output_flags_fixture: OutputFlags,
    dummy_summary_prompt_func: SummaryPromptFragmentFunc,
) -> None:
    """Covers error in handle_command_output (called via asyncio.to_thread)"""
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: default_output_flags_fixture,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", Mock())

    def raise_exc_handle_command_output(*args: object, **kwargs: object) -> None:
        raise Exception("fail handle_command_output")

    # This mock will be called inside asyncio.to_thread
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output",
        raise_exc_handle_command_output,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        Mock(return_value=Success(data="output")),
    )

    result = await run_version_command(
        args=(),
        show_raw_output=None,
        show_vibe=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )
    # The exception from handle_command_output (run in a thread) is caught
    # by the outer try-except in run_version_command
    assert isinstance(result, Error)
    assert "Exception processing kubectl version" in result.error
    assert result.exception is not None


@pytest.mark.asyncio
async def test_cli_version_error_handling() -> None:
    """Test error handling in version command when called via CLI."""
    cli_runner = CliRunner()  # Direct instantiation
    # run_kubectl is synchronous, called via asyncio.to_thread
    with (
        patch("vibectl.subcommands.version_cmd.run_kubectl") as mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
    ):
        mock_run_kubectl.side_effect = Exception("Test error from run_kubectl")

        result = await cli_runner.invoke(cli.commands["version"])  # type: ignore[arg-type]

        assert result.exit_code != 0, (
            "CLI command should exit with non-zero code on error"
        )
        mock_run_kubectl.assert_called_once_with(
            ["version", "--output=json"], config=ANY
        )
        mock_handle_output.assert_not_called()


@pytest.mark.asyncio
async def test_cli_version_output_processing() -> None:
    """Test version command output processing when called via CLI."""
    cli_runner = CliRunner()  # Direct instantiation
    # run_kubectl is synchronous, called via asyncio.to_thread
    with (
        patch("vibectl.subcommands.version_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.version_cmd.handle_command_output"
        ) as mock_handle_output,
    ):
        mock_run_kubectl.return_value = Success(
            data='{"clientVersion": {"gitVersion": "v1.28.1"} }'
        )
        # Mock handle_command_output to simulate it completing successfully
        mock_handle_output.return_value = Success(
            message="Processed by mock_handle_output"
        )

        result = await cli_runner.invoke(cli.commands["version"])  # type: ignore[arg-type]

        assert result.exit_code == 0, (
            f"CLI command should exit with zero code on success. "
            f"Output: {result.output}"
        )
        mock_run_kubectl.assert_called_once_with(
            ["version", "--output=json"], config=ANY
        )
        mock_handle_output.assert_called_once()


@pytest.mark.asyncio
async def test_cli_version_memory_flags() -> None:
    """Test version command with memory flags using Click's command invocation."""
    cli_runner = CliRunner()  # Direct instantiation

    # Mocks for dependencies within vibectl.subcommands.version_cmd
    mock_run_kubectl_sub = MagicMock(
        return_value=Success(data='{"clientVersion": {"gitVersion": "v1.0.0"}}')
    )
    mock_handle_output_sub = AsyncMock(return_value=Success(data="version vibe output"))
    mock_configure_mem_sub = MagicMock()
    mock_output_flags_instance = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=True,
    )
    mock_configure_out_sub = MagicMock(return_value=mock_output_flags_instance)

    with (
        patch("vibectl.subcommands.version_cmd.run_kubectl", mock_run_kubectl_sub),
        patch(
            "vibectl.subcommands.version_cmd.handle_command_output",
            mock_handle_output_sub,
        ),
        patch(
            "vibectl.subcommands.version_cmd.configure_memory_flags",
            mock_configure_mem_sub,
        ),
        patch(
            "vibectl.subcommands.version_cmd.configure_output_flags",
            mock_configure_out_sub,
        ),
        patch("vibectl.cli.logger"),
        patch("vibectl.subcommands.version_cmd.logger"),
    ):
        result_freeze = await cli_runner.invoke(
            cli.commands["version"], ["--freeze-memory"]
        )  # type: ignore[arg-type]

        assert result_freeze.exit_code == 0, (
            f"CLI exited with code {result_freeze.exit_code} on freeze call. "
            f"Output: {result_freeze.output}"
        )

        mock_configure_mem_sub.assert_any_call(True, None)


@pytest.mark.asyncio
async def test_cli_version_vibe_no_request(
    cli_runner: CliRunner,
) -> None:
    """Test version vibe command without a request when called via CLI."""
    with patch(
        "vibectl.subcommands.version_cmd.handle_vibe_request", new_callable=AsyncMock
    ) as mock_handle_vibe_request:
        cmd_obj = cli.commands["version"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main(["vibe"])  # Calling 'version vibe' with no further args

    assert exc_info.value.code != 0, (
        "CLI should exit non-zero if 'vibe' is called without a request"
    )
    mock_handle_vibe_request.assert_not_called()
