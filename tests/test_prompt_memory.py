"""Tests for prompt module memory integration.

This module tests the memory integration in prompt templates.
"""

# Import datetime for patching
from datetime import datetime as dt
from unittest.mock import Mock, patch

import pytest

from vibectl.config import Config
from vibectl.prompts.shared import get_formatting_fragments

# Constants
TEST_MEMORY_CONTENT = "Memory content for tests"

# Fixture for config is implicitly used via test function arguments


@pytest.fixture
def mock_config() -> Mock:
    """Provides a mock Config object for isolated testing."""
    config = Mock(spec=Config)
    config.get.side_effect = lambda key, default=None: {
        "memory_enabled": True,
        "memory": TEST_MEMORY_CONTENT,
        "custom_instructions": None,
    }.get(key, default)
    return config


def test_get_formatting_fragments_with_no_memory() -> None:
    """Test formatting instructions when memory is disabled."""
    # Setup
    with (
        patch("vibectl.memory.is_memory_enabled", return_value=False),
        patch("vibectl.memory.get_memory") as mock_get_memory,
        patch("vibectl.prompt.Config") as mock_config_class,
    ):
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        mock_config.get.return_value = None

        # Execute
        system_fragments, user_fragments = get_formatting_fragments(mock_config)
        combined_text = "\n".join(system_fragments + user_fragments)

        # Assert
        assert "Memory context:" not in combined_text
        mock_get_memory.assert_not_called()


def test_get_formatting_fragments_with_empty_memory() -> None:
    """Test formatting instructions when memory is empty."""
    # Setup
    with (
        patch("vibectl.memory.is_memory_enabled", return_value=True),
        patch("vibectl.memory.get_memory", return_value=""),
        patch("vibectl.prompt.Config") as mock_config_class,
    ):
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        mock_config.get.return_value = None

        # Execute
        system_fragments, user_fragments = get_formatting_fragments(mock_config)
        combined_text = "\n".join(system_fragments + user_fragments)

        # Assert
        assert "Memory context:" not in combined_text


def test_get_formatting_fragments_with_provided_config() -> None:
    """Test formatting instructions with provided config."""
    # Setup
    mock_config = Mock()
    mock_config.get.return_value = None  # Simulate no custom_instructions

    # Patch datetime.now() to return a fixed datetime object
    fixed_datetime = dt(2023, 1, 1, 12, 0, 0)
    with patch("vibectl.prompts.shared.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_datetime
        # Execute
        system_fragments, user_fragments = get_formatting_fragments(mock_config)
        combined_text = "\n".join(system_fragments + user_fragments)

        # Assert
        # Check if the formatted fixed time is present
        # The fragment_current_time() prepends "Current time is "
        assert "Current time is 2023-01-01 12:00:00" in combined_text
        assert (
            "Format your response using rich.Console() markup syntax" in combined_text
        )
        assert "Important:" in combined_text
        # Ensure custom instructions part is not present if config returns None
        assert "Custom instructions:" not in combined_text


def test_formatting_with_memory_integration(mock_config: Mock) -> None:
    """Test that get_formatting_fragments runs with a memory-configured mock_config.
    Actual memory integration is handled by callers.
    """
    # mock_config fixture already sets up memory_enabled=True and TEST_MEMORY_CONTENT
    # via its .get side_effect. We are testing that get_formatting_fragments itself
    # doesn't break when such a config is passed, not that it USES the memory directly.

    system_fragments, user_fragments = get_formatting_fragments(mock_config)
    combined_text = "\n".join(
        system_fragments + user_fragments
    )  # For inspection if needed

    # Assert that get_formatting_fragments itself doesn't call these memory functions
    # This test now verifies that get_formatting_fragments *doesn't* do memory, which
    # is the new behavior.
    # We'd need other higher-level tests to verify memory IS integrated by the callers.

    # Accessing mock_config.get.called or similar would depend on how the mock_config
    # fixture is defined
    # For now, just ensuring it runs and doesn't include memory text directly is fine.
    assert "Memory context:" not in combined_text
    assert TEST_MEMORY_CONTENT not in combined_text


def test_formatting_respects_config_memory_disabled(mock_config: Mock) -> None:
    """Test that get_formatting_fragments respects memory_enabled=False from config."""
    mock_config.get.side_effect = lambda key, default=None: {
        "memory_enabled": False,
        "custom_instructions": None,
    }.get(key, default)
    system_fragments, user_fragments = get_formatting_fragments(mock_config)
    combined_text = "\n".join(system_fragments + user_fragments)
    assert "Memory context:" not in combined_text
