"""
Tests for vibectl CLI
"""

import subprocess
from unittest.mock import patch, Mock

import pytest
from click.testing import CliRunner

from vibectl.cli import cli


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_cli_version() -> None:
    """Test CLI version command"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


def test_vibe_command() -> None:
    """Test vibe command"""
    runner = CliRunner()
    result = runner.invoke(cli, ["vibe"])
    assert result.exit_code == 0
    assert "checking cluster vibes" in result.output.lower()


def test_no_vibes_proxy_command(cli_runner):
    """Test that --no-vibes properly proxies commands to kubectl"""
    mock_result = Mock()
    mock_result.stdout = "mock kubectl output\n"
    mock_result.stderr = ""

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        result = cli_runner.invoke(cli, ['--no-vibes', 'get', 'pods'])
        
        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            ['kubectl', 'get', 'pods'],
            check=True,
            text=True,
            capture_output=True
        )
        assert "mock kubectl output" in result.output


def test_no_vibes_kubectl_not_found(cli_runner):
    """Test error handling when kubectl is not found"""
    with patch('subprocess.run', side_effect=FileNotFoundError()):
        result = cli_runner.invoke(cli, ['--no-vibes', 'get', 'pods'])
        assert result.exit_code == 1
        assert "kubectl not found in PATH" in result.output


def test_no_vibes_kubectl_error(cli_runner):
    """Test error handling when kubectl returns an error"""
    mock_error = subprocess.CalledProcessError(1, ['kubectl'])
    mock_error.stderr = "mock kubectl error\n"
    
    with patch('subprocess.run', side_effect=mock_error):
        result = cli_runner.invoke(cli, ['--no-vibes', 'get', 'pods'])
        assert result.exit_code == 1
        assert "mock kubectl error" in result.output
