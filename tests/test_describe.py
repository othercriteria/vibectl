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
    """Mock kubectl output for testing."""
    return (
        "Name:         nginx-pod\n"
        "Namespace:    default\n"
        "Priority:     0\n"
        "Node:         worker-1/10.0.0.1\n"
        "Start Time:   Mon, 01 Jan 2024 10:00:00 +0000\n"
        "Labels:       app=nginx\n"
        "Status:       Running\n"
        "IP:           10.244.1.2\n"
        "IPs:\n"
        "  IP:  10.244.1.2\n"
        "Containers:\n"
        "  nginx:\n"
        "    Container ID:   containerd://abc123\n"
        "    Image:         nginx:latest\n"
        "    Image ID:      docker.io/library/nginx@sha256:xyz789\n"
        "    Port:          80/TCP\n"
        "    Host Port:     0/TCP\n"
        "    State:         Running\n"
        "      Started:     Mon, 01 Jan 2024 10:00:01 +0000\n"
        "    Ready:         True\n"
        "    Restart Count: 0\n"
        "    Limits:\n"
        "      cpu:     500m\n"
        "      memory:  512Mi\n"
        "    Requests:\n"
        "      cpu:     250m\n"
        "      memory:  256Mi"
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Mock LLM response for testing."""
    return (
        "[bold]nginx-pod[/bold] in [blue]default[/blue]: [green]Running[/green] "
        "on [blue]worker-1[/blue]\n"
        "Resources: [italic]CPU: 250m-500m, Memory: 256Mi-512Mi[/italic]"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Mock LLM plain response for testing."""
    return (
        "nginx-pod in default: Running on worker-1\n"
        "Resources: CPU: 250m-500m, Memory: 256Mi-512Mi"
    )


@pytest.fixture
def mock_config() -> Mock:
    """Mock config for testing."""
    mock = Mock()
    mock.get.side_effect = lambda key, default=None: default
    return mock


def test_describe_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test basic describe command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
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
    mock_config.get.side_effect = lambda key, default=None: default

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        # Test raw output only
        result = runner.invoke(
            cli, ["describe", "pod", "nginx-pod", "--raw", "--no-show-vibe"]
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" not in result.output
        assert mock_llm_plain_response not in result.output

        # Test raw output with vibe
        result = runner.invoke(
            cli, ["describe", "pod", "nginx-pod", "--raw", "--show-vibe"]
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
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
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])
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
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
        assert mock_llm_plain_response in result.output


def test_describe_command_token_limit(runner: CliRunner) -> None:
    """Test describe command with output exceeding token limit"""
    # Create a large output that would exceed the token limit
    large_output = "x" * (4 * 10001)  # Just over the 10k token limit
    mock_config = Mock()
    mock_config.get.side_effect = (
        lambda key, default=None: True if key == "show_raw_output" else default
    )

    # Create a mock model to handle the large output
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = (
        lambda: "kubectl describe output: Unable to analyze due to truncated content."
    )
    mock_model.prompt.return_value = mock_response

    with patch("vibectl.cli.run_kubectl", return_value=large_output), patch(
        "vibectl.cli.Config", return_value=mock_config
    ), patch("llm.get_model", return_value=mock_model):
        result = runner.invoke(
            cli,
            ["describe", "pod", "nginx-pod", "--show-raw-output"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        # Check for truncation warning in stderr
        assert "Output is too large for AI processing" in result.stderr

        # Check that at least some of the raw output is shown in stdout
        assert "x" * 50 in result.output or "xxxxx" in result.output

        # Verify that the vibe check attempted to analyze even with truncated output
        assert "✨ Vibe check:" in result.output
        assert "Unable to analyze due to truncated content" in result.output

        # Verify the LLM was called with a truncated prompt due to token limits
        assert len(mock_model.prompt.call_args[0][0]) < len(large_output)
        assert mock_model.prompt.called


def test_describe_command_token_limit_with_raw(runner: CliRunner) -> None:
    """Test describe command with output exceeding token limit and --raw flag"""
    large_output = "x" * (4 * 10001)
    mock_config = Mock()
    mock_config.get.side_effect = (
        lambda key, default=None: True if key == "show_raw_output" else default
    )

    # Create a mock model to handle the large output
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = (
        lambda: "The kubectl output contains only placeholder characters."
    )
    mock_model.prompt.return_value = mock_response

    with patch("vibectl.cli.run_kubectl", return_value=large_output), patch(
        "vibectl.cli.Config", return_value=mock_config
    ), patch("llm.get_model", return_value=mock_model):
        result = runner.invoke(
            cli,
            ["describe", "pod", "nginx-pod", "--raw", "--show-raw-output"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        # Check for truncation warning in stderr
        assert "Output is too large for AI processing" in result.stderr

        # Check that at least some of the raw output is shown in stdout
        assert "x" * 50 in result.output or "xxxxx" in result.output

        # Verify that the vibe check output includes the mocked response
        assert "✨ Vibe check:" in result.output
        assert "contains only placeholder characters" in result.output

        # Verify the LLM was called with a truncated prompt due to token limits
        assert len(mock_model.prompt.call_args[0][0]) < len(large_output)
        assert mock_model.prompt.called


def test_describe_command_no_output(runner: CliRunner) -> None:
    """Test describe command when kubectl returns no output"""
    mock_config = Mock()
    mock_config.get.side_effect = lambda key, default=None: default

    with patch("vibectl.cli.run_kubectl", return_value=None) as mock_run, patch(
        "vibectl.cli.Config", return_value=mock_config
    ):
        result = runner.invoke(cli, ["describe", "pod", "nginx-pod"])

        assert result.exit_code == 0
        mock_run.assert_called_once_with(["describe", "pod", "nginx-pod"], capture=True)


def test_describe_command_kubectl_error(runner: CliRunner) -> None:
    """Test describe command when kubectl fails"""
    mock_config = Mock()
    mock_config.get.side_effect = lambda key, default=None: default

    with patch("vibectl.cli.run_kubectl", side_effect=SystemExit(1)) as mock_run, patch(
        "vibectl.cli.Config", return_value=mock_config
    ):
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
    mock_config = Mock()
    # Ensure raw output is shown when LLM fails
    mock_config.get.side_effect = (
        lambda key, default=None: True if key == "show_raw_output" else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli,
            ["describe", "pod", "nginx-pod", "--show-raw-output"],
            catch_exceptions=False,
        )

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        # Error message should be shown in stderr
        assert "Could not get vibe check" in result.stderr
        assert "LLM error" in result.stderr
