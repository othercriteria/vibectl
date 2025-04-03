"""Tests for the logs command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli


@pytest.fixture
def mock_kubectl_output() -> str:
    """Sample kubectl logs output"""
    return (
        "2024-03-20 10:15:00 Starting container...\n"
        "2024-03-20 10:15:01 Connecting to database...\n"
        "2024-03-20 10:15:02 Connected successfully\n"
        "2024-03-20 10:15:10 Warning: Slow query detected (10s)\n"
        "2024-03-20 10:15:15 Error: Connection timeout\n"
        "2024-03-20 10:15:16 Error: Connection timeout\n"
        "2024-03-20 10:15:17 Error: Connection timeout\n"
        "2024-03-20 10:15:20 Reconnected to database"
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Raw marked-up response from LLM"""
    return (
        "[bold]Container startup[/bold] at [italic]2024-03-20 10:15:00[/italic]\n"
        "[green]Successfully connected[/green] to [blue]database[/blue]\n"
        "[yellow]Slow query detected[/yellow] [italic]10s ago[/italic]\n"
        "[red]3 connection timeouts[/red] in past minute"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Plain text version of the response (what we expect in test output)"""
    return (
        "Container startup at 2024-03-20 10:15:00\n"
        "Successfully connected to database\n"
        "Slow query detected 10s ago\n"
        "3 connection timeouts in past minute"
    )


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner that preserves stderr"""
    return CliRunner(mix_stderr=False, env={"FORCE_COLOR": "0"})


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
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"])

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Vibe check header should not be present
        assert "✨ Vibe check:" not in result.output
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
        result = runner.invoke(cli, ["logs", "pod/nginx-pod", "--raw"])

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (without emoji since it's stripped)
        assert "Vibe check:" in result.output
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
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"])

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (without emoji since it's stripped)
        assert "Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_logs_command_with_container(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
) -> None:
    """Test logs command with container argument"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output) as mock_run:
        result = runner.invoke(cli, ["logs", "pod/nginx-pod", "-c", "nginx"])

        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            ["logs", "pod/nginx-pod", "-c", "nginx"], capture=True
        )


def test_logs_command_token_limit(runner: CliRunner) -> None:
    """Test logs command with output exceeding token limit"""
    # Create a large output that would exceed the token limit
    large_output = "x" * (4 * 10001)  # Just over the 10k token limit

    with patch("vibectl.cli.run_kubectl", return_value=large_output):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=False)

        assert result.exit_code == 0
        # Should show truncation message in output
        assert "truncated" in result.output
        # Raw output should not be shown without --raw
        assert large_output not in result.output


def test_logs_command_token_limit_with_raw(runner: CliRunner) -> None:
    """Test logs command with output exceeding token limit and --raw flag"""
    large_output = "x" * (4 * 10001)

    with patch("vibectl.cli.run_kubectl", return_value=large_output):
        result = runner.invoke(
            cli, ["logs", "pod/nginx-pod", "--raw"], catch_exceptions=False
        )

        assert result.exit_code == 0
        # Raw output should be shown first
        assert "x" * 50 in result.output  # Check that some of the output is shown
        # Then truncation message
        assert "truncated" in result.output
        # Then summary
        assert "✨ Vibe check:" in result.output


def test_logs_command_llm_error(
    runner: CliRunner,
    mock_kubectl_output: str,
) -> None:
    """Test logs command when LLM fails"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ):
        result = runner.invoke(cli, ["logs", "pod/nginx-pod"], catch_exceptions=False)

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        assert "Could not get vibe check" in result.stderr
