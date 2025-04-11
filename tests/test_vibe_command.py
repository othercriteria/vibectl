"""Tests for the main vibe command to ensure it uses OutputFlags properly."""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.cli import vibe
from vibectl.command_handler import OutputFlags


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_handle_vibe_request() -> Generator[Mock, None, None]:
    """Mock the handle_vibe_request function."""
    with patch("vibectl.cli.handle_vibe_request") as mock:
        yield mock


@pytest.fixture
def mock_get_memory() -> Generator[Mock, None, None]:
    """Mock the get_memory function."""
    with patch("vibectl.cli.get_memory") as mock:
        mock.return_value = "Memory context"
        yield mock


def test_vibe_command_with_request(
    cli_runner: CliRunner,
    mock_handle_vibe_request: Mock,
    mock_get_memory: Mock,
    standard_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with a request."""
    with patch("vibectl.cli.configure_output_flags") as mock_flags:
        mock_flags.return_value = standard_output_flags
        
        # Run the command
        result = cli_runner.invoke(
            vibe,
            ["Create a deployment", "--show-raw-output"],
        )
        
        # Check that the command completed successfully
        assert result.exit_code == 0
        
        # Verify handle_vibe_request was called with OutputFlags
        mock_handle_vibe_request.assert_called_once()
        args, kwargs = mock_handle_vibe_request.call_args
        assert "output_flags" in kwargs
        assert kwargs["output_flags"] is standard_output_flags
        assert kwargs["request"] == "Create a deployment"


def test_vibe_command_without_request(
    cli_runner: CliRunner,
    mock_handle_vibe_request: Mock,
    mock_get_memory: Mock,
    standard_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command without a request."""
    with patch("vibectl.cli.configure_output_flags") as mock_flags:
        mock_flags.return_value = standard_output_flags
        
        # Run the command
        result = cli_runner.invoke(
            vibe,
            ["--show-raw-output"],
        )
        
        # Check that the command completed successfully
        assert result.exit_code == 0
        
        # Verify handle_vibe_request was called with OutputFlags
        mock_handle_vibe_request.assert_called_once()
        args, kwargs = mock_handle_vibe_request.call_args
        assert "output_flags" in kwargs
        assert kwargs["output_flags"] is standard_output_flags
        assert kwargs["request"] == ""
        assert kwargs["autonomous_mode"] is True


def test_vibe_command_with_yes_flag(
    cli_runner: CliRunner,
    mock_handle_vibe_request: Mock,
    mock_get_memory: Mock,
    standard_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with the yes flag."""
    with patch("vibectl.cli.configure_output_flags") as mock_flags:
        mock_flags.return_value = standard_output_flags
        
        # Run the command
        result = cli_runner.invoke(
            vibe,
            ["Create a deployment", "--yes", "--show-raw-output"],
        )
        
        # Check that the command completed successfully
        assert result.exit_code == 0
        
        # Verify handle_vibe_request was called with yes=True
        mock_handle_vibe_request.assert_called_once()
        args, kwargs = mock_handle_vibe_request.call_args
        assert "yes" in kwargs
        assert kwargs["yes"] is True 