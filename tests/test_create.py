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
def mock_plan_response() -> str:
    """Mock LLM plan response for testing."""
    return (
        "-n\ndefault\n---\n"
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        "  name: nginx-hello\n"
        "  labels:\n"
        "    app: nginx\n"
        "spec:\n"
        "  containers:\n"
        "  - name: nginx\n"
        "    image: nginx:latest\n"
        "    ports:\n"
        "    - containerPort: 80"
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Mock LLM response for testing."""
    return (
        "Created [bold]nginx-hello[/bold] pod in [blue]default namespace[/blue]\n"
        "[green]Successfully created[/green] with [italic]default settings[/italic]"
    )


@pytest.fixture
def mock_llm_plain_response() -> str:
    """Mock LLM plain response for testing."""
    return (
        "Created nginx-hello pod in default namespace\n"
        "Successfully created with default settings"
    )


@pytest.fixture
def mock_config() -> Mock:
    """Mock config for testing."""
    mock = Mock()
    mock.get.side_effect = lambda key, default=None: default
    return mock


def test_create_vibe_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_plan_response: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
    mock_config: Mock,
) -> None:
    """Test basic vibe command functionality"""
    mock_model = Mock()
    mock_model.prompt.side_effect = [
        Mock(text=lambda: mock_plan_response),  # First call for planning
        Mock(text=lambda: mock_llm_response),  # Second call for summarizing
    ]

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(cli, ["create", "vibe", "an nginx hello world pod"])

        assert result.exit_code == 0
        # Raw output should not be present
        assert mock_kubectl_output not in result.output
        # Vibe check header should be present
        assert "✨ Vibe check:" in result.output
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
        assert "Invalid resource type" in result.stderr


def test_create_vibe_command_with_raw_flag(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_plan_response: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test vibe command with --raw flag"""
    # Create a separate mock for each prompt call to ensure deterministic behavior
    plan_mock = Mock()
    plan_mock.text = lambda: mock_plan_response

    summary_mock = Mock()
    summary_mock.text = lambda: mock_llm_response

    mock_model = Mock()
    # Return different responses for each call
    mock_model.prompt.side_effect = [plan_mock, summary_mock]

    mock_config = Mock()
    mock_config.get.side_effect = lambda key, default=None: default

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        # Test raw output only
        result = runner.invoke(
            cli,
            ["create", "vibe", "an nginx hello world pod", "--raw", "--no-show-vibe"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" not in result.output

        # Reset the mock between runs
        mock_model.prompt.side_effect = [plan_mock, summary_mock]

        # Test raw output with vibe
        result = runner.invoke(
            cli,
            ["create", "vibe", "an nginx hello world pod", "--raw", "--show-vibe"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
        assert mock_llm_plain_response in result.output


def test_create_vibe_command_with_raw_config(
    runner: CliRunner,
    mock_kubectl_output: str,
    mock_plan_response: str,
    mock_llm_response: str,
    mock_llm_plain_response: str,
) -> None:
    """Test vibe command with show_raw_output config"""
    # Create separate mocks for deterministic behavior
    plan_mock = Mock()
    plan_mock.text = lambda: mock_plan_response

    summary_mock = Mock()
    summary_mock.text = lambda: mock_llm_response

    mock_model = Mock()
    mock_model.prompt.side_effect = [plan_mock, summary_mock]

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
        result = runner.invoke(
            cli, ["create", "vibe", "an nginx hello world pod"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" not in result.output

    # Reset the mock and mock_config for the second test
    mock_model = Mock()
    mock_model.prompt.side_effect = [plan_mock, summary_mock]

    # Test raw output with vibe
    mock_config = Mock()
    mock_config.get.side_effect = (
        lambda key, default=None: True
        if key in ["show_raw_output", "show_vibe"]
        else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        result = runner.invoke(
            cli, ["create", "vibe", "an nginx hello world pod"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
        assert mock_llm_plain_response in result.output


def test_create_vibe_command_invalid_plan_format(
    runner: CliRunner,
) -> None:
    """Test vibe command with invalid plan format"""
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = lambda: "invalid format without manifest"
    mock_model.prompt.return_value = mock_response

    mock_config = Mock()
    mock_config.get.return_value = None  # Let it use the default model
    mock_config.get.side_effect = (
        lambda key, default=None: False
    )  # Disable show_raw_output and show_vibe warnings

    with patch("llm.get_model", return_value=mock_model), patch(
        "vibectl.cli.Config", return_value=mock_config
    ):
        # We expect sys.exit(1) to be called when invalid format is detected
        result = runner.invoke(
            cli, ["create", "vibe", "an nginx hello world pod"], catch_exceptions=True
        )

        assert result.exit_code == 1
        # Match either of these possible error messages
        assert any(
            [
                "Invalid response format from planner" in result.stderr,
                "error: Unexpected args" in result.stderr,
            ]
        )


def test_create_command_basic(
    runner: CliRunner,
    mock_kubectl_output: str,
) -> None:
    """Test basic create command functionality"""
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "Created resource successfully")
    mock_config = Mock()
    # Ensure both raw output and vibe are shown
    mock_config.get.side_effect = (
        lambda key, default=None: True
        if key in ["show_raw_output", "show_vibe"]
        else default
    )

    with patch("vibectl.cli.run_kubectl", return_value=mock_kubectl_output), patch(
        "llm.get_model", return_value=mock_model
    ), patch("vibectl.cli.Config", return_value=mock_config):
        cmd = ["create", "pod", "nginx-hello", "--image=nginx", "--show-raw-output"]
        result = runner.invoke(cli, cmd, catch_exceptions=False)

        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        assert "✨ Vibe check:" in result.output
        assert "Created resource successfully" in result.output


def test_create_command_llm_error(
    runner: CliRunner,
    mock_kubectl_output: str,
) -> None:
    """Test create command when LLM fails"""
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
        cmd = ["create", "pod", "nginx-hello", "--image=nginx", "--show-raw-output"]
        result = runner.invoke(cli, cmd, catch_exceptions=False)

        # Should still succeed and show kubectl output even if LLM fails
        assert result.exit_code == 0
        assert mock_kubectl_output in result.output
        # Error message should be shown in stderr
        assert "Could not get vibe check" in result.stderr
        assert "LLM error" in result.stderr
