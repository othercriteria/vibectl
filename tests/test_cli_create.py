"""Tests for the CLI create command.

This module tests the create command functionality of vibectl with focus on error handling.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, Mock
from typing import Generator, Tuple

from vibectl.cli import create
from vibectl.prompt import PLAN_CREATE_PROMPT


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture providing a Click CLI test runner."""
    return CliRunner()


def test_create_vibe_request(cli_runner: CliRunner) -> None:
    """Test create vibe request handling."""
    with patch("vibectl.cli.handle_vibe_request") as mock_handle_vibe_request:
        # Execute
        with patch("sys.exit"):
            result = cli_runner.invoke(create, ["vibe", "create a deployment"])
        
        # Assert
        assert result.exit_code == 0
        mock_handle_vibe_request.assert_called_once()
        args, kwargs = mock_handle_vibe_request.call_args
        assert kwargs["request"] == "create a deployment"
        assert kwargs["command"] == "create"
        assert "plan_prompt" in kwargs
        assert kwargs["plan_prompt"] == PLAN_CREATE_PROMPT


def test_create_vibe_no_request(cli_runner: CliRunner) -> None:
    """Test error handling when no request is provided after vibe."""
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(create, ["vibe"])
        
        assert result.exit_code == 1
        mock_console.print_error.assert_called_once_with("Missing request after 'vibe'") 