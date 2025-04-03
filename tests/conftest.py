"""Shared pytest fixtures."""

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """Fixture that provides a CliRunner instance for testing Click applications."""
    return CliRunner()
