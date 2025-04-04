"""Tests for the get command."""

import subprocess
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cli


@pytest.fixture
def mock_kubectl_output() -> str:
    """Mock kubectl output for testing."""
    return (
        "NAME                     READY   STATUS    RESTARTS   AGE\n"
        "nginx-pod               1/1     Running   0          1h\n"
        "postgres-pod            1/1     Running   0          2h\n"
        "redis-pod               1/1     Running   1          3h"
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Mock LLM response for testing."""
    return (
        "[bold]Pod Status Summary[/bold]\n"
        "✅ All pods are [green]Running[/green]\n"
        "🔄 [yellow]1 pod[/yellow] had restarts\n"
        "⏰ Oldest pod: [blue]redis-pod[/blue] (3h)"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Mock LLM plain response for testing."""
    return (
        "Pod Status Summary\n"
        "✅ All pods are Running\n"
        "🔄 1 pod had restarts\n"
        "⏰ Oldest pod: redis-pod (3h)"
    )


@pytest.fixture
def mock_config() -> Mock:
    """Mock config for testing."""
    mock = Mock()
    mock.get.return_value = None  # Let it use the default model
    return mock


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner that preserves stderr"""
    return CliRunner(mix_stderr=False)


def test_get_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test basic get command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=False)

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_with_raw_flag(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test get command with --raw flag"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods", "--raw"], catch_exceptions=False)

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present
        assert "✨ Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_with_raw_config(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test get command with show_raw_output config"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = lambda key: True if key == "show_raw_output" else None

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=True)

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present
        assert "✨ Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_with_namespace(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test get command with namespace argument"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["get", "pods", "-n", "kube-system"], catch_exceptions=True
        )

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_kubectl_error(runner: CliRunner, mock_config: Mock) -> None:
    """Test get command when kubectl fails"""
    error_msg = "Error: the server doesn't have a resource type 'invalid'"
    with patch(
        "vibectl.cli.run_kubectl",
        side_effect=subprocess.CalledProcessError(1, "kubectl", error_msg.encode()),
    ):
        result = runner.invoke(cli, ["get", "invalid"], catch_exceptions=True)

        assert result.exit_code == 1
        assert isinstance(result.exception, subprocess.CalledProcessError)
        assert error_msg.encode() == result.exception.output


def test_get_command_llm_error(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_config: Mock,
) -> None:
    """Test get command when LLM fails"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=False)

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output


def test_get_command_with_namespace_default(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test get command with namespace argument"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.return_value = True  # Show raw output

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["get", "pods", "-n", "default"], catch_exceptions=True
        )

        assert result.exit_code == 0
        assert "✨ Vibe check:" in result.output
        assert mock_llm_plain_response in result.output
