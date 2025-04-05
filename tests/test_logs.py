"""Tests for the logs command."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli


@pytest.fixture
def mock_kubectl_output() -> str:
    """Mock kubectl output for testing."""
    return (
        "2024-03-20 10:15:00 Starting container...\n"
        "2024-03-20 10:15:01 Connecting to database...\n"
        "2024-03-20 10:15:02 Connect... Error: Connection timeout\n"
        "2024-03-20 10:15:17 Error: Connection timeout\n"
        "2024-03-20 10:15:20 Reconnected to database"
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Mock LLM response for testing."""
    return (
        "[bold]Container startup[/bold] at [italic]2024-03-20 10:15:00[/italic]\n"
        "[green]Successfully connected[/green] to [blue]database[/blue]\n"
        "[yellow]Slow query detected[/yellow] [italic]10s ago[/italic]\n"
        "[red]3 connection timeouts[/red] in past minute"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Mock LLM plain response for testing."""
    return (
        "Container startup at 2024-03-20 10:15:00\n"
        "Successfully connected to database\n"
        "Slow query detected 10s ago\n"
        "3 connection timeouts in past minute"
    )


@pytest.fixture
def mock_config() -> Mock:
    """Mock config for testing."""
    mock = Mock()
    mock.get.side_effect = lambda key, default=None: default
    return mock


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner that preserves stderr"""
    return CliRunner(mix_stderr=False)


@pytest.fixture
def large_output(tmp_path: Path) -> str:
    """Create a large output that would exceed token limit"""
    # Create a string that's just over the 10k token limit
    return "x" * (4 * 10001) + "\n"


def test_logs_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test basic logs command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=False)

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_logs_command_with_raw_flag(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test logs command with --raw flag"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = lambda key, default=None: default

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        # Test raw output only
        result = runner.invoke(
            cli,
            ["logs", "pod/nginx-pod", "--raw", "--no-show-vibe"],
            catch_exceptions=True,
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" not in result.output
        assert mock_llm_plain_response not in result.output

        # Test raw output with vibe
        result = runner.invoke(
            cli,
            ["logs", "pod/nginx-pod", "--raw", "--show-vibe"],
            catch_exceptions=True,
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
        assert mock_llm_plain_response in result.output


def test_logs_command_with_raw_config(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test logs command with show_raw_output config"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()

    # Test raw output only
    mock_config.get.side_effect = (
        lambda key, default=None: True
        if key == "show_raw_output"
        else False
        if key == "show_vibe"
        else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=True)
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" not in result.output
        assert mock_llm_plain_response not in result.output

    # Test raw output with vibe
    mock_config.get.side_effect = (
        lambda key, default=None: True
        if key in ["show_raw_output", "show_vibe"]
        else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=True)
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
        assert mock_llm_plain_response in result.output


def test_logs_command_with_container(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test logs command with container argument"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = lambda key, default=None: default

    with patch(
        "vibectl.cli.run_kubectl", return_value=mock_kubectl_output
    ) as mock_run, patch("llm.get_model", return_value=mock_model), patch(
        "vibectl.cli.Config", return_value=mock_config
    ):
        result = runner.invoke(
            cli, ["logs", "pod/nginx-pod", "-c", "nginx"], catch_exceptions=False
        )

        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            ["logs", "pod/nginx-pod", "-c", "nginx"], capture=True
        )
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_logs_command_token_limit_with_raw(
    runner: CliRunner, large_output: str
) -> None:
    """Test logs command with output exceeding token limit and raw output"""
    # Create a proper mock for the LLM model
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = lambda: (
        "Unable to analyze container logs - provided content contains "
        "only placeholder characters ('x')"
    )
    mock_model.prompt.return_value = mock_response

    mock_config = Mock()
    mock_config.get.side_effect = (
        lambda key, default=None: True if key == "show_raw_output" else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=large_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli,
            ["logs", "pod/nginx-pod", "--raw", "--show-raw-output"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        # 1. We see the truncation warning in stderr
        assert "Output is too large for AI processing" in result.stderr

        # 2. Verify the raw output contains 'x's
        assert "x" * 50 in result.output or "xxxxx" in result.output

        # 3. The vibe check shows the LLM's attempt to analyze the truncated content
        assert "✨ Vibe check:" in result.output
        assert "Unable to analyze container logs" in result.output

        # 4. Verify the LLM was called with a truncated prompt due to token limits
        assert len(mock_model.prompt.call_args[0][0]) < len(large_output)
        assert mock_model.prompt.called


def test_logs_command_llm_error(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test logs command when LLM fails"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")
    mock_config = Mock()
    # Ensure raw output is shown when LLM fails
    mock_config.get.side_effect = (
        lambda key, default=None: True if key == "show_raw_output" else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["logs", "pod/nginx-pod", "--show-raw-output"], catch_exceptions=False
        )

        assert result.exit_code == 0  # Command should still succeed
        assert mock_kubectl_output in result.output  # Raw output should be shown
        # Error message should be shown in stderr
        assert "Could not get vibe check" in result.stderr
        assert "LLM error" in result.stderr
