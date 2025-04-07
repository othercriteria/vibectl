"""Tests for the CLI cluster-info command.

This module tests the cluster-info command functionality of vibectl.
"""

from typing import Generator
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import cluster_info


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture providing a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Fixture providing a mocked run_kubectl function."""
    with patch("vibectl.cli.run_kubectl") as mock:
        mock.return_value = "test output"
        yield mock


@pytest.fixture
def mock_handle_command_output() -> Generator[Mock, None, None]:
    """Fixture providing a mocked handle_command_output function."""
    with patch("vibectl.cli.handle_command_output") as mock:
        yield mock


@pytest.fixture
def mock_handle_vibe_request() -> Generator[Mock, None, None]:
    """Fixture providing a mocked handle_vibe_request function."""
    with patch("vibectl.cli.handle_vibe_request") as mock:
        yield mock


@pytest.fixture
def mock_configure_output_flags() -> Generator[Mock, None, None]:
    """Fixture providing a mocked configure_output_flags function."""
    with patch("vibectl.cli.configure_output_flags") as mock:
        mock.return_value = (False, True, False, "test-model")
        yield mock


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Fixture providing a mocked console manager."""
    with patch("vibectl.cli.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_handle_exception() -> Generator[Mock, None, None]:
    """Fixture providing a mocked handle_exception function."""
    with patch("vibectl.cli.handle_exception") as mock:
        yield mock


def test_cluster_info_basic(
    mock_handle_command_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_output_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test basic cluster-info command functionality."""
    # Setup
    mock_run_kubectl.return_value = (
        "Kubernetes control plane is running at https://example:6443"
    )

    # Execute
    result = cli_runner.invoke(cluster_info, [])

    # Assert
    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_command_output.assert_called_once()


def test_cluster_info_with_args(
    mock_handle_command_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_output_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test cluster-info command with additional arguments."""
    # Setup
    mock_run_kubectl.return_value = "Detailed cluster info"

    # Execute
    result = cli_runner.invoke(cluster_info, ["dump"])

    # Assert
    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["cluster-info", "dump"], capture=True)
    mock_handle_command_output.assert_called_once()


def test_cluster_info_with_flags(
    mock_handle_command_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_output_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test cluster-info command with output flags."""
    # Setup
    mock_run_kubectl.return_value = (
        "Kubernetes control plane is running at https://example:6443"
    )

    # Execute
    result = cli_runner.invoke(
        cluster_info, ["--show-raw-output", "--no-show-vibe", "--model", "test-model"]
    )

    # Assert
    assert result.exit_code == 0
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=True, show_vibe=False, model="test-model"
    )
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_command_output.assert_called_once()


def test_cluster_info_no_output(
    mock_handle_command_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_output_flags: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test cluster-info command when kubectl returns no output."""
    # Setup
    mock_run_kubectl.return_value = ""

    # Execute
    result = cli_runner.invoke(cluster_info, [])

    # Assert
    assert result.exit_code == 0
    mock_run_kubectl.assert_called_once_with(["cluster-info"], capture=True)
    mock_handle_command_output.assert_not_called()


def test_cluster_info_vibe_request(
    mock_handle_vibe_request: Mock, cli_runner: CliRunner
) -> None:
    """Test cluster-info command with vibe request."""
    # Execute
    result = cli_runner.invoke(
        cluster_info, ["vibe", "show", "me", "cluster", "health"]
    )

    # Assert
    assert result.exit_code == 0
    mock_handle_vibe_request.assert_called_once()
    args, kwargs = mock_handle_vibe_request.call_args
    assert kwargs["request"] == "show me cluster health"
    assert kwargs["command"] == "cluster-info"


def test_cluster_info_vibe_no_request(
    cli_runner: CliRunner, mock_console: Mock
) -> None:
    """Test cluster-info vibe command without a request."""
    # Execute
    result = cli_runner.invoke(cluster_info, ["vibe"])

    # Assert
    assert result.exit_code == 1
    mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


def test_cluster_info_error_handling(
    mock_run_kubectl: Mock,
    mock_configure_output_flags: Mock,
    mock_handle_exception: Mock,
    cli_runner: CliRunner,
) -> None:
    """Test cluster-info command error handling."""
    # Setup
    mock_run_kubectl.side_effect = Exception("Test error")

    # Execute
    result = cli_runner.invoke(cluster_info, [])

    # Assert
    assert result.exit_code == 0  # Click runner catches the exception
    mock_handle_exception.assert_called_once()
