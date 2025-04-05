"""Tests for the events command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli


@pytest.fixture
def mock_kubectl_output() -> str:
    """Mock kubectl output for testing."""
    return (
        "LAST SEEN   TYPE      REASON              OBJECT                "
        "MESSAGE\n"
        "5m20s       Normal    Scheduled           pod/nginx-5f7cd9b8c-7sp69  "
        "Successfully assigned default/nginx-5f7cd9b8c-7sp69 to minikube\n"
        "4m56s       Normal    Pulled              pod/nginx-5f7cd9b8c-7sp69  "
        'Container image "nginx:1.17.0" already present on machine\n'
        "4m56s       Normal    Created             pod/nginx-5f7cd9b8c-7sp69  "
        "Created container nginx\n"
        "4m54s       Normal    Started             pod/nginx-5f7cd9b8c-7sp69  "
        "Started container nginx\n"
        "4m32s       Warning   BackOff             pod/webapp-86ddf46c9-ksvd6 "
        "Back-off restarting failed container\n"
        "3m12s       Warning   FailedScheduling    pod/redis-744b94f45d-pwts9 "
        "0/1 nodes are available: 1 Insufficient memory"
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Mock LLM response for testing."""
    return (
        "[bold]Event Summary[/bold]\n"
        "[green]Successfully scheduled[/green] [bold]nginx[/bold] pod "
        "[italic]5m20s ago[/italic]\n"
        "[green]Container started[/green] for [bold]nginx[/bold] pod "
        "[italic]4m54s ago[/italic]\n"
        "[yellow]BackOff[/yellow] warning for [bold]webapp[/bold] pod "
        "[italic]4m32s ago[/italic]\n"
        "[red]FailedScheduling[/red] for [bold]redis[/bold] pod due to "
        "[red]Insufficient memory[/red] [italic]3m12s ago[/italic]"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Mock LLM plain response for testing."""
    return (
        "Event Summary\n"
        "Successfully scheduled nginx pod 5m20s ago\n"
        "Container started for nginx pod 4m54s ago\n"
        "BackOff warning for webapp pod 4m32s ago\n"
        "FailedScheduling for redis pod due to Insufficient memory 3m12s ago"
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


def test_events_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test basic events command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        # Using only options defined in the Click command
        result = runner.invoke(cli, ["events"])

        assert result.exit_code == 0
        # Raw output should not be present by default
        assert mock_kubectl_output not in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_events_command_with_raw_flag(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test events command with --raw flag"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)

    # Create a normalized version of the output that removes whitespace differences
    normalized_output = " ".join(mock_kubectl_output.split())

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        # Test raw output only - using only options defined in the Click command
        result = runner.invoke(cli, ["events", "--raw", "--no-show-vibe"])

        assert result.exit_code == 0
        # Check if normalized content is present, ignoring whitespace differences
        assert normalized_output in " ".join(result.output.split())

        # Test raw output with vibe
        result = runner.invoke(cli, ["events", "--raw", "--show-vibe"])

        assert result.exit_code == 0
        # Check if normalized content is present, ignoring whitespace differences
        assert normalized_output in " ".join(result.output.split())
        assert "✨ Vibe check:" in result.output
        assert "Event Summary" in result.output


def test_events_command_llm_error(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_config: Mock,
) -> None:
    """Test events command when LLM fails"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")

    # Create a normalized version of the output that removes whitespace differences
    normalized_output = " ".join(mock_kubectl_output.split())

    # We need to ensure the raw output is displayed when LLM fails
    mock_config.get.side_effect = (
        lambda key, default=None: True if key == "show_raw_output" else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        # Using only options defined in the Click command
        result = runner.invoke(cli, ["events", "--show-raw-output"])

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        # Check if normalized content is present, ignoring whitespace differences
        assert normalized_output in " ".join(result.output.split())
        # Error message should be shown in stderr
        assert "Could not get vibe check" in result.stderr
        assert "LLM error" in result.stderr


def test_events_command_vibe_mode(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test events command in vibe mode (natural language)"""
    # Set up LLM to return a mock response
    mock_model = Mock()
    mock_model.prompt.side_effect = [
        # First call for planning
        Mock(text=lambda: "-n\ndefault\n---\nfield-selector=type=Warning"),
        # Second call for summarizing
        Mock(text=lambda: mock_llm_response),
    ]

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["events", "vibe", "show recent errors"])

        # Command should execute successfully
        assert result.exit_code == 0
        # Check output without relying on specific vibe content
        assert "✨ Vibe check:" in result.output


def test_events_vibe_error_response(
    runner: CliRunner,
    mock_config: Mock,
) -> None:
    """Test vibe mode with error response from planner"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "ERROR: Invalid field selector")

    with patch("llm.get_model", return_value=mock_model), patch(
        "vibectl.cli.Config", return_value=mock_config
    ), patch("vibectl.cli.console_manager.print_error") as mock_print_error:
        result = runner.invoke(
            cli, ["events", "vibe", "with an invalid selector"], catch_exceptions=True
        )

        assert result.exit_code == 1
        # Check that the error message was printed
        mock_print_error.assert_called_with("Invalid field selector")
