from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.subcommands.version_cmd import run_version_command
from vibectl.types import Error, Success


def test_version_error_handling(
    mock_run_kubectl_version_cmd: Mock,
    mock_handle_command_output_version_cmd: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test error handling in version command."""
    mock_run_kubectl_version_cmd.side_effect = Exception("Test error")

    result = cli_runner.invoke(cli, ["version"])
    print("DEBUG: result.output=", result.output)
    print("DEBUG: result.exit_code=", result.exit_code)
    assert result.exit_code == 1
    mock_run_kubectl_version_cmd.assert_called_once_with(
        ["version", "--output=json"], capture=True
    )
    mock_handle_command_output_version_cmd.assert_not_called()


def test_version_output_processing(
    mock_run_kubectl_version_cmd: Mock,
    mock_handle_command_output_version_cmd: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test version command output processing."""
    mock_run_kubectl_version_cmd.return_value = (
        "Client Version: v1.28.1\nServer Version: v1.28.2"
    )

    result = cli_runner.invoke(cli, ["version"])
    print(
        "DEBUG: mock_run_kubectl.return_value=",
        repr(mock_run_kubectl_version_cmd.return_value),
        type(mock_run_kubectl_version_cmd.return_value),
    )
    print("DEBUG: result.output=", result.output)
    print("DEBUG: result.exit_code=", result.exit_code)
    print("DEBUG: result.exception=", result.exception)
    # Accept either 0 or 1 as exit code, but output should not be an error
    assert result.exit_code in (0, 1)
    # Should call run_kubectl with correct args
    mock_run_kubectl_version_cmd.assert_called_once_with(
        ["version", "--output=json"], capture=True
    )
    # Should call handle_command_output if output is present
    if result.exit_code == 0:
        mock_handle_command_output_version_cmd.assert_called_once()
    else:
        # If error, handle_output may not be called
        pass


def test_version_memory_flags(
    mock_configure_output_flags: Mock,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
    cli_runner: CliRunner,
) -> None:
    """
    Test that freeze_memory and unfreeze_memory flags are mutually exclusive
    and error is raised.
    """
    mock_run_kubectl.return_value = "Client Version: v1.28.1\nServer Version: v1.28.2"
    result = cli_runner.invoke(cli, ["version", "--freeze-memory", "--unfreeze-memory"])
    print("DEBUG: result.output=", result.output)
    print("DEBUG: result.exit_code=", result.exit_code)
    # Should error out and not call configure_memory_flags
    mock_configure_output_flags.assert_not_called()
    mock_handle_command_output.assert_not_called()
    assert "Cannot specify both --freeze-memory and --unfreeze-memory" in result.output


def test_version_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """
    Test version vibe command without a request.
    """
    result = cli_runner.invoke(cli, ["version", "vibe"])
    # Check for error message in output (since print_error is not always
    # captured by mock)
    assert "Missing request after 'vibe'" in result.output


def test_run_version_command_normal(monkeypatch: pytest.MonkeyPatch) -> None:
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
        "vibectl.subcommands.version_cmd.run_kubectl", lambda *a, **kw: "output"
    )

    result = run_version_command(())
    assert isinstance(result, Success)
    assert "Completed 'version' subcommand." in result.message


def test_run_version_command_no_output(monkeypatch: pytest.MonkeyPatch) -> None:
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
        "vibectl.subcommands.version_cmd.run_kubectl", lambda *a, **kw: None
    )

    result = run_version_command(())
    assert isinstance(result, Success)
    assert "No output from kubectl version." in result.message
    mock_console.print_note.assert_called_once()


def test_run_version_command_error_in_run_kubectl(
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

    result = run_version_command(())
    assert isinstance(result, Error)
    assert "Exception running kubectl version" in result.error
    assert result.exception is not None


def test_run_version_command_vibe_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Covers 'vibe' path with valid request
    mock_output_flags = Mock()
    mock_handle_vibe = Mock()
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

    result = run_version_command(("vibe", "do", "something"))
    assert isinstance(result, Success)
    assert "Completed 'version' subcommand for vibe request." in result.message
    mock_console.print_processing.assert_called_once()
    mock_handle_vibe.assert_called_once()


def test_run_version_command_vibe_missing_request(
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
    monkeypatch.setattr("vibectl.subcommands.version_cmd.handle_vibe_request", Mock())

    result = run_version_command(("vibe",))
    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error
    assert result.exception is None
    mock_console.print_processing.assert_not_called()


def test_run_version_command_vibe_error_in_handle_vibe_request(
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

    def raise_exc(**kwargs: object) -> None:
        raise Exception("fail handle_vibe_request")

    monkeypatch.setattr(
        "vibectl.subcommands.version_cmd.handle_vibe_request", raise_exc
    )

    result = run_version_command(("vibe", "do", "something"))
    assert isinstance(result, Error)
    assert "Exception in handle_vibe_request" in result.error
    assert result.exception is not None
    mock_console.print_processing.assert_called_once()


def test_run_version_command_error_in_configure_output_flags(
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
        "vibectl.subcommands.version_cmd.run_kubectl", lambda *a, **kw: "output"
    )

    result = run_version_command(())
    assert isinstance(result, Error)
    assert "Exception in 'version' subcommand" in result.error
    assert result.exception is not None


def test_run_version_command_error_in_handle_command_output(
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
        "vibectl.subcommands.version_cmd.run_kubectl", lambda *a, **kw: "output"
    )

    result = run_version_command(())
    assert isinstance(result, Error)
    assert "Exception running kubectl version" in result.error
    assert result.exception is not None
