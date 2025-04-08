"""Tests for prompt module memory integration.

This module tests the memory integration in prompt templates.
"""

from unittest.mock import Mock, patch

from vibectl.prompt import get_formatting_instructions


def test_get_formatting_instructions_with_memory() -> None:
    """Test formatting instructions with memory."""
    # Setup
    with (
        patch("vibectl.memory.is_memory_enabled", return_value=True),
        patch("vibectl.memory.get_memory", return_value="Important cluster info"),
        patch("vibectl.prompt.Config") as mock_config_class,
    ):
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        mock_config.get.return_value = None  # No custom instructions

        # Execute
        result = get_formatting_instructions()

        # Assert
        assert "Memory context:" in result
        assert "Important cluster info" in result


def test_get_formatting_instructions_with_memory_and_instructions() -> None:
    """Test formatting instructions with both memory and custom instructions."""
    # Setup
    with (
        patch("vibectl.memory.is_memory_enabled", return_value=True),
        patch("vibectl.memory.get_memory", return_value="Important cluster info"),
        patch("vibectl.prompt.Config") as mock_config_class,
    ):
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        mock_config.get.return_value = "Custom instruction text"

        # Execute
        result = get_formatting_instructions()

        # Assert
        assert "Memory context:" in result
        assert "Important cluster info" in result
        assert "Custom instructions:" in result
        assert "Custom instruction text" in result


def test_get_formatting_instructions_with_disabled_memory() -> None:
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
        result = get_formatting_instructions()

        # Assert
        assert "Memory context:" not in result
        mock_get_memory.assert_not_called()


def test_get_formatting_instructions_with_empty_memory() -> None:
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
        result = get_formatting_instructions()

        # Assert
        assert "Memory context:" not in result


def test_get_formatting_instructions_with_provided_config() -> None:
    """Test formatting instructions with provided config."""
    # Setup
    mock_config = Mock()
    mock_config.get.return_value = None

    with (
        patch("vibectl.memory.is_memory_enabled", return_value=True),
        patch("vibectl.memory.get_memory", return_value="Memory with config"),
        patch("vibectl.prompt.Config") as mock_config_class,
        patch("vibectl.prompt.refresh_datetime", return_value="2023-01-01 12:00:00"),
    ):
        # Execute
        result = get_formatting_instructions(mock_config)

        # Assert
        assert "Memory context:" in result
        assert "Memory with config" in result
        assert "2023-01-01 12:00:00" in result
        mock_config_class.assert_not_called()  # Should not create a new config
