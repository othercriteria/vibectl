"""
Tests for vibectl get command
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
def mock_llm_response() -> str:
    """Raw marked-up response from LLM"""
    return (
        "[bold]2 pods[/bold] in [blue]default namespace[/blue], "
        "all [green]Running[/green]"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Plain text version of the response (what we expect in test output)"""
    return "2 pods in default namespace, all Running"


@pytest.fixture
def mock_kubectl_output() -> str:
    return """NAME                     READY   STATUS    RESTARTS   AGE
nginx-6d4cf56db6-abc12   1/1     Running   0          1h
redis-7b6f89d5b7-def34   1/1     Running   0          2h"""


def test_get_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test basic get command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"])

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Vibe check header should not be present
        assert "✨ Vibe check:" not in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_with_raw_flag(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test get command with --raw flag"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = lambda key: None if key == "llm_model" else False

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods", "--raw"])

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (without emoji since it's stripped)
        assert "Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_with_raw_config(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test get command with show_raw_output config"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = lambda key: True if key == "show_raw_output" else None

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"])

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (without emoji since it's stripped)
        assert "Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_with_namespace(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
) -> None:
    """Test get command with namespace argument"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output) as mock_run:
        result = runner.invoke(cli, ["get", "pods", "-n", "kube-system"])

        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            ["get", "pods", "-n", "kube-system"], capture=True
        )


def test_get_command_no_output(runner: CliRunner) -> None:
    """Test get command when kubectl returns no output"""
    with patch("vibectl.cli.run_kubectl", return_value=None) as mock_run:
        result = runner.invoke(cli, ["get", "pods"])

        assert result.exit_code == 0
        mock_run.assert_called_once_with(["get", "pods"], capture=True)


def test_get_command_kubectl_error(runner: CliRunner) -> None:
    """Test get command when kubectl fails"""
    with patch("vibectl.cli.run_kubectl", side_effect=SystemExit(1)) as mock_run:
        result = runner.invoke(cli, ["get", "pods"])

        assert result.exit_code == 1
        mock_run.assert_called_once_with(["get", "pods"], capture=True)


def test_get_command_llm_error(runner: CliRunner, mock_kubectl_output: str) -> None:
    """Test get command when LLM fails"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ):
        result = runner.invoke(cli, ["get", "pods"])

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        assert "Could not get vibe check" in result.stderr
