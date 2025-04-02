"""
Tests for vibectl CLI
"""
from typing import NoReturn

from click.testing import CliRunner

from vibectl.cli import cli

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