"""Tests for vibectl.subcommands.version_cmd."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.config import DEFAULT_CONFIG, Config
from vibectl.subcommands.version_cmd import run_version_command
from vibectl.types import (
    Error,
    Fragment,
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
        show_raw=False,
        show_vibe=False,  # Typically false for version
        warn_no_output=True,
        model_name="test-model",
        show_metrics=False,
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
        show_raw=cast(bool, DEFAULT_CONFIG["show_raw_output"]),
        show_vibe=cast(bool, DEFAULT_CONFIG["show_vibe"]),
        warn_no_output=cast(bool, DEFAULT_CONFIG["warn_no_output"]),
        model_name=cast(str, DEFAULT_CONFIG["model"]),
        show_metrics=cast(bool, DEFAULT_CONFIG["show_metrics"]),
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
        result = await run_version_command(args=())

        # configure_output_flags is called by run_version_command internally
        mock_configure_output_flags.assert_called_once()
        # configure_memory_flags is also called
        mock_configure_memory.assert_called_once()

        expected_kubectl_cmd_args = ["version", "--output=json"]
        mock_run_kubectl.assert_called_once_with(expected_kubectl_cmd_args)

        mock_handle_output.assert_called_once()
        _call_args, call_kwargs = mock_handle_output.call_args
        # Assert against the specific instance we told configure_output_flags to return
        assert call_kwargs.get("output") == mock_kubectl_result
        assert call_kwargs.get("output_flags") == expected_flags
        assert (
            call_kwargs.get("summary_prompt_func") is not None
        )  # Check that some func is passed

        assert isinstance(result, Success)
        assert result.message == "Completed 'version' subcommand."


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

    mock_handle_command_output = Mock(
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

    result = await run_version_command(args=())
    assert isinstance(result, Success)
    # The final message comes from run_version_command itself in this path
    assert "Completed 'version' subcommand." in result.message
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

    result = await run_version_command(args=())
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

    result = await run_version_command(args=())
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

    result = await run_version_command(args=("vibe", "do", "something"))
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

    result = await run_version_command(args=("vibe",))
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

    result = await run_version_command(args=("vibe", "do", "something"))
    assert isinstance(result, Error)
    assert "Exception in handle_vibe_request" in result.error
    assert result.exception is not None
    mock_console.print_processing.assert_called_once()


@pytest.mark.asyncio
async def test_run_version_command_error_in_configure_output_flags(
    monkeypatch: pytest.MonkeyPatch,
    dummy_summary_prompt_func: SummaryPromptFragmentFunc,
) -> None:
    """Covers error in configure_output_flags"""

    def raise_exc(**kwargs: object) -> None:
        raise Exception("fail configure_output_flags")

    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags", raise_exc
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", Mock())
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output", lambda **kwargs: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        Mock(return_value=Success(data="output")),
    )

    result = await run_version_command(args=())
    assert isinstance(result, Error)
    assert "Exception in 'version' subcommand" in result.error
    assert result.exception is not None


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

    result = await run_version_command(args=())
    # The exception from handle_command_output (run in a thread) is caught
    # by the outer try-except in run_version_command
    assert isinstance(result, Error)
    assert "Exception running kubectl version" in result.error
    assert result.exception is not None


@pytest.mark.asyncio
async def test_cli_version_error_handling(
    cli_runner: CliRunner,  # Assuming CliRunner is available
) -> None:
    """Test error handling in version command when called via CLI."""
    # run_kubectl is synchronous, called via asyncio.to_thread
    with (
        patch("vibectl.subcommands.version_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.version_cmd.handle_command_output"
        ) as mock_handle_output,
    ):
        mock_run_kubectl.side_effect = Exception("Test error from run_kubectl")

        cmd_obj = cli.commands["version"]
        # Simulate Click's invocation. Since run_version_command is async,
        # and Click commands are typically wrapped to handle async,
        # we call main() which is what Click would do.
        # The SystemExit is expected as Click commands often exit.
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main([])

        assert exc_info.value.code != 0, (
            "CLI command should exit with non-zero code on error"
        )
        mock_run_kubectl.assert_called_once_with(["version", "--output=json"])
        mock_handle_output.assert_not_called()


@pytest.mark.asyncio
async def test_cli_version_output_processing(
    cli_runner: CliRunner,
) -> None:
    """Test version command output processing when called via CLI."""
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

        cmd_obj = cli.commands["version"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main([])

    assert exc_info.value.code == 0, "CLI command should exit with zero code on success"
    mock_run_kubectl.assert_called_once_with(["version", "--output=json"])
    mock_handle_output.assert_called_once()  # handle_command_output should be called


@pytest.mark.asyncio
async def test_cli_version_memory_flags(
    cli_runner: CliRunner,  # Assuming CliRunner is available
) -> None:
    """Test version command with memory flags using Click's command invocation."""

    # Mock dependencies of run_version_command
    # run_kubectl is synchronous
    mock_run_kubectl_instance = MagicMock(
        return_value=Success(data="some version data")
    )
    mock_handle_command_output_instance = Mock(return_value=Success())
    mock_configure_memory_flags_instance = MagicMock()
    mock_output_flags_instance = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,
    )

    with (
        patch("vibectl.subcommands.version_cmd.run_kubectl", mock_run_kubectl_instance),
        patch(
            "vibectl.subcommands.version_cmd.handle_command_output",
            mock_handle_command_output_instance,
        ),
        patch(
            "vibectl.subcommands.version_cmd.configure_memory_flags",
            mock_configure_memory_flags_instance,
        ),
        patch(
            "vibectl.subcommands.version_cmd.configure_output_flags",
            return_value=mock_output_flags_instance,
        ),
    ):
        cmd_obj = cli.commands["version"]

        # First invocation with --freeze-memory
        with pytest.raises(SystemExit) as exc_info_1:
            await cmd_obj.main(
                ["--freeze-memory", "--show-metrics", "--model", "test-model"]
            )
        assert exc_info_1.value.code == 0, (
            f"CLI exited with code {exc_info_1.value.code} on first call"
        )
        mock_run_kubectl_instance.assert_called_once_with(["version", "--output=json"])
        mock_configure_memory_flags_instance.assert_any_call(
            True, False
        )  # freeze=True, unfreeze=False

        # Reset mocks for the second invocation as needed
        mock_run_kubectl_instance.reset_mock()
        mock_handle_command_output_instance.reset_mock()
        # We don't reset mock_configure_memory_flags_instance to check cumulative calls

        # Second invocation with --unfreeze-memory
        with pytest.raises(SystemExit) as exc_info_2:
            await cmd_obj.main(
                ["--unfreeze-memory", "--show-metrics", "--model", "test-model"]
            )
        assert exc_info_2.value.code == 0, (
            f"CLI failed: {exc_info_2.value.code} on second call"
        )
        mock_run_kubectl_instance.assert_called_once_with(["version", "--output=json"])
        mock_configure_memory_flags_instance.assert_any_call(
            False, True
        )  # freeze=False, unfreeze=True

        assert mock_configure_memory_flags_instance.call_count == 2


@pytest.mark.asyncio
async def test_cli_version_vibe_no_request(
    cli_runner: CliRunner,  # Assuming CliRunner is available
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
