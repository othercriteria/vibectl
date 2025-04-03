"""
Tests for vibectl create command
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
    """Mock output from kubectl create"""
    return "pod/nginx-hello created"


@pytest.fixture
def mock_llm_response() -> str:
    """Raw marked-up response from LLM"""
    return (
        "Created [bold]nginx-hello[/bold] pod in [blue]default namespace[/blue]\n"
        "[green]Successfully created[/green] with [italic]default settings[/italic]"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Plain text version of the response (what we expect in test output)"""
    return (
        "Created nginx-hello pod in default namespace\n"
        "Successfully created with default settings"
    )


@pytest.fixture
def mock_plan_response() -> str:
    """Mock response for planning kubectl create command"""
    return """-n
default
---
apiVersion: v1
kind: Pod
metadata:
  name: nginx-hello
  labels:
    app: nginx
spec:
  containers:
  - name: nginx
    image: nginx:latest
    ports:
    - containerPort: 80"""


def test_create_vibe_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_plan_response: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test basic vibe command functionality"""
    mock_model = Mock()
    mock_model.prompt.side_effect = [
        Mock(text=lambda: mock_plan_response),  # First call for planning
        Mock(text=lambda: mock_llm_response),  # Second call for summarizing
    ]
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["create", "vibe", "an nginx hello world pod"])

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Vibe check header should not be present
        assert "✨ Vibe check:" not in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_create_vibe_command_error_response(
    runner: CliRunner,
) -> None:
    """Test vibe command with error response from planner"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "ERROR: Invalid resource type")
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("llm.get_model", return_value=mock_model), patch(
        "vibectl.cli.Config", return_value=mock_config
    ):
        result = runner.invoke(cli, ["create", "vibe", "an invalid resource"])

        assert result.exit_code == 1
        assert "Error: Invalid resource type" in result.stderr


def test_create_vibe_command_with_raw_flag(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_plan_response: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test vibe command with --raw flag"""
    mock_model = Mock()
    mock_model.prompt.side_effect = [
        Mock(text=lambda: mock_plan_response),  # First call for planning
        Mock(text=lambda: mock_llm_response),  # Second call for summarizing
    ]
    mock_config = Mock()
    mock_config.get.side_effect = lambda key: None if key == "llm_model" else False

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["create", "vibe", "an nginx hello world pod", "--raw"]
        )

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (without emoji since it's stripped)
        assert "Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_create_vibe_command_with_raw_config(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_plan_response: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test vibe command with show_raw_output config"""
    mock_model = Mock()
    mock_model.prompt.side_effect = [
        Mock(text=lambda: mock_plan_response),  # First call for planning
        Mock(text=lambda: mock_llm_response),  # Second call for summarizing
    ]
    mock_config = Mock()
    mock_config.get.side_effect = lambda key: True if key == "show_raw_output" else None

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["create", "vibe", "an nginx hello world pod"])

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (without emoji since it's stripped)
        assert "Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_create_vibe_command_invalid_plan_format(
    runner: CliRunner,
) -> None:
    """Test vibe command with invalid plan format"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(
        text=lambda: "invalid format without manifest"
    )
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("llm.get_model", return_value=mock_model), patch(
        "vibectl.cli.Config", return_value=mock_config
    ):
        result = runner.invoke(cli, ["create", "vibe", "an nginx hello world pod"])

        assert result.exit_code == 1
        assert "Error: Invalid response format from planner" in result.stderr


def test_create_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test basic create command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["create", "pod", "nginx-hello", "--image=nginx"])

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Vibe check header should not be present
        assert "✨ Vibe check:" not in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_create_command_llm_error(
    runner: CliRunner,
    mock_kubectl_output: str,
) -> None:
    """Test create command when LLM fails"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ):
        cmd = ["create", "pod", "nginx-hello", "--image=nginx"]
        result = runner.invoke(cli, cmd)

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "Could not get vibe check" in result.stderr
