from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.subcommands.version_cmd import run_version_command
from vibectl.types import Error, OutputFlags, Success


@pytest.mark.asyncio
async def test_version_error_handling(
    mock_run_kubectl_version_cmd: Mock,
    mock_handle_command_output_version_cmd: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in version command."""
    with (
        patch("vibectl.subcommands.version_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.version_cmd.handle_command_output"
        ) as mock_handle_output,
    ):
        mock_run_kubectl.side_effect = Exception("Test error")

        cmd_obj = cli.commands["version"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main([])

        assert exc_info.value.code != 0
        mock_run_kubectl.assert_called_once_with(["version", "--output=json"])
        mock_handle_output.assert_not_called()


@pytest.mark.asyncio
async def test_version_output_processing(
    mock_run_kubectl_version_cmd: Mock,
    mock_handle_command_output_version_cmd: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test version command output processing."""
    with (
        patch("vibectl.subcommands.version_cmd.run_kubectl") as mock_run_kubectl,
        patch(
            "vibectl.subcommands.version_cmd.handle_command_output"
        ) as mock_handle_output,
    ):
        mock_run_kubectl.return_value = Success(
            data='{"clientVersion": {"gitVersion": "v1.28.1"} }'
        )

        cmd_obj = cli.commands["version"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main([])

    assert exc_info.value.code == 0
    mock_run_kubectl.assert_called_once_with(["version", "--output=json"])
    mock_handle_output.assert_called_once()


@pytest.mark.asyncio
async def test_version_memory_flags(
    mock_configure_output_flags: Mock,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test version command with memory flags using CliRunner."""
    mock_run_kubectl.return_value = Success(data="some version data")
    mock_handle_command_output.return_value = Success()
    mock_configure_memory_flags = MagicMock()  # Change to MagicMock

    # Use a consistent OutputFlags instance
    mock_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=True,  # Revert show_vibe to True
    )
    mock_configure_output_flags.return_value = mock_flags

    with (
        patch(
            "vibectl.subcommands.version_cmd.configure_memory_flags",
            mock_configure_memory_flags,
        ),
        patch(
            "vibectl.subcommands.version_cmd.run_kubectl",
            mock_run_kubectl,  # Use the existing mock fixture
        ),
        patch(
            "vibectl.subcommands.version_cmd.handle_command_output",
            mock_handle_command_output,  # Use the existing mock fixture
        ),
    ):
        cmd_obj = cli.commands["version"]

        # First invocation
        with pytest.raises(SystemExit) as exc_info_1:
            await cmd_obj.main(
                [
                    "--freeze-memory",
                    "--show-metrics",
                    "--model",
                    "test-model",
                ]
            )
        assert exc_info_1.value.code == 0, (
            f"CLI exited with code {exc_info_1.value.code}"
        )

        # Verify run_kubectl was called for the first invocation
        mock_run_kubectl.assert_called_once_with(["version", "--output=json"])
        # Use positional arguments for assertion
        mock_configure_memory_flags.assert_any_call(True, False)

        # Reset mocks for the second invocation
        mock_run_kubectl.reset_mock()
        mock_handle_command_output.reset_mock()  # Assuming called by version_cmd.main
        # mock_configure_memory_flags.reset_mock()
        # # Not resetting this one to check cumulative calls

        # Second invocation
        with pytest.raises(SystemExit) as exc_info_2:
            await cmd_obj.main(
                [
                    "--unfreeze-memory",
                    "--show-metrics",
                    "--model",
                    "test-model",
                ]
            )
        assert exc_info_2.value.code == 0, f"CLI failed: {exc_info_2.value.code}"

        # Verify run_kubectl was called for the second invocation
        mock_run_kubectl.assert_called_once_with(["version", "--output=json"])
        # Use positional arguments for assertion
        mock_configure_memory_flags.assert_any_call(False, True)

        # Verify total calls for configure_memory_flags if not reset
        assert mock_configure_memory_flags.call_count == 2


@pytest.mark.asyncio
async def test_version_vibe_no_request(
    cli_runner: CliRunner,
) -> None:
    """
    Test version vibe command without a request.
    """
    with (
        patch(
            "vibectl.subcommands.version_cmd.handle_vibe_request",
            new_callable=AsyncMock,
        ) as mock_handle_vibe,
    ):
        cmd_obj = cli.commands["version"]
        with pytest.raises(SystemExit) as exc_info:
            await cmd_obj.main(["vibe"])

    assert exc_info.value.code != 0
    mock_handle_vibe.assert_not_called()


@pytest.mark.asyncio
async def test_run_version_command_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Covers normal version command with output
    mock_output_flags = Mock()
    mock_output_flags.show_raw = True
    mock_output_flags.show_vibe = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.show_kubectl = False

    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: mock_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.version_prompt", lambda: "prompt"
    )
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", Mock())
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output", lambda **kwargs: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        lambda *a, **kw: Success(data="output"),
    )

    result = await run_version_command(())
    assert isinstance(result, Success)
    assert "Completed 'version' subcommand." in result.message


@pytest.mark.asyncio
async def test_run_version_command_no_output(monkeypatch: pytest.MonkeyPatch) -> None:
    # Covers version command with no output from run_kubectl
    mock_output_flags = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: mock_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.version_prompt", lambda: "prompt"
    )
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", mock_console)
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output", lambda **kwargs: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        lambda *a, **kw: Success(data=None),
    )

    result = await run_version_command(())
    assert isinstance(result, Success)
    assert "No output from kubectl version." in result.message
    mock_console.print_note.assert_called_once_with("No output from kubectl version.")


@pytest.mark.asyncio
async def test_run_version_command_error_in_run_kubectl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers error in run_kubectl
    mock_output_flags = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: mock_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.version_prompt", lambda: "prompt"
    )
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", Mock())
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output", lambda **kwargs: None
    )

    def raise_exc(*a: object, **kw: object) -> None:
        raise Exception("fail run_kubectl")

    monkeypatch.setattr("vibectl.subcommands.version_cmd.run_kubectl", raise_exc)

    result = await run_version_command(())
    assert isinstance(result, Error)
    assert "Exception running kubectl version" in result.error
    assert result.exception is not None


@pytest.mark.asyncio
async def test_run_version_command_vibe_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Covers 'vibe' path with valid request
    mock_output_flags = Mock()
    mock_handle_vibe = AsyncMock(return_value=Success(message="Vibe success"))
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: mock_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.version_prompt", lambda: "prompt"
    )
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", mock_console)
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_vibe_request", mock_handle_vibe
    )

    result = await run_version_command(("vibe", "do", "something"))
    assert isinstance(result, Success)
    assert result.message == "Vibe success"
    mock_console.print_processing.assert_called_once()
    mock_handle_vibe.assert_called_once()


@pytest.mark.asyncio
async def test_run_version_command_vibe_missing_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers 'vibe' path with missing request
    mock_output_flags = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: mock_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.version_prompt", lambda: "prompt"
    )
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", mock_console)
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_vibe_request", AsyncMock()
    )

    result = await run_version_command(("vibe",))
    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error
    assert result.exception is None
    mock_console.print_processing.assert_not_called()


@pytest.mark.asyncio
async def test_run_version_command_vibe_error_in_handle_vibe_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers error in handle_vibe_request
    mock_output_flags = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: mock_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.version_prompt", lambda: "prompt"
    )
    mock_console = Mock()
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", mock_console)

    mock_vibe_handler = AsyncMock(side_effect=Exception("fail handle_vibe_request"))
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_vibe_request", mock_vibe_handler
    )

    result = await run_version_command(("vibe", "do", "something"))
    assert isinstance(result, Error)
    assert "Exception in handle_vibe_request" in result.error
    assert result.exception is not None
    mock_console.print_processing.assert_called_once()


@pytest.mark.asyncio
async def test_run_version_command_error_in_configure_output_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers error in configure_output_flags
    def raise_exc(**kwargs: object) -> None:
        raise Exception("fail configure_output_flags")

    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags", raise_exc
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.version_prompt", lambda: "prompt"
    )
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", Mock())
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output", lambda **kwargs: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        lambda *a, **kw: Success(data="output"),
    )

    result = await run_version_command(())
    assert isinstance(result, Error)
    assert "Exception in 'version' subcommand" in result.error
    assert result.exception is not None


@pytest.mark.asyncio
async def test_run_version_command_error_in_handle_command_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers error in handle_command_output
    mock_output_flags = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_output_flags",
        lambda **kwargs: mock_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.configure_memory_flags", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.version_prompt", lambda: "prompt"
    )
    monkeypatch.setattr("vibectl.subcommands.version_cmd.console_manager", Mock())

    def raise_exc(**kwargs: object) -> None:
        raise Exception("fail handle_command_output")

    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_command_output", raise_exc
    )
    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.run_kubectl",
        lambda *a, **kw: Success(data="output"),
    )

    result = await run_version_command(())
    assert isinstance(result, Error)
    assert "Exception running kubectl version" in result.error
    assert result.exception is not None
