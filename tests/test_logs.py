"""Tests for the logs command."""

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
def runner() -> CliRunner:
    """Create a Click test runner that preserves stderr"""
    return CliRunner(mix_stderr=False)


@pytest.fixture
def large_output() -> str:
    """Create a large output that would exceed the token limit.
    Using a smaller string repeated instead of a huge multiplication."""
    base = "x" * 100 + "\n"  # 101 chars per line
    return base * 400  # ~40k chars total, well over the 10k token limit


def test_logs_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test basic logs command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=True)

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
    mock_config.get.side_effect = lambda key: None if key == "llm_model" else False

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["logs", "pod/nginx-pod", "--raw"], catch_exceptions=True
        )

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present
        assert "✨ Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
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
    mock_config.get.side_effect = lambda key: True if key == "show_raw_output" else None

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=True)

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present
        assert "✨ Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
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
    mock_config.get.return_value = None  # Let it use the default model

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


def test_logs_command_token_limit(runner: CliRunner, large_output: str) -> None:
    """Test logs command with output exceeding token limit"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(
        text=lambda: (
            "Unable to analyze container logs - provided content contains "
            "only placeholder characters ('x')"
        )
    )
    mock_config = Mock()
    mock_config.get.return_value = True  # Show raw output

    with patch("vibectl.cli.run_kubectl", return_value=large_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=True)

        assert result.exit_code == 0
        assert "Note: Output truncated for LLM analysis" in result.stderr
        # Check that the LLM output mentions placeholder characters
        assert "Unable to analyze container logs" in result.output
        assert "characters ('x')" in result.output


def test_logs_command_token_limit_with_raw(
    runner: CliRunner, large_output: str
) -> None:
    """Test logs command with output exceeding token limit and raw output"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(
        text=lambda: (
            "Unable to analyze container logs - provided content contains "
            "only placeholder characters ('x')"
        )
    )
    mock_config = Mock()
    mock_config.get.side_effect = lambda key: True if key == "show_raw_output" else None

    with patch("vibectl.cli.run_kubectl", return_value=large_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["logs", "pod/nginx-pod", "--raw"], catch_exceptions=True
        )

        assert result.exit_code == 0
        assert "Note: Output truncated for LLM analysis" in result.stderr
        # Check that the raw output contains the placeholder text and vibe check
        assert "✨ Vibe check:" in result.output
        assert "Unable to analyze container logs" in result.output
        assert (
            "characters ('x')" in result.output
        )  # Simplified assertion to match actual output


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
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=True)

        assert result.exit_code == 0  # Command should still succeed
        assert mock_kubectl_output in result.output  # Raw output should be shown
        assert (
            "Could not get vibe check: LLM error" in result.stderr
        )  # Error message should be shown
