"""
Tests for vibectl describe command
"""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner that preserves stderr"""
    return CliRunner(mix_stderr=False)


@pytest.fixture
def mock_kubectl_output() -> str:
    """Sample kubectl describe output"""
    return """Name:         nginx-pod
Namespace:    default
Priority:     0
Node:         worker-1/10.0.0.1
Start Time:   Mon, 01 Jan 2024 00:00:00 +0000
Labels:       app=nginx
Status:       Running
IP:           10.244.0.1
Containers:
  nginx:
    Image:          nginx:1.25
    State:          Running
      Started:      Mon, 01 Jan 2024 00:00:00 +0000
    Ready:          True
    Restart Count: 0
    Limits:
      cpu:     500m
      memory:  512Mi
    Requests:
      cpu:     250m
      memory:  256Mi"""


@pytest.fixture
def mock_llm_response() -> str:
    """Raw marked-up response from LLM"""
    return (
        "[bold]nginx-pod[/bold] in [blue]default[/blue]: [green]Running[/green] on "
        "[blue]worker-1[/blue]\nResources: [italic]CPU: 250m-500m, Memory: 256Mi-512Mi"
        "[/italic]"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Plain text version of the response (what we expect in test output)"""
    return (
        "nginx-pod in default: Running on worker-1\n"
        "Resources: CPU: 250m-500m, Memory: 256Mi-512Mi"
    )


def test_describe_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test basic describe command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Vibe check header should not be present
        assert "✨ Vibe check:" not in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_describe_command_with_raw_flag(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test describe command with --raw flag"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = lambda key: None if key == "llm_model" else False

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod", "--raw"])

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (without emoji since it's stripped)
        assert "Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_describe_command_with_raw_config(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test describe command with show_raw_output config"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = lambda key: True if key == "show_raw_output" else None

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (without emoji since it's stripped)
        assert "Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_describe_command_token_limit(runner: CliRunner) -> None:
    """Test describe command with output exceeding token limit"""
    # Create a large output that would exceed the token limit
    large_output = "x" * (4 * 10001)  # Just over the 10k token limit

    with patch("vibectl.cli.run_kubectl", return_value=large_output):
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])

        assert result.exit_code == 0
        assert "Output is too large for AI processing" in result.stderr
        # Raw output should not be shown without --raw
        assert large_output not in result.output


def test_describe_command_token_limit_with_raw(runner: CliRunner) -> None:
    """Test describe command with output exceeding token limit and --raw flag"""
    large_output = "x" * (4 * 10001)

    with patch("vibectl.cli.run_kubectl", return_value=large_output):
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod", "--raw"])

        assert result.exit_code == 0
        assert "Output is too large for AI processing" in result.stderr
        # Raw output should be shown with --raw, but no summary
        assert "x" * 50 in result.output  # Check that some of the output is shown
        assert "✨ Vibe check:" not in result.output


def test_describe_command_no_output(runner: CliRunner) -> None:
    """Test describe command when kubectl returns no output"""
    with patch("vibectl.cli.run_kubectl", return_value=None) as mock_run:
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])

        assert result.exit_code == 0
        mock_run.assert_called_once_with(["describe", "pod", "nginx-pod"], capture=True)


def test_describe_command_kubectl_error(runner: CliRunner) -> None:
    """Test describe command when kubectl fails"""
    with patch("vibectl.cli.run_kubectl", side_effect=SystemExit(1)) as mock_run:
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])

        assert result.exit_code == 1
        mock_run.assert_called_once_with(["describe", "pod", "nginx-pod"], capture=True)


def test_describe_command_llm_error(
    runner: CliRunner,
    mock_kubectl_output: str,
) -> None:
    """Test describe command when LLM fails"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ):
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        assert "Could not get vibe check" in result.stderr
