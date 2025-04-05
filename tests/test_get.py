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
    mock.get.side_effect = lambda key, default=None: default
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
        # Test raw output only
        result = runner.invoke(
            cli, ["get", "pods", "--raw", "--no-show-vibe"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output

        # Test raw output with vibe
        result = runner.invoke(
            cli, ["get", "pods", "--raw", "--show-vibe"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
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
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=True)
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
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=True)
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
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
    mock_config.get.side_effect = lambda key, default=None: default

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
        # CLI handler is calling sys.exit(1) in handle_vibe_request when run_kubectl raises
        assert isinstance(result.exception, SystemExit)
        # Cannot check the CalledProcessError output since it's being caught in handle_vibe_request


def test_get_command_llm_error(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_config: Mock,
) -> None:
    """Test get command when LLM fails"""
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("LLM error")

    # We need to ensure the raw output is displayed when LLM fails
    mock_config.get.side_effect = (
        lambda key, default=None: True if key == "show_raw_output" else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["get", "pods", "--show-raw-output"], catch_exceptions=False
        )

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        # Error message should be shown in stderr
        assert "Could not get vibe check" in result.stderr
        assert "LLM error" in result.stderr


def test_get_command_with_show_raw_output_flag(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test get command with --show-raw-output flag"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["get", "pods", "--show-raw-output"], catch_exceptions=False
        )

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (default show_vibe=True)
        assert "✨ Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_with_show_raw_output_config(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test get command with show_raw_output config"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = (
        lambda key, default=None: True if key == "show_raw_output" else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=True)

        assert result.exit_code == 0
        # Raw output should be present
        assert mock_kubectl_output in result.output
        # Vibe check header should be present (default show_vibe=True)
        assert "✨ Vibe check:" in result.output
        # Check LLM summary is displayed (without markup)
        assert mock_llm_plain_response in result.output


def test_get_command_with_show_vibe_config_false(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test get command with show_vibe config set to false"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    mock_config.get.side_effect = (
        lambda key, default=None: False if key == "show_vibe" else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=True)

        assert result.exit_code == 0
        # Raw output should not be present (default show_raw_output=False)
        assert mock_kubectl_output not in result.output
        # Vibe check should not be present
        assert "✨ Vibe check:" not in result.output
        # LLM summary should not be displayed
        assert mock_llm_plain_response not in result.output


def test_get_command_flag_overrides_config(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test that command flags override config values"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    # Config has show_raw_output=True and show_vibe=False
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
        # Override config with flags: show_raw_output=False and show_vibe=True
        result = runner.invoke(
            cli,
            ["get", "pods", "--no-show-raw-output", "--show-vibe"],
            catch_exceptions=True,
        )

        assert result.exit_code == 0
        # Raw output should not be present (flag overrides config)
        assert mock_kubectl_output not in result.output
        # Vibe check should be present (flag overrides config)
        assert "✨ Vibe check:" in result.output
        # LLM summary should be displayed (flag overrides config)
        assert mock_llm_plain_response in result.output


def test_get_command_suppress_output_warning(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test get command with suppress_output_warning config set to true"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: mock_llm_response)
    mock_config = Mock()
    # Set both show_raw_output and show_vibe to false, but enable suppress_output_warning
    mock_config.get.side_effect = lambda key, default=None: (
        True
        if key == "suppress_output_warning"
        else False
        if key in ["show_raw_output", "show_vibe"]
        else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=True)

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Vibe check should not be present
        assert "✨ Vibe check:" not in result.output
        # LLM summary should not be displayed
        assert mock_llm_plain_response not in result.output
        # Warning should be suppressed
        assert "Neither raw output nor vibe output is enabled" not in result.stderr

    # Now test with suppress_output_warning set to false (default)
    mock_config.get.side_effect = lambda key, default=None: (
        False
        if key in ["show_raw_output", "show_vibe", "suppress_output_warning"]
        else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["get", "pods"], catch_exceptions=True)

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Vibe check should not be present
        assert "✨ Vibe check:" not in result.output
        # LLM summary should not be displayed
        assert mock_llm_plain_response not in result.output
        # Warning should be shown
        assert "Neither raw output nor vibe output is enabled" in result.stderr
