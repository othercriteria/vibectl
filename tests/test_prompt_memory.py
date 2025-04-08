"""Tests for prompt module memory integration.

This module tests the memory integration in prompt templates.
"""

from unittest.mock import Mock, patch

from vibectl.prompt import get_formatting_instructions


@patch("vibectl.prompt.is_memory_enabled")
@patch("vibectl.prompt.get_memory")
@patch("vibectl.prompt.Config")
def test_get_formatting_instructions_with_memory(
    mock_config_class: Mock, mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test formatting instructions with memory."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = None  # No custom instructions

    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Important cluster info"

    # Execute
    result = get_formatting_instructions()

    # Assert
    assert "Memory context:" in result
    assert "Important cluster info" in result
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()


@patch("vibectl.prompt.is_memory_enabled")
@patch("vibectl.prompt.get_memory")
@patch("vibectl.prompt.Config")
def test_get_formatting_instructions_with_memory_and_instructions(
    mock_config_class: Mock, mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test formatting instructions with both memory and custom instructions."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = "Custom instruction text"

    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Important cluster info"

    # Execute
    result = get_formatting_instructions()

    # Assert
    assert "Memory context:" in result
    assert "Important cluster info" in result
    assert "Custom instructions:" in result
    assert "Custom instruction text" in result
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()


@patch("vibectl.prompt.is_memory_enabled")
@patch("vibectl.prompt.get_memory")
@patch("vibectl.prompt.Config")
def test_get_formatting_instructions_with_disabled_memory(
    mock_config_class: Mock, mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test formatting instructions when memory is disabled."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = None

    mock_is_enabled.return_value = False

    # Execute
    result = get_formatting_instructions()

    # Assert
    assert "Memory context:" not in result
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_not_called()


@patch("vibectl.prompt.is_memory_enabled")
@patch("vibectl.prompt.get_memory")
@patch("vibectl.prompt.Config")
def test_get_formatting_instructions_with_empty_memory(
    mock_config_class: Mock, mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test formatting instructions when memory is empty."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = None

    mock_is_enabled.return_value = True
    mock_get_memory.return_value = ""

    # Execute
    result = get_formatting_instructions()

    # Assert
    assert "Memory context:" not in result
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()


@patch("vibectl.prompt.refresh_datetime")
@patch("vibectl.prompt.is_memory_enabled")
@patch("vibectl.prompt.get_memory")
@patch("vibectl.prompt.Config")
def test_get_formatting_instructions_with_provided_config(
    mock_config_class: Mock,
    mock_get_memory: Mock,
    mock_is_enabled: Mock,
    mock_refresh_datetime: Mock,
) -> None:
    """Test formatting instructions with provided config."""
    # Setup
    mock_config = Mock()
    mock_config.get.return_value = None

    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Memory with config"
    mock_refresh_datetime.return_value = "2023-01-01 12:00:00"

    # Execute
    result = get_formatting_instructions(mock_config)

    # Assert
    assert "Memory context:" in result
    assert "Memory with config" in result
    assert "2023-01-01 12:00:00" in result
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()
    mock_config_class.assert_not_called()  # Should not create a new config
