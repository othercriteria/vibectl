from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli
from vibectl.subcommands.describe_cmd import run_describe_command
from vibectl.types import Error, Success


def test_describe_basic(
    cli_runner: CliRunner, mock_run_kubectl: Mock, mock_handle_command_output: Mock
) -> None:
    """Test basic describe command functionality."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
    ):
        cmd_mock_run_kubectl.return_value = "test output"
        result = cli_runner.invoke(cli, ["describe", "pod", "my-pod"])
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once_with(
            ["describe", "pod", "my-pod"], capture=True
        )
        cmd_mock_handle_output.assert_called_once()


@pytest.mark.parametrize(
    "args, should_succeed",
    [
        (["describe", "pod", "my-pod", "--", "-n", "default"], True),  # valid: with --
        (["describe", "pod", "my-pod", "-n", "default"], False),  # invalid: no --
        (["describe", "-n", "default"], False),  # invalid: missing resource
    ],
)
def test_describe_args_variants(
    cli_runner: CliRunner,
    mock_run_kubectl: Mock,
    mock_handle_command_output: Mock,
    args: list[str],
    should_succeed: bool,
) -> None:
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
    ):
        cmd_mock_run_kubectl.return_value = "test output"
        result = cli_runner.invoke(cli, args)
        if should_succeed:
            assert result.exit_code == 0
            cmd_mock_run_kubectl.assert_called_once()
            cmd_mock_handle_output.assert_called_once()
        else:
            assert result.exit_code == 2
            assert "Usage" in result.output or "Error" in result.output


def test_describe_with_flags(
    cli_runner: CliRunner, mock_run_kubectl: Mock, mock_handle_command_output: Mock
) -> None:
    """Test describe command with output flags."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
    ):
        cmd_mock_run_kubectl.return_value = "test output"
        result = cli_runner.invoke(
            cli,
            [
                "describe",
                "pod",
                "my-pod",
                "--show-raw-output",
                "--show-vibe",
                "--show-kubectl",
            ],
        )
        assert result.exit_code == 0
        cmd_mock_run_kubectl.assert_called_once()
        cmd_mock_handle_output.assert_called_once()


def test_describe_error_handling(
    cli_runner: CliRunner, mock_run_kubectl: Mock, mock_handle_command_output: Mock
) -> None:
    """Test describe command when kubectl returns an error."""
    with (
        patch("vibectl.command_handler.run_kubectl") as cmd_mock_run_kubectl,
        patch(
            "vibectl.command_handler.handle_command_output"
        ) as cmd_mock_handle_output,
    ):
        cmd_mock_run_kubectl.side_effect = Exception("kubectl error")
        result = cli_runner.invoke(cli, ["describe", "pod", "my-pod"])
        assert result.exit_code != 0 or "error" in result.output.lower()
        cmd_mock_run_kubectl.assert_called_once()
        # handle_command_output should not be called on error
        assert cmd_mock_handle_output.call_count == 0


@patch("vibectl.subcommands.describe_cmd.handle_vibe_request")
def test_describe_vibe_request(mock_handle_vibe: Mock, cli_runner: CliRunner) -> None:
    """Test describe command with 'vibe' request."""
    result = cli_runner.invoke(
        cli, ["describe", "vibe", "show", "me", "the", "nginx", "pod"]
    )
    assert result.exit_code == 0
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == "show me the nginx pod"
    assert kwargs["command"] == "describe"


def test_describe_vibe_no_request(cli_runner: CliRunner, mock_console: Mock) -> None:
    """Test describe command with 'vibe' but no request (should error)."""
    result = cli_runner.invoke(cli, ["describe", "vibe"])
    # The CLI should exit with a nonzero code and print the error message
    assert result.exit_code != 0
    assert "Missing request after 'vibe'" in result.output


# --- Unit tests for run_describe_command for 100% coverage ---


def test_run_describe_command_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers the normal path (resource != 'vibe')."""
    called = {}

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        called["flags"] = True
        return Mock()

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        called["mem"] = True

    def fake_handle_standard_command(**kwargs: object) -> None:
        called["std"] = True

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.handle_standard_command",
        fake_handle_standard_command,
    )
    monkeypatch.setattr("vibectl.subcommands.describe_cmd.logger", Mock())
    result = run_describe_command(
        "pod", ("my-pod",), None, None, None, None, False, False
    )
    assert isinstance(result, Success)
    assert called["flags"] and called["mem"] and called["std"]


def test_run_describe_command_vibe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers the 'vibe' path with args."""
    called = {}

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return Mock()

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    def fake_handle_vibe_request(**kwargs: object) -> None:
        called["vibe"] = kwargs

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.handle_vibe_request", fake_handle_vibe_request
    )
    monkeypatch.setattr("vibectl.subcommands.describe_cmd.logger", Mock())
    result = run_describe_command(
        "vibe", ("foo",), None, None, None, None, False, False
    )
    assert isinstance(result, Success)
    assert "vibe" in called


def test_run_describe_command_vibe_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers the 'vibe' path with no args (error)."""

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return Mock()

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    fake_console_manager = Mock()
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.console_manager", fake_console_manager
    )
    monkeypatch.setattr("vibectl.subcommands.describe_cmd.logger", Mock())
    result = run_describe_command("vibe", (), None, None, None, None, False, False)
    assert isinstance(result, Error)
    fake_console_manager.print_error.assert_called_once()


def test_run_describe_command_vibe_handle_vibe_request_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers exception in handle_vibe_request."""

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return Mock()

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    def fake_handle_vibe_request(**kwargs: object) -> None:
        raise Exception("fail")

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.handle_vibe_request", fake_handle_vibe_request
    )
    monkeypatch.setattr("vibectl.subcommands.describe_cmd.logger", Mock())
    result = run_describe_command(
        "vibe", ("foo",), None, None, None, None, False, False
    )
    assert isinstance(result, Error)


def test_run_describe_command_standard_command_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers exception in handle_standard_command."""

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return Mock()

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    def fake_handle_standard_command(**kwargs: object) -> None:
        raise Exception("fail")

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.handle_standard_command",
        fake_handle_standard_command,
    )
    monkeypatch.setattr("vibectl.subcommands.describe_cmd.logger", Mock())
    result = run_describe_command(
        "pod", ("my-pod",), None, None, None, None, False, False
    )
    assert isinstance(result, Error)


def test_run_describe_command_configure_output_flags_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers exception in configure_output_flags."""

    def fake_configure_output_flags(*a: object, **kw: object) -> None:
        raise Exception("fail")

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr("vibectl.subcommands.describe_cmd.logger", Mock())
    result = run_describe_command(
        "pod", ("my-pod",), None, None, None, None, False, False
    )
    assert isinstance(result, Error)


def test_run_describe_command_configure_memory_flags_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers exception in configure_memory_flags."""

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return Mock()

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        raise Exception("fail")

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr("vibectl.subcommands.describe_cmd.logger", Mock())
    result = run_describe_command(
        "pod", ("my-pod",), None, None, None, None, False, False
    )
    assert isinstance(result, Error)
